"""MARK: pyckingsolver checks: the instance JSON, what the binary does with it, the native callback, the watchdog.

Usage:  cd test && uv run python test_pyckingsolver.py
"""

import json
import re
import sys
import tempfile
import threading
import time
from itertools import combinations
from pathlib import Path

from shapely.affinity import rotate, scale, translate
from shapely.geometry import Point, Polygon, box

import pyckingsolver as ps
import pyckingsolver.solve as opt

MAIN_CPP = Path(__file__).resolve().parents[1] / "extern/packingsolver/src/irregular/main.cpp"
PLATE = Polygon(box(0, 0, 150, 100).exterior,
                [Point(x, y).buffer(12, 16).exterior for x in (25, 125) for y in (25, 75)])
DISC = Point(8, 8).buffer(8, 16)  # a Shapely disc anchored at the origin


def params(**kw):
    p = ps.OptimizeParameters()
    p.time_limit, p.stall_timeout = 10, 2
    for k, v in kw.items():
        setattr(p, k, v)
    return p


def placed(shape, item):
    """The pose: mirrored (about the y axis), turned about the origin, then moved to `bl_corner`."""
    s = scale(shape, -1, 1, origin=(0, 0)) if item.mirror else shape
    return translate(rotate(s, item.angle, origin=(0, 0)), item.bl_corner.x, item.bl_corner.y)


# MARK: instance JSON


def test_instance_json():
    cw = Polygon([(0, 0, 5), (0, 10, 5), (10, 10, 5), (10, 0, 5)], [[(2, 2), (8, 2), (8, 8), (2, 8)]])
    ib = ps.InstanceBuilder()
    ib.set_objective(ps.Objective.Knapsack)
    ib.set_item_item_minimum_spacing(2.5)
    ib.set_leftover_mode(ps.LeftoverMode.TopRight)
    b = ib.add_bin_type(Polygon(box(0, 0, 100, 50).exterior, [[(40, 20), (60, 20), (60, 30)]]),
                        item_bin_minimum_spacing=1, copies=3)
    t = ib.add_item_type(cw, profit=7, copies=3, copies_min=1, allowed_rotations=[(0, 0, False), (90, 90, True)])
    ib.add_fixed_item(b, t, (1, 2))
    ib.set_item_types_continuous_rotations()
    d = ib.build().to_json()

    assert d["objective"] == "knapsack"
    assert d["parameters"] == {"item_item_minimum_spacing": 2.5, "leftover_mode": "TopRight"}
    item = d["item_types"][0]
    assert item["vertices"] == [{"x": 10, "y": 0}, {"x": 10, "y": 10}, {"x": 0, "y": 10}, {"x": 0, "y": 0}]
    assert item["holes"][0]["vertices"][1] == {"x": 8, "y": 2}, "every ring goes out counter-clockwise"
    assert (item["profit"], item["copies"], item["copies_min"]) == (7, 3, 1)
    assert item["allowed_rotations"] == [{"start": 0, "end": 360, "mirror": False}]
    bin0 = d["bin_types"][0]
    assert "holes" not in bin0 and bin0["defects"][0]["item_defect_minimum_spacing"] == 1, "a bin hole is a defect"
    assert bin0["fixed_items"][0]["bl_corner"] == {"x": 1, "y": 2}
    with tempfile.TemporaryDirectory() as tmp:
        ps.Instance(d).write(Path(tmp, "i.json"))
        ib.read(Path(tmp, "i.json"))
        assert ib.build().to_json() == d, "read() of a written instance is the same instance"
    print("   instance JSON: CCW rings, no Z, bin holes as defects, set_* sweeps, read/write round trip")


def test_every_cli_option_is_reachable():
    """Each main.cpp option is an OptimizeParameters field, an InstanceBuilder method, or wired by optimize()."""
    cli = set(re.findall(r'^\s*\("([a-z0-9-]+)[,"]', MAIN_CPP.read_text(), re.M))
    p = ps.OptimizeParameters()
    for f in opt.fields(p):
        if f.name not in opt._NOT_FLAGS:
            setattr(p, f.name, 1)
    p.reduction_parameters.reduce = True
    sent = {a[2:] for a in opt._flags(p, ps.Instance({"bin_types": []})) if a.startswith("--")}
    wired = {"input", "certificate", "output", "time-limit", "verbosity-level"}
    builder = {"objective", "item-bin-minimum-spacing", "item-item-minimum-spacing", "leftover-mode",
               "leftover-all-bins", "bin-unweighted", "unweighted", "continuous-rotations"}
    dead = {"log2stderr", "only-write-at-the-end"}  # main.cpp reads log-to-stderr; the stream is always on
    assert cli == sent | wired | builder | dead, f"flag drift: {sorted(cli ^ (sent | wired | builder | dead))}"
    print(f"   {len(cli)} CLI options: {len(sent)} parameters, {len(builder)} builder, {len(wired)} wired")


