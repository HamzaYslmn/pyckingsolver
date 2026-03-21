"""Core types and enums for PackingSolver.

All dataclasses carry an ``_extra`` dict that preserves unknown JSON fields,
ensuring forward-compatibility when the C++ solver adds new features.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Optional

from shapely.geometry import Polygon, MultiPolygon


# MARK: - Enums

class Objective(str, enum.Enum):
    """Packing objective function.

    The C++ solver accepts multiple formats per objective (kebab-case,
    PascalCase, abbreviation).  This enum stores the canonical kebab-case
    form and normalises all alternative spellings via ``_missing_``.
    """
    DEFAULT = "default"
    KNAPSACK = "knapsack"
    BIN_PACKING = "bin-packing"
    BIN_PACKING_WITH_LEFTOVERS = "bin-packing-with-leftovers"
    OPEN_DIMENSION_X = "open-dimension-x"
    OPEN_DIMENSION_Y = "open-dimension-y"
    OPEN_DIMENSION_Z = "open-dimension-z"
    OPEN_DIMENSION_XY = "open-dimension-xy"
    VARIABLE_SIZED_BIN_PACKING = "variable-sized-bin-packing"
    SEQUENTIAL_ONEDIMENSIONAL_RECTANGLE_SUBPROBLEM = (
        "sequential-onedimensional-rectangle-subproblem"
    )

    @classmethod
    def _missing_(cls, value: object):
        """Accept PascalCase, abbreviations, and unknown strings."""
        if isinstance(value, str):
            canon = _OBJECTIVE_ALIASES.get(value)
            if canon is not None:
                return cls(canon)
            # Forward-compat: unknown string kept as-is
            obj = str.__new__(cls, value)
            obj._name_ = value
            obj._value_ = value
            return obj
        return None


# All C++ accepted aliases → canonical kebab-case value
_OBJECTIVE_ALIASES: dict[str, str] = {
    # PascalCase
    "Default": "default",
    "Knapsack": "knapsack",
    "KP": "knapsack",
    "BinPacking": "bin-packing",
    "BPP": "bin-packing",
    "BinPackingWithLeftovers": "bin-packing-with-leftovers",
    "BPPL": "bin-packing-with-leftovers",
    "OpenDimensionX": "open-dimension-x",
    "ODX": "open-dimension-x",
    "OpenDimensionY": "open-dimension-y",
    "ODY": "open-dimension-y",
    "OpenDimensionZ": "open-dimension-z",
    "ODZ": "open-dimension-z",
    "OpenDimensionXY": "open-dimension-xy",
    "ODXY": "open-dimension-xy",
    "VariableSizedBinPacking": "variable-sized-bin-packing",
    "VBPP": "variable-sized-bin-packing",
    "SequentialOneDimensionalRectangleSubproblem":
        "sequential-onedimensional-rectangle-subproblem",
    "BDRS": "sequential-onedimensional-rectangle-subproblem",
}


class Corner(str, enum.Enum):
    """Reference corner for leftover calculation."""
    BOTTOM_LEFT = "BottomLeft"
    BOTTOM_RIGHT = "BottomRight"
    TOP_LEFT = "TopLeft"
    TOP_RIGHT = "TopRight"

    @classmethod
    def _missing_(cls, value: object):
        """Accept abbreviated and kebab-case corner strings."""
        if isinstance(value, str):
            canon = _CORNER_ALIASES.get(value)
            if canon is not None:
                return cls(canon)
        return None


_CORNER_ALIASES: dict[str, str] = {
    "bl": "BottomLeft",
    "br": "BottomRight",
    "tl": "TopLeft",
    "tr": "TopRight",
    "bottom-left": "BottomLeft",
    "bottom-right": "BottomRight",
    "top-left": "TopLeft",
    "top-right": "TopRight",
}


# MARK: - Parameters

@dataclass
class Parameters:
    """Global problem parameters."""
    item_item_minimum_spacing: float = 0.0
    open_dimension_xy_aspect_ratio: float = -1.0
    leftover_corner: Corner = Corner.BOTTOM_LEFT
    quality_rules: list[list[int]] = field(default_factory=list)
    _extra: dict[str, Any] = field(default_factory=dict, repr=False)


# MARK: - Defect

@dataclass
class Defect:
    """A defect region inside a bin.

    Holes are stored inside the Shapely Polygon's interior rings.
    """
    shape: Polygon | MultiPolygon = field(default_factory=Polygon)
    defect_type: int = -1
    item_defect_minimum_spacing: float = 0.0
    _extra: dict[str, Any] = field(default_factory=dict, repr=False)


# MARK: - BinType

@dataclass
class BinType:
    """A bin type definition."""
    shape: Polygon = field(default_factory=Polygon)
    cost: float = -1.0
    copies: int = 1
    copies_min: int = 0
    item_bin_minimum_spacing: float = 0.0
    defects: list[Defect] = field(default_factory=list)
    _extra: dict[str, Any] = field(default_factory=dict, repr=False)


# MARK: - ItemShape

@dataclass
class ItemShape:
    """A single shape component of an item.

    Holes are stored inside the Shapely Polygon's interior rings.
    """
    shape: Polygon | MultiPolygon = field(default_factory=Polygon)
    quality_rule: int = -1
    _extra: dict[str, Any] = field(default_factory=dict, repr=False)


# MARK: - ItemType

@dataclass
class ItemType:
    """An item type definition."""
    shapes: list[ItemShape] = field(default_factory=list)
    profit: float = -1.0
    copies: int = 1
    allowed_rotations: list[tuple[float, float]] = field(
        default_factory=lambda: [(0.0, 0.0)]
    )
    allow_mirroring: bool = False
    _extra: dict[str, Any] = field(default_factory=dict, repr=False)


# MARK: - Solution types

@dataclass
class SolutionItem:
    """A placed item in the solution."""
    item_type_id: int = 0
    x: float = 0.0
    y: float = 0.0
    angle: float = 0.0
    mirror: bool = False
    shapes: list[Polygon | MultiPolygon] = field(default_factory=list)
    _extra: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class SolutionBin:
    """A bin used in the solution."""
    bin_type_id: int = 0
    copies: int = 1
    items: list[SolutionItem] = field(default_factory=list)
    shape: Optional[Polygon] = None
    defects: list[Polygon | MultiPolygon] = field(default_factory=list)
    _extra: dict[str, Any] = field(default_factory=dict, repr=False)
