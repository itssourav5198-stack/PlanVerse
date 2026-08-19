"""
AI House Layout Engine — v0.1
Takes a room program (name, area, zone, adjacency) + plot dimensions
and generates a proportion-accurate 2D floor plan as SVG.

Algorithm: adjacency-ordered squarified treemap.
 1. Rooms are grouped by zone (public/private/service) and ordered
    within each zone by adjacency strength (simple greedy chain),
    so rooms that should sit next to each other end up next to
    each other in the treemap ordering.
 2. The ordered list is packed into the plot rectangle using the
    "squarified treemap" algorithm (Bruls, Huizing, van Wijk),
    which keeps each room's aspect ratio close to square and its
    area proportional to the requested sq ft.
 3. Output is an SVG floor plan with walls, room labels and areas.

This is a real, runnable v0.1 — not a mockup. Next iterations should
add: explicit adjacency edges as corridor/door constraints, minimum
dimension constraints per room type, and door placement.
"""

from dataclasses import dataclass, field
from typing import List, Tuple
import json


@dataclass
class Room:
    name: str
    area: float          # sq ft
    zone: str = "public"  # public | private | service
    adjacent_to: List[str] = field(default_factory=list)
    floor: int = 0        # 0 = ground floor, 1 = first floor, etc.


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float


def order_rooms(rooms: List[Room]) -> List[Room]:
    """Group by zone, then greedily chain rooms with shared adjacency
    so related rooms land next to each other in the treemap order."""
    zones = {}
    for r in rooms:
        zones.setdefault(r.zone, []).append(r)

    ordered: List[Room] = []
    for zone_rooms in zones.values():
        remaining = zone_rooms[:]
        chain = [remaining.pop(0)]
        while remaining:
            last = chain[-1]
            # find a remaining room adjacent to the last placed room
            match = next(
                (r for r in remaining if r.name in last.adjacent_to
                 or last.name in r.adjacent_to),
                None,
            )
            if match is None:
                match = remaining[0]
            chain.append(match)
            remaining.remove(match)
        ordered.extend(chain)
    return ordered


def _worst_ratio(row: List[float], length: float) -> float:
    total = sum(row)
    side = total / length
    return max(max(a / (side * side), (side * side) / a) for a in row)


def squarify(areas: List[float], x: float, y: float, w: float, h: float) -> List[Rect]:
    """Classic squarified treemap. areas must sum to w*h."""
    rects: List[Rect] = []
    areas = areas[:]

    def layout_row(row, x, y, w, h, vertical):
        total = sum(row)
        if vertical:
            row_w = total / h
            cy = y
            for a in row:
                rh = a / row_w
                rects.append(Rect(x, cy, row_w, rh))
                cy += rh
            return x + row_w, y, w - row_w, h
        else:
            row_h = total / w
            cx = x
            for a in row:
                rw = a / row_h
                rects.append(Rect(cx, y, rw, row_h))
                cx += rw
            return x, y + row_h, w, h - row_h

    while areas:
        length = min(w, h)
        vertical = h <= w
        row = [areas[0]]
        i = 1
        while i < len(areas):
            trial = row + [areas[i]]
            if _worst_ratio(trial, length) <= _worst_ratio(row, length):
                row = trial
                i += 1
            else:
                break
        x, y, w, h = layout_row(row, x, y, w, h, vertical)
        areas = areas[i:]

    return rects


def _apply_squarify(ordered: List[Room], plot_w: float, plot_h: float):
    total_area = sum(r.area for r in ordered)
    plot_area = plot_w * plot_h
    scale = plot_area / total_area
    scaled_areas = [r.area * scale for r in ordered]
    rects = squarify(scaled_areas, 0, 0, plot_w, plot_h)
    return list(zip(ordered, rects))


def _worst_room_ratio(plan) -> float:
    return max(max(rect.w, rect.h) / min(rect.w, rect.h) for _, rect in plan)


def optimize_order(ordered: List[Room], plot_w: float, plot_h: float,
                    max_iters: int = 300, seed: int = 42) -> List[Room]:
    """Hill-climb over room orderings (swapping two rooms within the same
    zone, so zoning/adjacency grouping from order_rooms is preserved) to
    minimize the worst per-room aspect ratio the squarify pass produces.
    Cheap and effective: the treemap's shapes depend heavily on packing
    order, so most bad-aspect-ratio rooms can be fixed without touching
    the geometry algorithm itself."""
    import random
    rng = random.Random(seed)

    best = ordered[:]
    best_score = _worst_room_ratio(_apply_squarify(best, plot_w, plot_h))

    zone_indices = {}
    for idx, r in enumerate(ordered):
        zone_indices.setdefault(r.zone, []).append(idx)
    swappable_zones = [idxs for idxs in zone_indices.values() if len(idxs) > 1]
    if not swappable_zones:
        return best

    current, current_score = best[:], best_score
    for _ in range(max_iters):
        zone_idxs = rng.choice(swappable_zones)
        i, j = rng.sample(zone_idxs, 2)
        candidate = current[:]
        candidate[i], candidate[j] = candidate[j], candidate[i]
        score = _worst_room_ratio(_apply_squarify(candidate, plot_w, plot_h))
        if score <= current_score:  # accept equal/better moves, keeps search moving
            current, current_score = candidate, score
            if score < best_score:
                best, best_score = candidate, score
        if best_score <= 2.0:  # good enough, stop early
            break
    return best


