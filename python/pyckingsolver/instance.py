"""Instance + InstanceBuilder for the irregular packing problem."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from shapely.affinity import rotate, scale
from shapely.geometry import MultiPolygon, Polygon

from pyckingsolver.geometry import (
    ARC_RESOLUTION,
    circle_polygon,
    rectangle_polygon,
    shape_from_json,
    shape_to_json,
)
from pyckingsolver.types import (
    AllowedRotation,
    BinType,
    Defect,
    FixedItem,
    ItemShape,
    ItemType,
    LeftoverMode,
    Objective,
    Parameters,
    ShapeLike,
)


class Instance:
    """Immutable problem definition. Build via `InstanceBuilder`."""

    def __init__(self, objective: Objective, bin_types: list[BinType],
                 item_types: list[ItemType], parameters: Parameters | None = None):
        self.objective = objective
        self.bin_types = list(bin_types)
        self.item_types = list(item_types)
        self.parameters = parameters or Parameters()

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"objective": self.objective.value}
        params = _params_to_dict(self.parameters)
        if params:
            out["parameters"] = params
        out["bin_types"] = [_bin_to_dict(b) for b in self.bin_types]
        out["item_types"] = [_item_to_dict(it) for it in self.item_types]
        return out

    def to_json(self, path: str | Path | None = None) -> str:
        text = json.dumps(self.to_dict(), indent=2)
        if path is not None:
            Path(path).write_text(text, encoding="utf-8")
        return text

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Instance:
        return cls(
            objective=Objective(data["objective"]),
            bin_types=[_bin_from_dict(b) for b in data.get("bin_types", [])],
            item_types=[_item_from_dict(i) for i in data.get("item_types", [])],
            parameters=_params_from_dict(data.get("parameters", {})),
        )

    @classmethod
    def from_json(cls, path: str | Path) -> Instance:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def fits_some_bin(self, item_type_id: int) -> bool:
        """Upstream's cheap check: does the item's bounding box, at one of its discrete allowed
        angles, fit some bin's bounding box? Always True with a continuous rotation range."""
        it = self.item_types[item_type_id]
        if any(r.start_angle != r.end_angle for r in it.allowed_rotations):
            return True
        bins = [(x1 - x0, y1 - y0) for x0, y0, x1, y1 in (b.shape.bounds for b in self.bin_types)]
        for r in it.allowed_rotations:
            boxes = [rotate(scale(s.shape, -1, 1, origin=(0, 0)) if r.mirror else s.shape,
                            r.start_angle, origin=(0, 0)).bounds for s in it.shapes]
            w = max(b[2] for b in boxes) - min(b[0] for b in boxes)
            h = max(b[3] for b in boxes) - min(b[1] for b in boxes)
            if any(w - bw <= 1e-6 and h - bh <= 1e-6 for bw, bh in bins):  # rotate() float noise
                return True
        return False

    def __repr__(self) -> str:
        return (f"Instance(objective={self.objective.value!r}, "
                f"bins={len(self.bin_types)}, items={len(self.item_types)})")


