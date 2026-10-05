"""MARK: test_nesting — PackingSolver nesting tests with PNG output.

Usage:  cd pyckingsolver && uv run --directory python python ../test/test_nesting.py
"""

import dataclasses
import json
import math
import re
import subprocess
import tempfile
from pathlib import Path

import pymupdf
from shapely.geometry import MultiPolygon, Polygon, Point

from pyckingsolver import Instance, InstanceBuilder, Objective, Solution, Solver, SolverInfeasible, SolverParams
from pyckingsolver.geometry import ARC_RESOLUTION, circle_polygon

# MARK: - Paths

_REPO = Path(__file__).resolve().parents[1]            # pyckingsolver/
_SOLVER_DIR = _REPO / "extern" / "packingsolver"      # C++ submodule
_DATA = _SOLVER_DIR / "data" / "irregular"
_OUT = Path(__file__).resolve().parent            # scratch for the temp instance/solution
_IMG = _REPO / "img"                              # the README gallery, the only home for PNGs


# MARK: - Helpers

def _find_solver() -> str:
    """Find the solver binary — bundled (pip install) or local build."""
    return str(Solver().binary)


def _solve(instance: Instance, time_limit: int = 15) -> Solution:
    """Run C++ solver, return parsed Solution."""
    solver_bin = _find_solver()
    json_path = _OUT / "_tmp_instance.json"
    sol_path = _OUT / "_tmp_solution.json"
    try:
        instance.to_json(json_path)
        result = subprocess.run(
            [solver_bin, "--input", str(json_path),
             "--time-limit", str(time_limit), "--certificate", str(sol_path)],
            capture_output=True, text=True, timeout=time_limit + 30,
        )
        assert result.returncode == 0, f"Solver failed:\n{result.stderr}"
        return Solution.from_json(sol_path)
    finally:
        json_path.unlink(missing_ok=True)
        sol_path.unlink(missing_ok=True)


def _render_png(sol: Solution, inst: Instance, colors: list[str], path: Path):
    """Render first bin of solution to PNG via SVG + PyMuPDF."""
    bt = inst.bin_types[sol.bins[0].bin_type_id]
    bx0, by0, bx1, by1 = bt.shape.bounds
    w, h = bx1 - bx0, by1 - by0
    m = max(w, h) * 0.03
    vw, vh = w + 2 * m, h + 2 * m
    ox, oy = bx0 - m, by0 - m

    def _poly_d(poly):
        """Shapely Polygon -> SVG path d (exterior + holes)."""
        parts = []
        for ring in [poly.exterior, *poly.interiors]:
            pts = " ".join(f"{x - ox:.1f} {vh - (y - oy):.1f}" for x, y in ring.coords)
            parts.append(f"M {pts} Z")
        return " ".join(parts)

    elems = [f'<rect x="0" y="0" width="{vw:.1f}" height="{vh:.1f}" fill="#1a1a2e"/>']
    elems.append(f'<path d="{_poly_d(bt.shape)}" fill="none" stroke="#555" '
                 f'stroke-width="2" stroke-dasharray="8 4"/>')
    for item in sol.bins[0].items:
        c = colors[item.item_type_id % len(colors)]
        for poly in item.shapes:
            elems.append(f'<path d="{_poly_d(poly)}" fill="{c}70" stroke="{c}" '
                         f'stroke-width="1.5" fill-rule="evenodd"/>')

    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vw:.1f} {vh:.1f}" '
           f'width="{int(vw * 4)}" height="{int(vh * 4)}">{"".join(elems)}</svg>')
    doc = pymupdf.open(stream=svg.encode("utf-8"), filetype="svg")
    path.write_bytes(doc[0].get_pixmap().tobytes(output="png"))
    doc.close()
    print(f"  -> {path.name}")


def _rect(w, h):
    return Polygon([(0, 0), (w, 0), (w, h), (0, h)])


def _ring(outer_r, inner_r, res=32):
    return Point(0, 0).buffer(outer_r, resolution=res).difference(
        Point(0, 0).buffer(inner_r, resolution=res))


def _disc(r, res=32):
    return Point(0, 0).buffer(r, resolution=res)


# MARK: - Test 1: Existing C++ test (exact hole fill)

def test_hole_fill():
    """400x300 frame with 200x100 hole + matching 200x100 filler."""
    print("\n[1] Existing polygon_with_hole.json")
    inst = Instance.from_json(_DATA / "tests" / "polygon_with_hole.json")
    sol = _solve(inst)
    print(f"   {sol.total_item_count()} items in {sol.total_bins_used()} bin")
    _render_png(sol, inst, ["#00cc88", "#ff6644"], _IMG / "test1_hole_fill.png")