def test_native_shapes():
    """Upstream's shape types: exact arcs on the wire, exact areas, a Shapely round trip, exact circles solved."""
    import math
    circle = ps.build_circle(10)
    assert circle.to_json() == {"type": "circle", "x": 0.0, "y": 0.0, "radius": 10.0}
    assert abs(circle.compute_area() - math.pi * 100) < 1e-9
    slot = ps.build_shape([(0, 0), (20, 0), (20, 5, 1), (20, 10), (0, 10), (0, 5, 1)])  # a stadium: two half arcs
    assert slot.to_json()["type"] == "general" and abs(slot.compute_area() - (200 + math.pi * 25)) < 1e-9
    assert abs(ps.to_shapely(slot, 512).area - slot.compute_area()) < 0.1
    plate = ps.from_shapely(PLATE)
    assert len(plate.holes) == 4 and abs(plate.compute_area() - PLATE.area) < 1e-6

    ib = ps.InstanceBuilder()
    ib.set_objective(ps.Objective.Knapsack)
    ib.set_item_item_minimum_spacing(2)
    ib.add_bin_type(ps.build_rectangle(100, 40))
    ib.add_item_type(circle, copies=8)
    s = ps.optimize(ib.build(), params()).solution
    centers = [s.shape_scaled(0, k).shape.elements[0].center for k in range(len(s.bin(0).items))]
    gap = min(math.dist((a.x, a.y), (b.x, b.y)) - 20 for a, b in combinations(centers, 2))
    assert len(centers) >= 3 and gap >= 2 - 1e-6, (len(centers), gap)
    print(f"   native shapes: circle JSON, exact arc areas, Shapely round trip; {len(centers)} exact circles, "
          f"closest gap {gap:.3f} (spacing 2)")


# MARK: what the binary does


def test_holes_spacing_and_pose():
    ib = ps.InstanceBuilder()
    ib.set_objective(ps.Objective.Knapsack)
    ib.set_item_item_minimum_spacing(2.0)
    ib.add_bin_type(ps.build_rectangle(150, 100))
    ib.add_item_type(PLATE, copies_min=1)
    ib.add_item_type(DISC, copies=8)
    s = ps.optimize(ib.build(), params()).solution
    items = s.bin(0).items
    shapes = [placed(PLATE if i.item_type_id == 0 else DISC, i) for i in items]
    assert all(abs(p.area - ps.to_shapely(s.shape_scaled(0, k)).area) < 1 for k, p in enumerate(shapes)), "pose != certificate shape"
    holes = [Polygon(r) for p in shapes for r in p.interiors]
    in_holes = sum(any(h.contains(p) for h in holes) for p in shapes if p.area < 1000)
    gap = min(p.distance(q) for p, q in combinations(shapes, 2))
    assert in_holes == 4 and gap >= 2.0 - 1e-6, (in_holes, gap)
    print(f"   holes: {in_holes} discs in the plate's holes, closest pair {gap:.2f} (spacing 2)")


def test_copies_min_fixed_items_resources_infeasible():
    def knapsack(copies_min=None, capacity=None, pins=0):
        ib = ps.InstanceBuilder()
        ib.set_objective(ps.Objective.Knapsack)
        ib.add_bin_type(ps.build_rectangle(100, 100))
        big = ib.add_item_type(ps.build_rectangle(90, 90), profit=1, copies_min=copies_min)
        small = ib.add_item_type(ps.build_rectangle(20, 20), profit=50, copies=25)
        if capacity is not None:
            ib.add_resource_consumption(0, r := ib.add_bin_type_resource(0, capacity), small, [1])
            ib.set_bin_type_resource_tolerance(0, r, 0.5)  # upstream reads the key: a bad one throws
        for k in range(pins):  # identical pinned types: upstream's reduction would merge them and throw
            ib.add_fixed_item(0, ib.add_item_type(ps.build_rectangle(20, 20)), (k * 25, 80))
        return ps.optimize(ib.build(), params(time_limit=5)).solution

    assert knapsack().item_copies(0) == 0 and knapsack(copies_min=1).item_copies(0) == 1
    assert knapsack(capacity=3).item_copies(1) == 3, "a resource capacity caps the copies"
    s = knapsack(pins=3)
    assert sum(i.is_fixed for i in s.bin(0).items) == 3, "pins come back flagged"

    ib = ps.InstanceBuilder()
    ib.set_objective(ps.Objective.BinPacking)
    ib.add_bin_type(ps.build_rectangle(40, 20))
    ib.add_item_type(ps.build_rectangle(10, 30))
    out = ps.optimize(ib.build(), params(time_limit=2))
    assert out.is_proven_infeasible and out.solution.number_of_bins() == 0
    print("   copies_min forces an item, capacity 3 caps at 3, 3 pins flagged, infeasible reported")