def generate_plan(rooms: List[Room], plot_w: float, plot_h: float, optimize: bool = True):
    ordered = order_rooms(rooms)
    if optimize:
        ordered = optimize_order(ordered, plot_w, plot_h)
    return _apply_squarify(ordered, plot_w, plot_h)


def find_shared_edges(plan, tol: float = 0.05, min_overlap: float = 1.5):
    """Return list of (i, j, orientation, seg_start, seg_end, coord) for every
    pair of rooms that physically share a wall segment long enough for a door
    (min_overlap in ft, default 1.5ft so doors don't land in corners)."""
    edges = []
    n = len(plan)
    for i in range(n):
        r1, rect1 = plan[i]
        for j in range(i + 1, n):
            r2, rect2 = plan[j]
            # vertical shared boundary (one room's right edge = other's left edge)
            if abs((rect1.x + rect1.w) - rect2.x) < tol or abs((rect2.x + rect2.w) - rect1.x) < tol:
                y0, y1 = max(rect1.y, rect2.y), min(rect1.y + rect1.h, rect2.y + rect2.h)
                if y1 - y0 >= min_overlap:
                    xc = rect1.x + rect1.w if abs((rect1.x + rect1.w) - rect2.x) < tol else rect2.x + rect2.w
                    edges.append((i, j, "vertical", y0, y1, xc))
            # horizontal shared boundary
            if abs((rect1.y + rect1.h) - rect2.y) < tol or abs((rect2.y + rect2.h) - rect1.y) < tol:
                x0, x1 = max(rect1.x, rect2.x), min(rect1.x + rect1.w, rect2.x + rect2.w)
                if x1 - x0 >= min_overlap:
                    yc = rect1.y + rect1.h if abs((rect1.y + rect1.h) - rect2.y) < tol else rect2.y + rect2.h
                    edges.append((i, j, "horizontal", x0, x1, yc))
    return edges


def compute_doors(plan, door_width: float = 3.0):
    """Place a door on every shared edge where the two rooms requested
    adjacency to each other. Returns list of dicts: orientation, center x/y."""
    edges = find_shared_edges(plan)
    doors = []
    for i, j, orient, s0, s1, coord in edges:
        r1, _ = plan[i]
        r2, _ = plan[j]
        wants_door = r2.name in r1.adjacent_to or r1.name in r2.adjacent_to
        if not wants_door:
            continue
        mid = (s0 + s1) / 2
        if orient == "vertical":
            doors.append({"orient": "vertical", "x": coord, "y0": mid - door_width / 2, "y1": mid + door_width / 2})
        else:
            doors.append({"orient": "horizontal", "y": coord, "x0": mid - door_width / 2, "x1": mid + door_width / 2})
    return doors


def find_entrance_door(plan, plot_w: float, plot_h: float, door_width: float = 3.0):
    """Find a room whose name suggests the main entry and touches the plot
    boundary; return an exterior door spec for it (or None)."""
    tol = 0.05
    for room, rect in plan:
        if not any(k in room.name.lower() for k in ("entrance", "foyer", "porch")):
            continue
        if abs(rect.y) < tol:  # touches top exterior wall
            mx = rect.x + rect.w / 2
            return {"orient": "horizontal", "y": 0, "x0": mx - door_width / 2, "x1": mx + door_width / 2}
        if abs(rect.x) < tol:  # touches left exterior wall
            my = rect.y + rect.h / 2
            return {"orient": "vertical", "x": 0, "y0": my - door_width / 2, "y1": my + door_width / 2}
        if abs(rect.x + rect.w - plot_w) < tol:
            my = rect.y + rect.h / 2
            return {"orient": "vertical", "x": plot_w, "y0": my - door_width / 2, "y1": my + door_width / 2}
        if abs(rect.y + rect.h - plot_h) < tol:
            mx = rect.x + rect.w / 2
            return {"orient": "horizontal", "y": plot_h, "x0": mx - door_width / 2, "x1": mx + door_width / 2}
    return None