# MARK: - Test 2: Frames + rings with fillers inside holes

def test_holes_with_fillers():
    """Frames and rings with small pieces designed to fit inside their holes."""
    print("\n[2] Custom hole nesting (fillers fit inside holes)")
    b = InstanceBuilder(Objective.OPEN_DIMENSION_X)
    b.add_bin_type_rectangle(800, 400)

    # Frame 200x150 with 120x80 hole -> filler 110x70 fits inside
    frame = Polygon([(0, 0), (200, 0), (200, 150), (0, 150)],
                    [[(40, 35), (160, 35), (160, 115), (40, 115)]])
    b.add_item_type(frame, copies=2)                     # green frame
    b.add_item_type(_rect(110, 70), copies=2)            # red filler for frame hole
    b.add_item_type(_ring(60, 35), copies=2)             # blue ring (hole R=35)
    b.add_item_type(_disc(30), copies=2)                 # yellow disc (R=30 < hole R=35)
    b.add_item_type(Polygon([(0,0),(100,0),(100,30),(30,30),(30,80),(0,80)]), copies=3)  # pink L-bracket
    b.add_item_type(Polygon([(0,0),(80,0),(40,60)]), copies=4)                          # cyan triangle

    inst = b.build()
    print(f"   {sum(it.copies for it in inst.item_types)} items, {len(inst.item_types)} types")
    sol = _solve(inst)
    print(f"   {sol.total_item_count()} items in {sol.total_bins_used()} bin")
    _render_png(sol, inst, ["#00cc88", "#ff6644", "#4488ff", "#ffcc00", "#ff44aa", "#44ffcc"],
                _IMG / "test2_custom_holes.png")


# MARK: - Test 3: Metal cutting (plates, brackets, washers, gussets)

def test_metal_cutting():
    """Laser cutting: plates with bolt holes, U-brackets, washers, discs, gussets.

    OPEN_DIMENSION_X minimises the used X extent, nothing else. A part already behind the
    frontier costs the objective nothing wherever it sits, so hole filling here is
    opportunistic (4 of the 8 discs land in a hole) rather than something the objective buys;
    filling every hole needs the hole to be the only space left, as in test 2. The packing is
    identical at bin widths 360, 400 and 1200, so the bin is sized to the result.
    """
    print("\n[3] Metal cutting with holes")
    b = InstanceBuilder(Objective.OPEN_DIMENSION_X)
    b.set_item_item_minimum_spacing(2.0)
    b.add_bin_type_rectangle(400, 300)
    rots_4 = [(0, 0), (90, 90), (180, 180), (270, 270)]

    # Mounting plate 150x100 with 4 bolt holes R=12
    plate = _rect(150, 100)
    for cx, cy in [(25, 25), (125, 25), (25, 75), (125, 75)]:
        plate = plate.difference(Point(cx, cy).buffer(12, resolution=16))
    b.add_item_type(plate, copies=4, allowed_rotations=rots_4)

    # Disc R=8 fits in bolt hole (R=12 - R=8 = 4mm gap > 2mm spacing)
    b.add_item_type(_disc(8, res=16), copies=8)

    # U-bracket
    b.add_item_type(Polygon([(0,0),(80,0),(80,60),(70,60),(70,10),(10,10),(10,60),(0,60)]),
                    copies=6, allowed_rotations=rots_4)

    # Washer R=20 / R=12  (hole R=12 fits disc R=8 with 2mm gap)
    b.add_item_type(_ring(20, 12, res=16), copies=4)

    # Triangular gusset
    b.add_item_type(Polygon([(0,0),(50,0),(0,50)]), copies=6, allowed_rotations=rots_4)

    inst = b.build()
    print(f"   {sum(it.copies for it in inst.item_types)} items, {len(inst.item_types)} types")
    sol = _solve(inst)
    print(f"   {sol.total_item_count()} items in {sol.total_bins_used()} bin")
    _render_png(sol, inst, ["#22dd88", "#ff5533", "#3399ff", "#ffdd33", "#ff55cc"],
                _IMG / "test3_metal_cutting.png")


# MARK: - Test 4: wrapper invariants that a solver upgrade can silently break


