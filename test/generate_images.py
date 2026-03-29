"""Generate PNG visualizations for all 12 test examples.

Usage:  cd pyckingsolver && uv run --directory python python test/generate_images.py
"""

from __future__ import annotations

import math
import os
import sys
import tempfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.collections import PatchCollection
from shapely.geometry import Point, Polygon, MultiPolygon

# ensure local pyckingsolver is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
from pyckingsolver import InstanceBuilder, Objective, Solver, Corner, Instance

_solver = Solver()
IMG_DIR = os.path.join(os.path.dirname(__file__), "..", "img")
os.makedirs(IMG_DIR, exist_ok=True)

# MARK: Color palette
COLORS = [
    "#4e79a7", "#f28e2b", "#e15759", "#76b7b2",
    "#59a14f", "#edc948", "#b07aa1", "#ff9da7",
    "#9c755f", "#bab0ac", "#86bcb6", "#d37295",
]
BIN_COLOR = "#f0f0f0"
BIN_EDGE = "#333333"
DEFECT_COLOR = "#ff4444"


def _poly_patch(poly, **kwargs):
    """Create a matplotlib patch from a Shapely Polygon."""
    from matplotlib.path import Path as MplPath
    import numpy as np

    verts = list(poly.exterior.coords)
    codes = [MplPath.MOVETO] + [MplPath.LINETO] * (len(verts) - 2) + [MplPath.CLOSEPOLY]

    for hole in poly.interiors:
        hverts = list(hole.coords)
        verts += hverts
        codes += [MplPath.MOVETO] + [MplPath.LINETO] * (len(hverts) - 2) + [MplPath.CLOSEPOLY]

    path = MplPath(verts, codes)
    return mpatches.PathPatch(path, **kwargs)