class InstanceBuilder:
    """Fluent builder. Mirrors the upstream `InstanceBuilder` C++ class.

    `add_bin(...)` and `add_item(...)` accept a Shapely Polygon, a `(w, h)`
    tuple, or a numeric radius and dispatch to the right concrete adder. Tuples
    and radii are discretized to Shapely polygons.
    """

    def __init__(self, objective: Objective | str = Objective.BIN_PACKING):
        self._objective = Objective(objective)
        self._bins: list[BinType] = []
        self._items: list[ItemType] = []
        self._params = Parameters()

    def set_objective(self, objective: Objective | str) -> InstanceBuilder:
        self._objective = Objective(objective)
        return self

    def set_item_item_minimum_spacing(self, spacing: float) -> InstanceBuilder:
        self._params.item_item_minimum_spacing = spacing
        return self

    def set_open_dimension_xy_aspect_ratio(self, ratio: float) -> InstanceBuilder:
        self._params.open_dimension_xy_aspect_ratio = ratio
        return self

    def set_leftover_mode(self, mode: LeftoverMode | str) -> InstanceBuilder:
        self._params.leftover_mode = LeftoverMode(mode)
        return self

    def add_bin(self, shape, *, cost: float = -1.0, copies: int = 1,
                copies_min: int = 0, item_bin_minimum_spacing: float = 0.0) -> int:
        """Add a bin. `shape` may be a Polygon, `(w, h)` tuple, or radius (float)."""
        self._bins.append(BinType(
            shape=_coerce_shape(shape), cost=cost, copies=copies,
            copies_min=copies_min,
            item_bin_minimum_spacing=item_bin_minimum_spacing))
        return len(self._bins) - 1

    def add_bin_type(self, shape, **kw) -> int:
        return self.add_bin(shape, **kw)

    def add_bin_type_rectangle(self, width: float, height: float, **kw) -> int:
        return self.add_bin(rectangle_polygon(width, height), **kw)

    def add_bin_type_circle(self, radius: float, resolution: int = ARC_RESOLUTION,
                            **kw) -> int:
        return self.add_bin(circle_polygon(radius, resolution=resolution), **kw)

    def add_defect(self, bin_type_id: int, shape, *, defect_type: int = -1,
                   item_defect_minimum_spacing: float = 0.0) -> int:
        self._bins[bin_type_id].defects.append(Defect(
            shape=_coerce_shape(shape), defect_type=defect_type,
            item_defect_minimum_spacing=item_defect_minimum_spacing))
        return len(self._bins[bin_type_id].defects) - 1

    def add_fixed_item(self, bin_type_id: int, item_type_id: int,
                       bl_corner: tuple[float, float], *,
                       angle: float = 0.0, mirror: bool = False) -> int:
        """Pre-place an item in every bin of `bin_type_id`. Solver packs around it."""
        self._bins[bin_type_id].fixed_items.append(FixedItem(
            item_type_id=item_type_id, bl_corner=tuple(bl_corner),
            angle=angle, mirror=mirror))
        return len(self._bins[bin_type_id].fixed_items) - 1

    def add_item(self, shape, *, profit: float = -1.0, copies: int = 1,
                 copies_min: int = -1,
                 allowed_rotations: list | None = None,
                 allow_mirroring: bool = False) -> int:
        """Add an item type.

        - `shape` may be a Polygon, list of Polygons / ItemShapes (multi-shape
          item), an `(w, h)` tuple, or a numeric radius.
        - `copies_min` forces at least that many copies to be packed. KNAPSACK
          only: every other objective rejects `copies_min != copies`. Leave at
          -1 for the solver default.
        - `copies=-1` (KNAPSACK only, finite bins) means unlimited: the solver
          resolves it to as many copies as the total bin area allows.
        - `allowed_rotations` accepts:
            * None / []           -> single fixed angle 0, no mirror
            * list[float]         -> discrete angles
            * list[(s, e)]        -> continuous ranges
            * list[(s, e, mir)]   -> full triple form
            * list[AllowedRotation]
          When `allow_mirroring=True`, every base entry is duplicated with
          `mirror=True`.
        """
        if isinstance(shape, list) and shape and not _is_pair(shape[0]):
            shapes = [s if isinstance(s, ItemShape) else _item_shape(s) for s in shape]
        else:
            shapes = [_item_shape(shape)]

        rots = _normalize_rotations(allowed_rotations, allow_mirroring)
        self._items.append(ItemType(shapes=shapes, profit=profit,
                                    copies=copies, copies_min=copies_min,
                                    allowed_rotations=rots))
        return len(self._items) - 1

    def add_item_type(self, shape, **kw) -> int:
        return self.add_item(shape, **kw)

    def add_item_type_rectangle(self, width: float, height: float, **kw) -> int:
        return self.add_item(rectangle_polygon(width, height), **kw)

    def add_item_type_circle(self, radius: float, resolution: int = ARC_RESOLUTION,
                             **kw) -> int:
        circle = ItemShape(shape=circle_polygon(radius, resolution=resolution),
                           circle=(0.0, 0.0, float(radius)))
        return self.add_item([circle], **kw)

    def build(self) -> Instance:
        # Deep copy: later builder calls (add_defect, set_*) must not reach a built Instance.
        return Instance(self._objective, *copy.deepcopy((self._bins, self._items)),
                        copy.deepcopy(self._params))