def test_new_solution_callback_and_cancel():
    ib = ps.InstanceBuilder()
    ib.set_objective(ps.Objective.Knapsack)
    ib.add_bin_type(ps.build_rectangle(1000, 1000))
    for shape in (ps.build_rectangle(137, 89), ps.build_shape([(0, 0), (113, 0), (0, 97)]), ps.build_circle(41)):
        ib.add_item_type(shape, copies=40)
    instance = ib.build()
    outputs = []
    t0 = time.monotonic()
    out = ps.optimize(instance, params(time_limit=20, stall_timeout=1.5, new_solution_callback=outputs.append))
    elapsed = time.monotonic() - t0
    assert outputs and outputs[-1].solution.number_of_items() == out.solution.number_of_items() > 0
    assert outputs[-1].solution.profit() > 0, "a provisional output carries the binary's metrics"
    assert elapsed < 12, f"no early stop: {elapsed:.1f} of 20 s"

    cancel = threading.Event()
    threading.Timer(0.5, cancel.set).start()
    try:
        ps.optimize(instance, params(time_limit=20, stall_timeout=None, cancel=cancel))
        raise AssertionError("cancel ignored")
    except ps.OptimizeCancelled:
        pass
    print(f"   new_solution_callback: {len(outputs)} outputs, stopped at {elapsed:.1f} of 20 s; cancel raises")


# MARK: watchdog, on stand-in children (deterministic and fast)

_SLEEP = [sys.executable, "-c", "import time; time.sleep(30)"]


def _writer(path, texts, gap):
    """A child writing each text to `path`, `gap` apart, then hanging: a stalling solve."""
    return [sys.executable, "-c", f"import time,pathlib\np=pathlib.Path(r'{path}')\n"
            f"for t in {texts!r}:\n    p.write_text(t)\n    time.sleep({gap})\ntime.sleep(30)"]


def _certificate(items):
    """The binary's layout: indent 4, the top-level brace alone on the last line."""
    return json.dumps({"bins": [{"id": 0, "copies": 1, "items": [
        {"id": 0, "x": i, "y": 0, "angle": 0, "mirror": False} for i in range(items)]}]}, indent=4) + "\n"


def _watch(cmd_for, stall=None, first=None):
    seen = []
    with tempfile.TemporaryDirectory() as tmp:
        cert = Path(tmp) / "solution.json"
        t0 = time.monotonic()
        code, _, text = opt._run(cmd_for(cert), cert, 60, stall, first, None, seen.append)
        return code, text, time.monotonic() - t0, cert.read_text() if cert.exists() else None, seen


def test_watchdog():
    code, text, t, _, _ = _watch(lambda c: _SLEEP, first=1.0)
    assert code == 0 and text is None and t < 5, "a wedged solve stops at first_solution_timeout"

    certs = [_certificate(i + 1) for i in range(3)]
    code, text, t, _, seen = _watch(lambda c: _writer(c, certs, 0.3), stall=1.5)
    assert code == 0 and text == certs[-1] and 1.5 <= t < 6 and seen == certs, "each new layout, last one kept"

    _, text, t, _, _ = _watch(lambda c: _writer(c, ["null"], 0.1), stall=10, first=1.0)
    assert text is None and t < 3, "the null written at t~0 is not a layout"
    _, _, t, _, seen = _watch(lambda c: _writer(c, [_certificate(1)] * 8, 0.3), stall=1.0)
    assert t < 2.5 and len(seen) == 1, "rewrites of one layout (bound updates) are not progress"

    cert = _certificate(2)
    torn = cert[:cert.index("}") + 1]
    _, text, _, on_disk, _ = _watch(lambda c: _writer(c, [cert, torn], 0.3), stall=1.0)
    assert on_disk == torn and text == cert, "a stop mid-rewrite keeps the last complete certificate"
    print("   watchdog: first/stall stops, null and bound rewrites ignored, torn file ignored")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("All tests passed.")