def _render(name: str, sol, instance_bins=None, defects=None, title=""):
    """Render solution bins as side-by-side subplots, save to IMG_DIR."""
    n_bins = len(sol.bins)
    if n_bins == 0:
        print(f"  {name}: no bins, skipping")
        return

    fig, axes = plt.subplots(1, n_bins, figsize=(6 * n_bins, 5), squeeze=False)
    fig.suptitle(title or name, fontsize=13, fontweight="bold", y=0.98)

    for idx, sbin in enumerate(sol.bins):
        ax = axes[0][idx]
        ax.set_aspect("equal")
        ax.set_title(f"Bin {idx} (type={sbin.bin_type_id}, {len(sbin.items)} items)",
                     fontsize=9)

        # Draw bin boundary if we know it
        if instance_bins and sbin.bin_type_id < len(instance_bins):
            bp = instance_bins[sbin.bin_type_id]
            if bp:
                patch = _poly_patch(bp, facecolor=BIN_COLOR, edgecolor=BIN_EDGE,
                                    linewidth=1.5, zorder=0)
                ax.add_patch(patch)

        # Draw defects
        if defects and sbin.bin_type_id in defects:
            for dp in defects[sbin.bin_type_id]:
                dpatch = _poly_patch(dp, facecolor=DEFECT_COLOR, edgecolor="darkred",
                                     alpha=0.4, linewidth=1, zorder=1)
                ax.add_patch(dpatch)

        # Draw items
        for i, item in enumerate(sbin.items):
            color = COLORS[item.item_type_id % len(COLORS)]
            for shape in item.shapes:
                if isinstance(shape, MultiPolygon):
                    for geom in shape.geoms:
                        p = _poly_patch(geom, facecolor=color, edgecolor="black",
                                        linewidth=0.6, alpha=0.85, zorder=2)
                        ax.add_patch(p)
                else:
                    p = _poly_patch(shape, facecolor=color, edgecolor="black",
                                    linewidth=0.6, alpha=0.85, zorder=2)
                    ax.add_patch(p)

        ax.autoscale_view()
        ax.set_xlabel("X", fontsize=8)
        ax.set_ylabel("Y", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.grid(True, alpha=0.2)

    plt.tight_layout(rect=[0, 0, 1, 0.94])
    path = os.path.join(IMG_DIR, f"{name}.png")
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  ✓ {path}")


# MARK: 1 — BIN_PACKING
def ex01():
    b = InstanceBuilder(Objective.BIN_PACKING)
    b.set_item_item_minimum_spacing(2.0)
    b.add_bin_type_rectangle(200, 150, copies=10)
    b.add_item_type_rectangle(60, 40, copies=5,
                              allowed_rotations=[(0, 0), (90, 90)])
    b.add_item_type(Polygon([(0, 0), (50, 0), (25, 40)]), copies=4)
    b.add_item_type_circle(15, copies=3)
    sol = _solver.solve(b.build(), time_limit=10)
    bins_geom = [Polygon([(0, 0), (200, 0), (200, 150), (0, 150)])]
    _render("ex01_bin_packing", sol, bins_geom,
            title="1. BIN_PACKING — fewest bins")


# MARK: 2 — KNAPSACK
def ex02():
    b = InstanceBuilder(Objective.KNAPSACK)
    b.add_bin_type_rectangle(200, 100)
    b.add_item_type_rectangle(80, 50, copies=3, profit=100.0)
    b.add_item_type_rectangle(40, 30, copies=6, profit=30.0)
    b.add_item_type(Polygon([(0, 0), (60, 0), (30, 50)]), copies=4, profit=55.0)
    sol = _solver.solve(b.build(), time_limit=10)
    bins_geom = [Polygon([(0, 0), (200, 0), (200, 100), (0, 100)])]
    _render("ex02_knapsack", sol, bins_geom,
            title="2. KNAPSACK — max profit")


# MARK: 3 — OPEN_DIMENSION_X
def ex03():
    b = InstanceBuilder(Objective.OPEN_DIMENSION_X)
    b.set_item_item_minimum_spacing(1.5)
    b.add_bin_type_rectangle(99999, 300)
    b.add_item_type_rectangle(80, 60, copies=6,
                              allowed_rotations=[(0, 0), (90, 90)])
    b.add_item_type(Polygon([(0, 0), (50, 0), (25, 45)]), copies=5,
                    allowed_rotations=[(0, 360)])
    sol = _solver.solve(b.build(), time_limit=10)
    # Compute actual used width
    max_x = max((s.bounds[2] for item in sol.all_items() for s in item.shapes), default=300)
    bins_geom = [Polygon([(0, 0), (max_x + 10, 0), (max_x + 10, 300), (0, 300)])]
    _render("ex03_strip_x", sol, bins_geom,
            title="3. OPEN_DIMENSION_X — minimize strip width")


# MARK: 4 — OPEN_DIMENSION_Y
def ex04():
    b = InstanceBuilder(Objective.OPEN_DIMENSION_Y)
    b.add_bin_type_rectangle(400, 99999)
    b.add_item_type_rectangle(60, 80, copies=4)
    b.add_item_type_rectangle(90, 40, copies=3)
    sol = _solver.solve(b.build(), time_limit=10)
    max_y = max((s.bounds[3] for item in sol.all_items() for s in item.shapes), default=200)
    bins_geom = [Polygon([(0, 0), (400, 0), (400, max_y + 10), (0, max_y + 10)])]
    _render("ex04_strip_y", sol, bins_geom,
            title="4. OPEN_DIMENSION_Y — minimize strip height")


# MARK: 5 — OPEN_DIMENSION_XY (may crash)
def ex05():
    b = InstanceBuilder(Objective.OPEN_DIMENSION_XY)
    b.add_bin_type_rectangle(99999, 99999)
    b.add_item_type_rectangle(30, 20, copies=6)
    b.add_item_type_rectangle(40, 25, copies=4)
    try:
        sol = _solver.solve(b.build(), time_limit=10)
        max_x = max((s.bounds[2] for item in sol.all_items() for s in item.shapes), default=200)
        max_y = max((s.bounds[3] for item in sol.all_items() for s in item.shapes), default=200)
        bins_geom = [Polygon([(0, 0), (max_x + 10, 0), (max_x + 10, max_y + 10), (0, max_y + 10)])]
        _render("ex05_open_xy", sol, bins_geom,
                title="5. OPEN_DIMENSION_XY — compact rectangle")
    except RuntimeError:
        print("  ⚠ ex05_open_xy: SKIPPED (C++ solver crash)")


# MARK: 6 — VARIABLE_SIZED_BIN_PACKING
def ex06():
    b = InstanceBuilder(Objective.VARIABLE_SIZED_BIN_PACKING)
    b.set_item_item_minimum_spacing(2.0)
    b.add_bin_type_rectangle(200, 150, cost=1.0, copies=5)
    b.add_bin_type_rectangle(400, 300, cost=3.5, copies=3)
    b.add_item_type_rectangle(60, 40, copies=8)
    b.add_item_type_rectangle(80, 50, copies=4)
    b.add_item_type(Polygon([(0, 0), (70, 0), (35, 55)]), copies=3)
    sol = _solver.solve(b.build(), time_limit=10)
    bins_geom = [
        Polygon([(0, 0), (200, 0), (200, 150), (0, 150)]),
        Polygon([(0, 0), (400, 0), (400, 300), (0, 300)]),
    ]
    _render("ex06_variable_bins", sol, bins_geom,
            title="6. VARIABLE_SIZED_BIN_PACKING — min cost")


# MARK: 7 — BIN_PACKING_WITH_LEFTOVERS
def ex07():
    b = InstanceBuilder(Objective.BIN_PACKING_WITH_LEFTOVERS)
    b.set_leftover_corner(Corner.BOTTOM_LEFT)
    b.add_bin_type_rectangle(300, 200, copies=5)
    b.add_item_type_rectangle(100, 80, copies=3)
    b.add_item_type_rectangle(60, 50, copies=5)
    sol = _solver.solve(b.build(), time_limit=10)
    bins_geom = [Polygon([(0, 0), (300, 0), (300, 200), (0, 200)])]
    _render("ex07_leftovers", sol, bins_geom,
            title="7. BIN_PACKING_WITH_LEFTOVERS")


# MARK: 8 — Defects
def ex08():
    b = InstanceBuilder(Objective.BIN_PACKING)
    bin_id = b.add_bin_type_rectangle(300, 200, copies=5)
    scratch = Point(150, 100).buffer(25)
    b.add_defect(bin_id, scratch, item_defect_minimum_spacing=3.0)
    b.add_item_type_rectangle(60, 40, copies=6,
                              allowed_rotations=[(0, 0), (90, 90)])
    sol = _solver.solve(b.build(), time_limit=10)
    bins_geom = [Polygon([(0, 0), (300, 0), (300, 200), (0, 200)])]
    defects = {0: [scratch]}
    _render("ex08_defects", sol, bins_geom, defects=defects,
            title="8. DEFECTS — avoid scratch zone")


# MARK: 9 — Polygon bins (hexagon)
def ex09():
    b = InstanceBuilder(Objective.KNAPSACK)
    hex_pts = [(100 * math.cos(math.pi / 3 * i),
                100 * math.sin(math.pi / 3 * i)) for i in range(6)]
    hex_poly = Polygon(hex_pts)
    b.add_bin_type(hex_poly)
    b.add_item_type_rectangle(30, 20, copies=8, profit=1.0,
                              allowed_rotations=[(0, 0), (60, 60), (120, 120)])
    b.add_item_type_circle(10, copies=5, profit=0.5)
    sol = _solver.solve(b.build(), time_limit=10)
    _render("ex09_polygon_bin", sol, [hex_poly],
            title="9. POLYGON BIN — hexagonal")


# MARK: 10 — Holes & mirroring
def ex10():
    b = InstanceBuilder(Objective.BIN_PACKING)
    b.set_item_item_minimum_spacing(2.0)
    b.add_bin_type_rectangle(400, 300)
    frame = Polygon([(0, 0), (100, 0), (100, 80), (0, 80)],
                    [[(20, 15), (80, 15), (80, 65), (20, 65)]])
    b.add_item_type(frame, copies=3, allow_mirroring=True,
                    allowed_rotations=[(0, 0), (90, 90)])
    lshape = Polygon([(0, 0), (60, 0), (60, 20), (20, 20), (20, 50), (0, 50)])
    b.add_item_type(lshape, copies=4, allow_mirroring=True,
                    allowed_rotations=[(0, 0), (90, 90), (180, 180), (270, 270)])
    sol = _solver.solve(b.build(), time_limit=10)
    bins_geom = [Polygon([(0, 0), (400, 0), (400, 300), (0, 300)])]
    _render("ex10_holes_mirror", sol, bins_geom,
            title="10. HOLES & MIRRORING")


# MARK: 11 — LP solver + anchor
def ex11():
    b = InstanceBuilder(Objective.BIN_PACKING)
    b.set_item_item_minimum_spacing(1.0)
    b.add_bin_type_rectangle(200, 150)
    b.add_item_type_rectangle(50, 30, copies=6)
    b.add_item_type(Polygon([(0, 0), (40, 0), (20, 35)]), copies=4)
    sol = _solver.solve(
        b.build(), time_limit=10,
        linear_programming_solver="Highs",
        anchor_to_corner=True,
        anchor_to_corner_corner=Corner.BOTTOM_LEFT,
    )
    bins_geom = [Polygon([(0, 0), (200, 0), (200, 150), (0, 150)])]
    _render("ex11_lp_anchor", sol, bins_geom,
            title="11. LP=Highs + ANCHOR post-processing")


# MARK: 12 — JSON round-trip
def ex12():
    b = InstanceBuilder(Objective.BIN_PACKING)
    b.add_bin_type_rectangle(200, 150)
    b.add_item_type_rectangle(60, 40, copies=4)
    inst = b.build()
    path = os.path.join(tempfile.gettempdir(), "_pycks_rt.json")
    inst.to_json(path)
    loaded = Instance.from_json(path)
    sol = _solver.solve(loaded, time_limit=5)
    os.unlink(path)
    bins_geom = [Polygon([(0, 0), (200, 0), (200, 150), (0, 150)])]
    _render("ex12_json_roundtrip", sol, bins_geom,
            title="12. JSON ROUND-TRIP")


def main():
    print(f"Generating images to {IMG_DIR} ...")
    examples = [ex01, ex02, ex03, ex04, ex05, ex06,
                ex07, ex08, ex09, ex10, ex11, ex12]
    for fn in examples:
        try:
            fn()
        except Exception as e:
            print(f"  ✗ {fn.__name__}: {e}")
    print("Done.")


if __name__ == "__main__":
    main()
