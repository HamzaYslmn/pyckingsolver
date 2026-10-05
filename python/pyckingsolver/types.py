"""Dataclasses and enums for the irregular packing problem.

Mirrors fontanf/packingsolver/irregular. Geometry is stored as Shapely Polygons
(holes go in interior rings); coordinates are in user units and angles in degrees.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from shapely.geometry import MultiPolygon, Polygon

# A shape accepted by the builder: arbitrary Shapely geometry.
ShapeLike = Polygon | MultiPolygon


class Objective(str, enum.Enum):
    """Packing objective. Values match the C++ kebab-case CLI strings.

    Only the objectives irregular solves: OpenDimensionZ and the sequential 1D subproblem throw.
    """
    KNAPSACK = "knapsack"
    BIN_PACKING = "bin-packing"
    BIN_PACKING_WITH_LEFTOVERS = "bin-packing-with-leftovers"
    OPEN_DIMENSION_X = "open-dimension-x"
    OPEN_DIMENSION_Y = "open-dimension-y"
    OPEN_DIMENSION_XY = "open-dimension-xy"
    VARIABLE_SIZED_BIN_PACKING = "variable-sized-bin-packing"
    FEASIBILITY = "feasibility"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            v = _OBJ_ALIASES.get(value)
            if v:
                return cls(v)
        return None


_OBJ_ALIASES = {
    "Knapsack": "knapsack", "KP": "knapsack",
    "BinPacking": "bin-packing", "BPP": "bin-packing",
    "BinPackingWithLeftovers": "bin-packing-with-leftovers",
    "BPPL": "bin-packing-with-leftovers",
    "OpenDimensionX": "open-dimension-x", "ODX": "open-dimension-x",
    "OpenDimensionY": "open-dimension-y", "ODY": "open-dimension-y",
    "OpenDimensionXY": "open-dimension-xy", "ODXY": "open-dimension-xy",
    "VariableSizedBinPacking": "variable-sized-bin-packing",
    "VBPP": "variable-sized-bin-packing", "VSBP": "variable-sized-bin-packing",
    "Feasibility": "feasibility",
}


class LeftoverMode(str, enum.Enum):
    """Reference corner/edge for leftover/anchor calculations."""
    BOTTOM_LEFT = "BottomLeft"
    BOTTOM_RIGHT = "BottomRight"
    TOP_LEFT = "TopLeft"
    TOP_RIGHT = "TopRight"
    LEFT = "Left"
    RIGHT = "Right"
    BOTTOM = "Bottom"
    TOP = "Top"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            v = {"bl": "BottomLeft", "br": "BottomRight",
                 "tl": "TopLeft", "tr": "TopRight",
                 "bottom-left": "BottomLeft", "bottom-right": "BottomRight",
                 "top-left": "TopLeft", "top-right": "TopRight",
                 "l": "Left", "r": "Right", "b": "Bottom", "t": "Top",
                 "left": "Left", "right": "Right",
                 "bottom": "Bottom", "top": "Top"}.get(value)
            if v:
                return cls(v)
        return None


@dataclass
class AllowedRotation:
    """Continuous rotation range with optional mirror.

    Maps to upstream `AllowedRotation { start_angle, end_angle, mirror }`.
    A discrete angle has `start_angle == end_angle`.
    """
    start_angle: float = 0.0
    end_angle: float = 0.0
    mirror: bool = False


@dataclass
class Defect:
    """A defect region inside a bin (excluded area)."""
    shape: ShapeLike = field(default_factory=Polygon)
    defect_type: int = -1
    item_defect_minimum_spacing: float = 0.0


@dataclass
class FixedItem:
    """A pre-placed item that the solver packs around.

    Applies to every bin of the parent BinType.
    """
    item_type_id: int = 0
    bl_corner: tuple[float, float] = (0.0, 0.0)
    angle: float = 0.0
    mirror: bool = False


@dataclass
class BinType:
    """A bin (sheet/container) definition.

    `cost = -1` means the C++ solver uses the bin's area as cost.
    """
    shape: ShapeLike = field(default_factory=Polygon)
    cost: float = -1.0
    copies: int = 1
    copies_min: int = 0
    item_bin_minimum_spacing: float = 0.0
    defects: list[Defect] = field(default_factory=list)
    fixed_items: list[FixedItem] = field(default_factory=list)


@dataclass
class ItemShape:
    """A single shape component of an item (items can be multi-shape)."""
    shape: ShapeLike = field(default_factory=Polygon)
    # (x, y, radius): sent as a native circle, so the solver sees the exact disc; `shape` is
    # its polygon for Python-side use.
    circle: tuple[float, float, float] | None = None


@dataclass
class ItemType:
    """An item (part) definition."""
    shapes: list[ItemShape] = field(default_factory=list)
    profit: float = -1.0
    copies: int = 1
    copies_min: int = -1  # -1: solver default (0 for KNAPSACK, `copies` otherwise)
    allowed_rotations: list[AllowedRotation] = field(
        default_factory=lambda: [AllowedRotation()])


@dataclass
class Parameters:
    """Global problem-level parameters."""
    item_item_minimum_spacing: float = 0.0
    open_dimension_xy_aspect_ratio: float = -1.0
    leftover_mode: LeftoverMode = LeftoverMode.BOTTOM_LEFT


@dataclass
class SolutionItem:
    """One placed item in the solution."""
    item_type_id: int = 0
    x: float = 0.0
    y: float = 0.0
    angle: float = 0.0
    mirror: bool = False
    is_fixed: bool = False
    shapes: list[Polygon | MultiPolygon] = field(default_factory=list)


@dataclass
class SolutionBin:
    """One bin used in the solution."""
    bin_type_id: int = 0
    copies: int = 1
    items: list[SolutionItem] = field(default_factory=list)
    shape: Polygon | None = None
    defects: list[Polygon | MultiPolygon] = field(default_factory=list)
# __PYCK_END__