def test_wrapper_invariants():
    """copies_min reaches the solver, circles stay 64-gons, both JSON forms hold."""
    print("\n[4] Wrapper invariants")

    def _instance(copies_min):
        b = InstanceBuilder(Objective.KNAPSACK)
        b.add_bin_type_rectangle(100, 100)
        b.add_item_type_rectangle(90, 90, copies=1, profit=1, copies_min=copies_min)
        b.add_item_type_rectangle(20, 20, copies=25, profit=50)
        return b.build()

    solver = Solver()

    def _big_placed(copies_min):
        """Copies of the big low-profit item that KNAPSACK actually packed."""
        sol = solver.solve(_instance(copies_min), time_limit=5)
        assert sol is not None, f"no solution for copies_min={copies_min}"
        return sol, sum(1 for it in sol.all_items() if it.item_type_id == 0)

    free_sol, free_big = _big_placed(-1)
    assert free_big == 0, f"knapsack kept the low-profit item unasked ({free_big})"
    _, forced_big = _big_placed(1)
    assert forced_big == 1, f"copies_min=1 did not force the item in ({forced_big})"

    # ARC_RESOLUTION counts vertices per full circle on both sides of the wire.
    n = len(circle_polygon(50).exterior.coords) - 1
    assert n == ARC_RESOLUTION, f"circle_polygon emits {n} vertices, not {ARC_RESOLUTION}"

    # metrics is the flattened Output, not the raw --output document.
    m = free_sol.metrics
    assert "IntermediaryOutputs" not in m, "metrics still carries the per-improvement log"
    for key in ("BinCost", "ItemProfit", "FullWastePercentage", "Time", "IsProvenInfeasible"):
        assert key in m, f"metrics missing {key!r}: {sorted(m)}"

    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "sol.json"
        solver.solve(_instance(-1), time_limit=5, json_output=str(out))
        # json_output is the certificate: it must read back with geometry intact.
        reread = Solution.from_json(out)
        placed = reread.all_items()
        assert placed and placed[0].shapes, "json_output round trip lost the item geometry"

    # to_json() stays the sparse form upstream's SolutionBuilder::read accepts.
    bin0 = json.loads(reread.to_json())["bins"][0]
    assert {"id", "copies"} <= bin0.keys(), f"bin keys: {sorted(bin0)}"
    assert {"id", "x", "y", "angle", "mirror"} <= bin0["items"][0].keys(), (
        f"item keys: {sorted(bin0['items'][0])}")

    # Every main.cpp option is emitted by _build_cmd, and every SolverParams field reaches one.
    from pyckingsolver import solver as s
    main_cpp = Path(__file__).parents[1] / "extern/packingsolver/src/irregular/main.cpp"
    cpp = {"--" + o for o in re.findall(r'^\s*\("([a-z0-9-]+)[,"]', main_cpp.read_text(), re.M)}
    attrs = s._BOOL_VALUE_FLAGS + s._VALUE_FLAGS + s._PRESENCE_FLAGS + s._TRUE_ONLY_FLAGS
    fixed = {"--input", "--certificate", "--output", "--time-limit", "--verbosity-level"}
    dead = {"--log2stderr", "--item-bin-minimum-spacing"}  # declared in main.cpp, never read there
    sent = {s._flag(a) for a in attrs} | fixed | dead
    assert cpp == sent, f"flag drift: {cpp ^ sent}"
    wrapper_only = {"time_limit", "verbosity_level", "stall_timeout", "first_solution_timeout",
                    "extra_args", "item_bin_minimum_spacing"}
    unmapped = {f.name for f in dataclasses.fields(SolverParams)} - set(attrs) - wrapper_only
    assert not unmapped, f"SolverParams fields never sent: {unmapped}"

    print(f"   copies_min: {free_big} -> {forced_big} big item, {n}-gon circles, "
          f"{len(m)} metric keys, both JSON forms intact, {len(cpp)} CLI flags in sync")