def aspect_ratio_report(plan, max_ratio: float = 2.2):
    """Flag rooms whose long-side:short-side ratio exceeds max_ratio —
    these read as awkward corridors rather than usable rooms."""
    warnings = []
    for room, rect in plan:
        ratio = max(rect.w, rect.h) / min(rect.w, rect.h)
        if ratio > max_ratio:
            warnings.append(f"{room.name}: {rect.w:.1f}ft x {rect.h:.1f}ft (ratio {ratio:.1f}:1 — reshape or resize)")
    return warnings


def to_svg(plan, plot_w: float, plot_h: float, scale_px: float = 20,
           wall_thickness_ft: float = 0.4) -> str:
    W, H = plot_w * scale_px, plot_h * scale_px
    wt = wall_thickness_ft * scale_px
    zone_colors = {"public": "#EAD9C9", "private": "#CFE1D8", "service": "#D9D2E9"}
    doors = compute_doors(plan) + ([d] if (d := find_entrance_door(plan, plot_w, plot_h)) else [])

    parts = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
              f'font-family="Helvetica, Arial, sans-serif">']
    # exterior shell
    parts.append(f'<rect x="0" y="0" width="{W}" height="{H}" fill="#FAF7F2" '
                  f'stroke="#1A1A1A" stroke-width="{wt:.1f}"/>')
    # room fills + interior walls
    for room, rect in plan:
        x, y, w, h = rect.x * scale_px, rect.y * scale_px, rect.w * scale_px, rect.h * scale_px
        fill = zone_colors.get(room.zone, "#EEE")
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                      f'fill="{fill}" stroke="#1A1A1A" stroke-width="{wt*0.6:.1f}"/>')
        cx, cy = x + w / 2, y + h / 2
        parts.append(f'<text x="{cx:.1f}" y="{cy - 6:.1f}" font-size="13" '
                      f'text-anchor="middle" fill="#222" font-weight="600">{room.name}</text>')
        parts.append(f'<text x="{cx:.1f}" y="{cy + 10:.1f}" font-size="10.5" '
                      f'text-anchor="middle" fill="#555">{room.area:.0f} sq ft</text>')
    # doors: white gap across the wall + quarter-circle swing arc
    for d in doors:
        if d["orient"] == "vertical":
            x = d["x"] * scale_px
            y0, y1 = d["y0"] * scale_px, d["y1"] * scale_px
            parts.append(f'<line x1="{x:.1f}" y1="{y0:.1f}" x2="{x:.1f}" y2="{y1:.1f}" '
                          f'stroke="#FAF7F2" stroke-width="{wt+2:.1f}"/>')
            r = y1 - y0
            parts.append(f'<path d="M {x:.1f} {y0:.1f} A {r:.1f} {r:.1f} 0 0 1 {x+r:.1f} {y1:.1f}" '
                          f'fill="none" stroke="#999" stroke-width="1"/>')
        else:
            y = d["y"] * scale_px
            x0, x1 = d["x0"] * scale_px, d["x1"] * scale_px
            parts.append(f'<line x1="{x0:.1f}" y1="{y:.1f}" x2="{x1:.1f}" y2="{y:.1f}" '
                          f'stroke="#FAF7F2" stroke-width="{wt+2:.1f}"/>')
            r = x1 - x0
            parts.append(f'<path d="M {x0:.1f} {y:.1f} A {r:.1f} {r:.1f} 0 0 1 {x1:.1f} {y-r:.1f}" '
                          f'fill="none" stroke="#999" stroke-width="1"/>')
    parts.append('</svg>')
    return "\n".join(parts)


if __name__ == "__main__":
    rooms = [
        Room("Living Room", 220, "public", ["Dining Room", "Entrance"]),
        Room("Dining Room", 130, "public", ["Living Room", "Kitchen"]),
        Room("Kitchen", 110, "service", ["Dining Room"]),
        Room("Entrance/Foyer", 60, "public", ["Living Room"]),
        Room("Master Bedroom", 180, "private", ["Master Bath"]),
        Room("Master Bath", 60, "private", ["Master Bedroom"]),
        Room("Bedroom 2", 130, "private", []),
        Room("Common Bath", 45, "private", []),
        Room("Utility", 40, "service", ["Kitchen"]),
    ]
    plan = generate_plan(rooms, plot_w=30, plot_h=25)
    svg = to_svg(plan, 30, 25)
    with open("/home/claude/layout_engine/sample_plan.svg", "w") as f:
        f.write(svg)
    with open("/home/claude/layout_engine/sample_plan.json", "w") as f:
        json.dump([{"name": r.name, "area": r.area, "zone": r.zone,
                    "x": rect.x, "y": rect.y, "w": rect.w, "h": rect.h}
                   for r, rect in plan], f, indent=2)
    print("Generated sample_plan.svg and sample_plan.json")
    warnings = aspect_ratio_report(plan)
    if warnings:
        print("Aspect-ratio warnings:")
        for w in warnings:
            print(" -", w)
    else:
        print("All rooms within acceptable aspect ratio.")