# MARK: shape coercion ────────────────────────────────────────────────────────


def _item_shape(shape) -> ItemShape:
    if isinstance(shape, (int, float)):  # a radius: a native circle, exact for the solver
        return ItemShape(shape=circle_polygon(float(shape)), circle=(0.0, 0.0, float(shape)))
    return ItemShape(shape=_coerce_shape(shape))


def _coerce_shape(shape) -> ShapeLike:
    """Normalize a user shape into a Shapely Polygon/MultiPolygon.

    - `Polygon`/`MultiPolygon` -> passthrough
    - `(w, h)` tuple  -> rectangle polygon
    - numeric radius  -> circle polygon
    """
    if isinstance(shape, (Polygon, MultiPolygon)):
        return shape
    if isinstance(shape, (int, float)):
        return circle_polygon(float(shape))
    if isinstance(shape, tuple) and len(shape) == 2:
        return rectangle_polygon(float(shape[0]), float(shape[1]))
    raise TypeError(f"Cannot convert {type(shape).__name__!s} to a shape")


def _is_pair(x) -> bool:
    return isinstance(x, (tuple, list)) and len(x) in (2, 3) and all(
        isinstance(v, (int, float, bool)) for v in x)


def _normalize_rotations(rots, mirror_all: bool) -> list[AllowedRotation]:
    if not rots:
        base = [AllowedRotation()]
    else:
        base = []
        for r in rots:
            if isinstance(r, AllowedRotation):
                base.append(r)
            elif isinstance(r, (int, float)):
                base.append(AllowedRotation(float(r), float(r), False))
            elif isinstance(r, (tuple, list)):
                if len(r) == 2:
                    base.append(AllowedRotation(float(r[0]), float(r[1]), False))
                elif len(r) == 3:
                    base.append(AllowedRotation(float(r[0]), float(r[1]), bool(r[2])))
                else:
                    raise ValueError(f"Bad rotation entry: {r!r}")
            else:
                raise TypeError(f"Bad rotation entry: {r!r}")
    if mirror_all:
        base = base + [AllowedRotation(r.start_angle, r.end_angle, True)
                       for r in base if not r.mirror]
    return base


# MARK: parameters ────────────────────────────────────────────────────────────


def _params_to_dict(p: Parameters) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if p.item_item_minimum_spacing:
        out["item_item_minimum_spacing"] = p.item_item_minimum_spacing
    if p.open_dimension_xy_aspect_ratio > 0:
        out["open_dimension_xy_aspect_ratio"] = p.open_dimension_xy_aspect_ratio
    if p.leftover_mode != LeftoverMode.BOTTOM_LEFT:
        out["leftover_mode"] = p.leftover_mode.value
    return out


def _params_from_dict(jp: dict) -> Parameters:
    return Parameters(
        item_item_minimum_spacing=jp.get("item_item_minimum_spacing", 0.0),
        open_dimension_xy_aspect_ratio=jp.get("open_dimension_xy_aspect_ratio", -1.0),
        leftover_mode=LeftoverMode(jp["leftover_mode"]) if "leftover_mode" in jp
        else LeftoverMode.BOTTOM_LEFT,
    )


# MARK: bins ──────────────────────────────────────────────────────────────────


def _bin_to_dict(b: BinType) -> dict[str, Any]:
    # The C++ reads a bin as a plain Shape and drops "holes": send each hole as a defect instead.
    holes = [Defect(shape=Polygon(r), item_defect_minimum_spacing=b.item_bin_minimum_spacing)
             for r in getattr(b.shape, "interiors", ())]
    out = shape_to_json(Polygon(b.shape.exterior) if holes else b.shape)
    if b.cost != -1.0:
        out["cost"] = b.cost
    if b.copies != 1:
        out["copies"] = b.copies
    if b.copies_min:
        out["copies_min"] = b.copies_min
    if b.item_bin_minimum_spacing:
        out["item_bin_minimum_spacing"] = b.item_bin_minimum_spacing
    if b.defects or holes:
        out["defects"] = [_defect_to_dict(d) for d in b.defects + holes]
    if b.fixed_items:
        out["fixed_items"] = [_fixed_to_dict(f) for f in b.fixed_items]
    return out


