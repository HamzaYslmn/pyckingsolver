"""pyckingsolver's main features, one scenario each, every one saved as a WebP in img/.

Run:  cd test && uv run python ../examples/example.py [scenario ...]
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import Point, Polygon, box

import pyckingsolver as ps

OUT = Path(__file__).resolve().parent.parent / "img"
QUARTER_TURNS = [(a, a, False) for a in (0, 90, 180, 270)]


def solve(instance, **parameters):
    """A short solve: at most 10 s, stopped 2 s after the last new solution."""
    p = ps.OptimizeParameters()
    p.time_limit, p.stall_timeout = 10, 2
    for name, value in parameters.items():
        setattr(p, name, value)
    return ps.optimize(instance, p)


# MARK: parts, each anchored at the origin


def disc(r):
    """A native circle: one exact arc for the solver."""
    return ps.build_circle(r, ps.Point(r, r))


def plate(w, h, r, inset):
    """A Shapely polygon: a rectangle with a bolt hole near each corner."""
    holes = [Point(x, y).buffer(r, 16).exterior for x in (inset, w - inset) for y in (inset, h - inset)]
    return Polygon(box(0, 0, w, h).exterior, holes)


def bracket(w, h, t):
    return ps.build_shape([(0, 0), (w, 0), (w, t), (t, t), (t, h), (0, h)])


def gusset(a):
    return ps.build_triangle(ps.Point(0, 0), ps.Point(a, 0), ps.Point(0, a))


def slot(length, r):
    """A stadium: `(x, y, 1)` is the centre of an anticlockwise arc between its neighbours."""
    return ps.build_shape([(r, 0), (r + length, 0), (r + length, r, 1), (r + length, 2 * r), (r, 2 * r), (r, r, 1)])


def arch(w, h):
    """A rectangle with a half-circle on top."""
    return ps.build_shape([(0, 0), (w, 0), (w, h), (w / 2, h, 1), (0, h)])


# MARK: rendering

SS = 2  # draw at twice the size, then downscale for smooth edges
COLORS = ["#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#76b7b2", "#edc948", "#b07aa1", "#9c755f"]
BG, SHEET, INK, DEFECT, DEFECT_FILL = "#ffffff", "#e9edf2", "#2b2f36", "#c0392b", "#f5c6c0"


def render(name, title, instance, output, x_max=None):
    """Every bin of the solution side by side (wrapping) at one scale; `x_max` crops an open-dimension bin."""
    solution, data = output.solution, instance.to_json()
    bins = []  # (solution bin position, bin outline, its defects, crop width, height)
    for k, b in enumerate(solution.bins):
        bt = data["bin_types"][b.bin_type_id]
        outline = ps.to_shapely(ps.Shape.from_json(bt))
        x0, y0, x1, y1 = outline.bounds
        defects = [ps.to_shapely(ps.Shape.from_json(d)) for d in bt.get("defects", [])]
        bins.append((k, outline, defects, (x_max or x1) - x0, y1 - y0))

    width, pad, gap, head = 1400 * SS, 16 * SS, 24 * SS, 64 * SS
    max_w, max_h = max(b[3] for b in bins), max(b[4] for b in bins)
    fit_all = (width - (len(bins) - 1) * gap) / sum(b[3] for b in bins)
    s = min(max(fit_all, (width - 2 * gap) / (3 * max_w)), width / max_w, 500 * SS / max_h)  # at most 3 a row
    rows, row, used = [], [], 0.0  # wrap the bins into rows of at most `width`
    for b in bins:
        if row and used + b[3] * s > width:
            rows.append(row)
            row, used = [], 0.0
        row.append(b)
        used += b[3] * s + gap
    rows.append(row)
    font = ImageFont.load_default(22 * SS)
    img_w = max(max(sum(b[3] * s + gap for b in r) - gap for r in rows), font.getlength(title))
    height = head + sum(max(b[4] for b in r) * s + gap for r in rows) - gap + pad
    img = Image.new("RGB", (round(img_w) + 2 * pad, round(height)), BG)
    d = ImageDraw.Draw(img)
    d.text((pad, 14 * SS), title, fill=INK, font=font)

    top = head
    for r in rows:
        left = pad
        for k, outline, defects, w, h in r:
            x0, y0, _, _ = outline.bounds

            def pts(ring):
                return [(left + (x - x0) * s, top + (y0 + h - y) * s) for x, y, *_ in ring.coords]

            sheet = outline if x_max is None else outline.intersection(box(x0, y0, x_max, y0 + h))
            d.polygon(pts(sheet.exterior), fill=SHEET, outline=INK, width=SS)
            for p in defects:
                d.polygon(pts(p.exterior), fill=DEFECT_FILL, outline=DEFECT, width=2 * SS)
            placed = [(ps.to_shapely(solution.shape_scaled(k, j)), it) for j, it in enumerate(solution.bin(k).items)]
            for p, it in sorted(placed, key=lambda pi: -pi[0].area):  # big first, small ones on top
                d.polygon(pts(p.exterior), fill=COLORS[it.item_type_id % len(COLORS)], outline=INK,
                          width=4 * SS if it.is_fixed else SS)
                for hole in p.interiors:
                    d.polygon(pts(hole), fill=SHEET, outline=INK, width=SS)
            if solution.bin(k).copies > 1:
                d.text((left + 6 * SS, top + 4 * SS), f"x{solution.bin(k).copies}", fill=INK,
                       font=ImageFont.load_default(18 * SS))
            left += w * s + gap
        top += max(b[4] for b in r) * s + gap

    img.resize((img.width // SS, img.height // SS), Image.LANCZOS).save(OUT / f"{name}.webp", quality=80)
    print(f"{name}.webp  {title}")


def summary(solution):
    return f"{solution.number_of_items()} items, {solution.number_of_bins()} bin(s), " \
           f"{100 - solution.full_waste_percentage() * 100:.0f}% used"


# MARK: items with holes: small parts nest in the plates' bolt holes; new_solution_callback counts improvements


def laser_sheet():
    ib = ps.InstanceBuilder()
    ib.set_objective(ps.Objective.Knapsack)
    ib.set_item_item_minimum_spacing(3)
    ib.add_bin_type(ps.build_rectangle(1000, 500))
    for shape, copies in ((plate(220, 140, 18, 40), 12), (bracket(160, 120, 40), 6), (gusset(120), 6), (disc(8), 80)):
        ib.add_item_type(shape, copies=copies, allowed_rotations=QUARTER_TURNS)
    instance = ib.build()

    improvements = []
    output = solve(instance, new_solution_callback=lambda o: improvements.append(o.solution.profit()))
    s = output.solution
    shapes = [ps.to_shapely(s.shape_scaled(0, j)) for j in range(len(s.bin(0).items))]
    holes = [Polygon(r) for p in shapes for r in p.interiors]
    in_holes = sum(any(h.contains(p) for h in holes) for p in shapes)
    render("laser_sheet", f"Knapsack, 3 mm spacing: {summary(s)}, {in_holes} in holes, "
           f"{len(improvements)} improvements", instance, output)


# MARK: bin packing: arc-shaped parts (build_shape) over as few sheets as possible


def bin_packing():
    ib = ps.InstanceBuilder()
    ib.set_objective(ps.Objective.BinPacking)
    ib.set_item_item_minimum_spacing(2)
    ib.add_bin_type(ps.build_rectangle(500, 300), copies=-1)  # -1: as many sheets as needed
    for shape, copies in ((slot(160, 25), 10), (arch(90, 80), 10), (gusset(110), 10)):
        ib.add_item_type(shape, copies=copies, allowed_rotations=QUARTER_TURNS)
    instance = ib.build()
    output = solve(instance)
    render("bin_packing", f"Bin packing, slots and arches from build_shape: {summary(output.solution)}",
           instance, output)


# MARK: knapsack: the sheet is too small, profit picks; then a resource caps the number of parts

NAMES = ["plate", "bracket", "gusset", "disc"]


def knapsack_builder():
    ib = ps.InstanceBuilder()
    ib.set_objective(ps.Objective.Knapsack)
    ib.set_item_item_minimum_spacing(3)
    ib.add_bin_type(ps.build_rectangle(700, 450))
    for shape, copies, profit in ((plate(220, 140, 18, 35), 6, 1), (bracket(160, 120, 40), 8, 4),
                                  (gusset(120), 8, 2), (disc(25), 12, 3)):
        ib.add_item_type(shape, copies=copies, profit=profit, allowed_rotations=QUARTER_TURNS)
    return ib


def picked(s):
    return ", ".join(f"{s.item_copies(t)} {n}" for t, n in enumerate(NAMES)) + f", profit {s.profit():.0f}"


def knapsack():
    instance = knapsack_builder().build()
    output = solve(instance)
    render("knapsack", f"Knapsack by profit: {picked(output.solution)}", instance, output)


def resource():
    ib = knapsack_builder()
    handling = ib.add_bin_type_resource(0, capacity=20)  # at most 20 parts per sheet
    for item_type_id in range(len(NAMES)):
        ib.add_resource_consumption(0, handling, item_type_id, [1])  # each copy uses 1
    instance = ib.build()
    output = solve(instance)
    render("resource", f"A resource caps the sheet at 20 parts: {picked(output.solution)}", instance, output)


# MARK: open dimension x: a 500 mm strip, its used length minimised


def strip():
    ib = ps.InstanceBuilder()
    ib.set_objective(ps.Objective.OpenDimensionX)
    ib.set_item_item_minimum_spacing(3)
    ib.add_bin_type(ps.build_rectangle(4000, 500))
    for shape, copies in ((bracket(160, 120, 40), 12), (gusset(120), 16), (plate(140, 90, 12, 22), 8)):
        ib.add_item_type(shape, copies=copies, allowed_rotations=QUARTER_TURNS)
    instance = ib.build()
    output = solve(instance)
    s = output.solution
    render("strip", f"Open dimension X: {s.number_of_items()} items on a 500 mm strip, {s.x_max():.0f} mm long",
           instance, output, x_max=s.x_max())


# MARK: variable-sized bin packing: three sheet sizes, cheapest mix


def variable_sized():
    ib = ps.InstanceBuilder()
    ib.set_objective(ps.Objective.VariableSizedBinPacking)
    ib.set_item_item_minimum_spacing(3)
    sheets = ["1000x500", "600x400", "400x250"]
    for size in sheets:
        ib.add_bin_type(ps.build_rectangle(*map(int, size.split("x"))), copies=-1)  # the cost defaults to the area
    for shape, copies in ((plate(220, 140, 18, 35), 6), (bracket(160, 120, 40), 6), (disc(40), 8)):
        ib.add_item_type(shape, copies=copies, allowed_rotations=QUARTER_TURNS)
    instance = ib.build()
    output = solve(instance)
    s = output.solution
    sizes = ", ".join(sheets[b.bin_type_id] + (f" x{b.copies}" if b.copies > 1 else "") for b in s.bins)
    render("variable_sized", f"Variable-sized bin packing: sheets {sizes}, cost {s.cost():.0f}", instance, output)


# MARK: bin packing with leftovers: the last sheet keeps its leftover in one piece


def leftovers():
    ib = ps.InstanceBuilder()
    ib.set_objective(ps.Objective.BinPackingWithLeftovers)
    ib.set_item_item_minimum_spacing(3)
    ib.set_leftover_mode(ps.LeftoverMode.BottomLeft)  # the reference corner of the leftover value
    ib.add_bin_type(ps.build_rectangle(600, 400), copies=-1)
    for shape, copies in ((bracket(160, 120, 40), 12), (gusset(120), 14), (disc(30), 14)):
        ib.add_item_type(shape, copies=copies, allowed_rotations=QUARTER_TURNS)
    instance = ib.build()
    output = solve(instance)
    s = output.solution
    render("leftovers", f"Bin packing with leftovers (BottomLeft): {summary(s)}, "
           f"leftover value {s.leftover_value_orig():.0f}", instance, output)


# MARK: defects: a rust spot and a clamp zone, items kept 10 mm clear


def defects():
    ib = ps.InstanceBuilder()
    ib.set_objective(ps.Objective.Knapsack)
    ib.set_item_item_minimum_spacing(3)
    sheet = ib.add_bin_type(ps.build_rectangle(1000, 600))
    for zone in (ps.build_circle(70, ps.Point(430, 300)), ps.build_rectangle(80, 160)):
        ib.set_item_defect_minimum_spacing(sheet, ib.add_defect(sheet, -1, zone), 10)
    ib.add_item_type(ps.build_rectangle(120, 80), copies=60, allowed_rotations=[(0, 0, False), (90, 90, False)])
    ib.add_item_type(disc(25), copies=40)
    instance = ib.build()
    output = solve(instance)
    render("defects", f"Defects with 10 mm clearance: {summary(output.solution)}", instance, output)


# MARK: polygon bin with a hole: an offcut, the hole sent as a defect, 5 mm from every edge


def polygon_bin():
    offcut = Polygon([(0, 0), (700, 0), (700, 250), (450, 450), (0, 450)],
                     [Point(300, 220).buffer(60, 16).exterior])
    ib = ps.InstanceBuilder()
    ib.set_objective(ps.Objective.Knapsack)
    ib.set_item_item_minimum_spacing(3)
    ib.add_bin_type(offcut, item_bin_minimum_spacing=5)
    ib.add_item_type(ps.build_rectangle(100, 60), copies=40, allowed_rotations=[(0, 0, False), (90, 90, False)])
    ib.add_item_type(gusset(90), copies=20, allowed_rotations=QUARTER_TURNS)
    instance = ib.build()
    output = solve(instance)
    render("polygon_bin", f"Polygon bin with a hole: {summary(output.solution)}", instance, output)


# MARK: rotations: mirrored copies and a continuous angle range


def rotations():
    ib = ps.InstanceBuilder()
    ib.set_objective(ps.Objective.Knapsack)
    ib.set_item_item_minimum_spacing(3)
    ib.add_bin_type(ps.build_rectangle(800, 400))
    hook = Polygon([(0, 0), (200, 0), (200, 40), (60, 40), (60, 140), (0, 140)])  # an L, not mirror symmetric
    ib.add_item_type(hook, copies=12, allowed_rotations=[(0, 0, False), (0, 0, True), (180, 180, False),
                                                         (180, 180, True)])
    ib.add_item_type(gusset(110), copies=12, allowed_rotations=[(0, 90, False)])  # any angle from 0 to 90
    instance = ib.build()
    output = solve(instance)
    s = output.solution
    items = s.bin(0).items
    mirrored = sum(i.mirror for i in items)
    angles = sorted({round(i.angle) for i in items if i.item_type_id == 1})
    render("rotations", f"Mirroring and a 0-90 range: {mirrored} mirrored, triangle angles {angles}",
           instance, output)


# MARK: fixed item: a holed frame placed before the search, the rest packed around and inside it


def fixed_item():
    ib = ps.InstanceBuilder()
    ib.set_objective(ps.Objective.Knapsack)
    ib.set_item_item_minimum_spacing(3)
    ib.add_bin_type(ps.build_rectangle(1000, 600))
    frame = ib.add_item_type(Polygon(box(0, 0, 400, 300).exterior, [box(60, 60, 340, 240).exterior]))
    ib.add_fixed_item(0, frame, (300, 150))
    for shape in (plate(120, 80, 10, 20), bracket(100, 80, 30), disc(20)):
        ib.add_item_type(shape, copies=30, allowed_rotations=QUARTER_TURNS)
    instance = ib.build()
    output = solve(instance)
    render("fixed_item", f"Fixed frame (thick outline): {summary(output.solution)}", instance, output)


SCENARIOS = [laser_sheet, bin_packing, knapsack, resource, strip, variable_sized, leftovers, defects, polygon_bin, rotations,
             fixed_item]

if __name__ == "__main__":
    for scenario in SCENARIOS:
        if not sys.argv[1:] or scenario.__name__ in sys.argv[1:]:
            scenario()
