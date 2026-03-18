"""MARK: test_nesting — PackingSolver nesting tests with PNG output.

Usage:  cd python && uv run python test/test_nesting.py
"""

import subprocess
from pathlib import Path

import pymupdf
from shapely.geometry import Polygon, Point

from pyckingsolver import Instance, InstanceBuilder, Objective, Solution

# MARK: - Paths

_ROOT = Path(__file__).resolve().parents[1]           # python/
_REPO = _ROOT.parent                                  # pyckingsolver/
_SOLVER_DIR = _REPO / "extern" / "packingsolver"      # C++ submodule
_DATA = _SOLVER_DIR / "data" / "irregular"
_OUT = Path(__file__).resolve().parent


# MARK: - Helpers

def _find_solver() -> str:
    """Find the solver binary — bundled (pip install) or local build."""
    from pyckingsolver.solver import Solver
    return str(Solver._find_binary("irregular"))


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
    _render_png(sol, inst, ["#00cc88", "#ff6644"], _OUT / "test1_hole_fill.png")


# MARK: - Test 2: Frames + rings with fillers inside holes

def test_holes_with_fillers():
    """Frames and rings with small pieces designed to fit inside their holes."""
    print("\n[2] Custom hole nesting (fillers fit inside holes)")
    b = InstanceBuilder(Objective.OPEN_DIMENSION_X)
    b.add_bin_type_rectangle(800, 400)

    # Frame 200x150 with 120x80 hole -> filler 110x70 fits inside
    b.add_item_type(_rect(200, 150).difference(_rect(120, 80).buffer(0, join_style="mitre")
                    .__class__([(40, 35), (160, 35), (160, 115), (40, 115)])), copies=2)
    # Simpler: just build with explicit hole coords
    frame = Polygon([(0, 0), (200, 0), (200, 150), (0, 150)],
                    [[(40, 35), (160, 35), (160, 115), (40, 115)]])
    b._item_types.clear()
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
                _OUT / "test2_custom_holes.png")


# MARK: - Test 3: Metal cutting (plates, brackets, washers, gussets)

def test_metal_cutting():
    """Laser cutting: plates with bolt holes, U-brackets, washers, discs, gussets.
    Uses OPEN_DIMENSION_X so solver packs tightly — discs should fill holes."""
    print("\n[3] Metal cutting with holes")
    b = InstanceBuilder(Objective.OPEN_DIMENSION_X)
    b.set_item_item_minimum_spacing(2.0)
    b.add_bin_type_rectangle(1200, 300)
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
                _OUT / "test3_metal_cutting.png")


# MARK: - Main

def main():
    print(f"Solver: {_find_solver()}")
    print("PackingSolver Nesting Tests")
    print("=" * 40)
    test_hole_fill()
    test_holes_with_fillers()
    test_metal_cutting()
    print("\nAll tests passed.")


if __name__ == "__main__":
    main()