def _bin_from_dict(jb: dict) -> BinType:
    return BinType(
        shape=shape_from_json(jb),
        cost=jb.get("cost", -1.0),
        copies=jb.get("copies", 1),
        copies_min=jb.get("copies_min", 0),
        item_bin_minimum_spacing=jb.get("item_bin_minimum_spacing", 0.0),
        defects=[_defect_from_dict(d) for d in jb.get("defects", [])],
        fixed_items=[_fixed_from_dict(f) for f in jb.get("fixed_items", [])],
    )


def _fixed_to_dict(f: FixedItem) -> dict[str, Any]:
    return {
        "item_type_id": f.item_type_id,
        "bl_corner": {"x": f.bl_corner[0], "y": f.bl_corner[1]},
        "angle": f.angle,
        "mirror": f.mirror,
    }


def _fixed_from_dict(jf: dict) -> FixedItem:
    bl = jf.get("bl_corner", {})
    return FixedItem(
        item_type_id=jf.get("item_type_id", 0),
        bl_corner=(bl.get("x", 0.0), bl.get("y", 0.0)),
        angle=jf.get("angle", 0.0),
        mirror=jf.get("mirror", False),
    )


def _defect_to_dict(d: Defect) -> dict[str, Any]:
    out = shape_to_json(d.shape)
    if d.defect_type != -1:
        out["defect_type"] = d.defect_type
    if d.item_defect_minimum_spacing:
        out["item_defect_minimum_spacing"] = d.item_defect_minimum_spacing
    return out


def _defect_from_dict(jd: dict) -> Defect:
    return Defect(
        shape=shape_from_json(jd),
        defect_type=jd.get("defect_type", -1),
        item_defect_minimum_spacing=jd.get("item_defect_minimum_spacing", 0.0),
    )


# MARK: items ─────────────────────────────────────────────────────────────────


def _item_to_dict(it: ItemType) -> dict[str, Any]:
    parts = [j for s in it.shapes for j in _item_shape_to_json(s)]
    out = parts[0] if len(parts) == 1 else {"shapes": parts}
    if it.profit != -1.0:
        out["profit"] = it.profit
    if it.copies != 1:
        out["copies"] = it.copies
    if it.copies_min >= 0:
        out["copies_min"] = it.copies_min
    if it.allowed_rotations != [AllowedRotation()]:
        out["allowed_rotations"] = [_rot_to_dict(r) for r in it.allowed_rotations]
    return out


def _item_shape_to_json(s: ItemShape) -> list[dict[str, Any]]:
    if s.circle:
        x, y, r = s.circle
        return [{"type": "circle", "x": x, "y": y, "radius": r}]
    # The JSON has no multipolygon: each part of a MultiPolygon becomes one shape of the item.
    return [shape_to_json(g) for g in getattr(s.shape, "geoms", [s.shape])]


def _item_shape_from_json(js: dict) -> ItemShape:
    circle = (js.get("x", 0.0), js.get("y", 0.0), js["radius"]) if js.get("type") == "circle" else None
    return ItemShape(shape=shape_from_json(js), circle=circle)


def _item_from_dict(ji: dict) -> ItemType:
    shapes = [_item_shape_from_json(js) for js in ji.get("shapes", [ji])]
    rots = _normalize_rotations([_rot_from_dict(r) for r in ji.get("allowed_rotations", [])],
                                bool(ji.get("allow_mirroring")))
    return ItemType(shapes=shapes, profit=ji.get("profit", -1.0),
                    copies=ji.get("copies", 1),
                    copies_min=ji.get("copies_min", -1),
                    allowed_rotations=rots)


def _rot_to_dict(r: AllowedRotation) -> dict[str, Any]:
    return {"start": r.start_angle, "end": r.end_angle, "mirror": r.mirror}


def _rot_from_dict(jr: dict) -> AllowedRotation:
    return AllowedRotation(
        start_angle=jr.get("start", jr.get("start_angle", 0.0)),
        end_angle=jr.get("end", jr.get("end_angle", 0.0)),
        mirror=jr.get("mirror", False),
    )
# __PYCK_END__