def test_wire_contract():
    """What the C++ silently drops or rejects is handled on the Python side."""
    print("\n[5] Wire contract")
    solver = Solver()

    # A bin hole is a no-go zone (the C++ reads bins without holes).
    b = InstanceBuilder(Objective.KNAPSACK)
    hole = Polygon([(40, 40), (60, 40), (60, 60), (40, 60)])
    b.add_bin(Polygon([(0, 0), (100, 0), (100, 100), (0, 100)], [hole.exterior.coords]))
    b.add_item_type_rectangle(10, 10, copies=100, profit=1)
    inst = b.build()
    sol = solver.solve(inst, time_limit=2)
    inside = [it for it in sol.all_items() if it.shapes[0].intersection(hole).area > 1e-6]
    assert not inside, f"{len(inside)} items placed in the bin hole"

    # build() is a snapshot; a fractional time limit is not truncated to 0.
    b.add_defect(0, Polygon([(0, 0), (5, 0), (5, 5)]))
    assert not inst.bin_types[0].defects, "builder change leaked into a built Instance"
    from pyckingsolver.solver import _build_cmd
    cmd = _build_cmd(Path("x"), Path("i"), Path("c"), Path("o"), SolverParams(time_limit=0.5))
    assert cmd[cmd.index("--time-limit") + 1] == "0.5"

    # A MultiPolygon item is one item of several shapes; Z coordinates are dropped.
    b2 = InstanceBuilder(Objective.KNAPSACK)
    b2.add_bin_type_rectangle(100, 100)
    b2.add_item(MultiPolygon([_rect(10, 10), Polygon([(20, 0, 5), (30, 0, 5), (30, 10, 5), (20, 10, 5)])]),
                profit=1)
    sol2 = solver.solve(b2.build(), time_limit=2)
    assert sol2 and len(sol2.all_items()[0].shapes) == 2, "MultiPolygon item lost a part"

    # item_bin_minimum_spacing reaches the bins (tree search: upstream local search ignores it).
    b3 = InstanceBuilder(Objective.BIN_PACKING)
    b3.add_bin_type_rectangle(100, 100)
    b3.add_item_type_rectangle(30, 30, copies=4)
    sol3 = solver.solve(b3.build(), time_limit=2, use_tree_search=True, item_bin_minimum_spacing=5)
    edge = min(min(it.shapes[0].bounds[:2]) for it in sol3.all_items())
    assert edge >= 5 - 1e-6, f"item {edge} from the bin edge, spacing 5"

    # Proven infeasible raises, naming the item type that fits no bin; rotating it would fit.
    b4 = InstanceBuilder(Objective.BIN_PACKING)
    b4.add_bin_type_rectangle(40, 20)
    b4.add_item_type_rectangle(10, 10)
    b4.add_item_type_rectangle(10, 30)
    inst4 = b4.build()
    assert inst4.fits_some_bin(0) and not inst4.fits_some_bin(1)
    try:
        solver.solve(inst4, time_limit=2)
        raise AssertionError("infeasible instance returned")
    except SolverInfeasible as e:
        assert e.item_type_ids == [1], e.item_type_ids
    b4.add_item_type_rectangle(10, 30, allowed_rotations=[0, 90])
    assert b4.build().fits_some_bin(2)

    # Typed stats: 4 30x30 squares in one 100x100 bin is optimal for BIN_PACKING.
    assert sol3.number_of_items == 4 and sol3.number_of_bins == 1 and sol3.is_proven_optimal

    # Fixed items turn upstream's reduction off: it merges identical pinned types and throws.
    b6 = InstanceBuilder(Objective.KNAPSACK)
    b6.add_bin_type_rectangle(200, 200)
    for i in range(3):
        b6.add_fixed_item(0, b6.add_item_type_rectangle(20, 20), (i * 30, 0))
    b6.add_item_type_rectangle(20, 20, copies=5, profit=1)
    assert solver.solve(b6.build(), time_limit=2).number_of_items == 8

    # A radius is a native circle: exact discs reach the solver, arcs come back.
    b5 = InstanceBuilder(Objective.KNAPSACK)
    b5.add_bin_type_rectangle(100, 100)
    b5.add_item(10.0, copies=30, profit=1)
    inst5 = b5.build()
    assert inst5.to_dict()["item_types"][0]["type"] == "circle"
    assert Instance.from_dict(inst5.to_dict()).item_types[0].shapes[0].circle == (0.0, 0.0, 10.0)
    sol5 = solver.solve(inst5, time_limit=2)
    discs = sol5.all_items()
    assert discs and all(abs(d.shapes[0].area - math.pi * 100) < 1.0 for d in discs)

    # A relative instance path resolves against the caller's cwd, not the temp dir.
    with tempfile.TemporaryDirectory(dir=".") as d:
        rel = Path(Path(d).name) / "inst.json"
        b2.build().to_json(rel)
        assert solver.solve(str(rel), time_limit=2) is not None

    print(f"   bin hole respected ({len(sol.all_items())} items), snapshot build, 0.5s limit, "
          f"MultiPolygon/Z item, item-bin spacing, SolverInfeasible names the misfit, typed stats, {len(discs)} native discs, relative path")


# MARK: - Main

def main():
    print(f"Solver: {_find_solver()}")
    print("PackingSolver Nesting Tests")
    print("=" * 40)
    test_hole_fill()
    test_holes_with_fillers()
    test_metal_cutting()
    test_wrapper_invariants()
    test_wire_contract()
    print("\nAll tests passed.")


if __name__ == "__main__":
    main()
