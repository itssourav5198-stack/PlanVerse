"""
Elevation + Section Generator — v0.1 (Phase 3)
Extrudes the 2D plan (Phase 2 output) into:
  - a front elevation (exterior wall face, with door/window openings
    derived from which rooms touch that exterior edge)
  - a vertical section (a cut through the building showing floor
    height, slab thickness, and a simple parapet/roof line)

Pure rule-based geometry — no AI here on purpose (heights, sill levels,
lintel heights are architectural conventions, not something worth
generating stochastically). AI/image-gen comes in at Phase 4, applied
ON TOP of these accurate outlines for material + style rendering.
"""

from dataclasses import dataclass
from typing import List, Tuple
from engine import Room, Rect


# Indian residential defaults (ft) — override per project as needed
FLOOR_HEIGHT = 10.0
SILL_HEIGHT = 2.5        # window sill from floor
WINDOW_HEIGHT = 4.5
DOOR_HEIGHT = 7.0
SLAB_THICKNESS = 0.5
PARAPET_HEIGHT = 3.0


def _rooms_on_edge(plan, edge: str, plot_w: float, plot_h: float, tol: float = 0.05):
    """Rooms whose rect touches the given exterior edge ('front'=y=0,
    'back'=y=plot_h, 'left'=x=0, 'right'=x=plot_w), sorted along that edge."""
    hits = []
    for room, rect in plan:
        if edge == "front" and abs(rect.y) < tol:
            hits.append((room, rect.x, rect.w))
        elif edge == "back" and abs(rect.y + rect.h - plot_h) < tol:
            hits.append((room, rect.x, rect.w))
        elif edge == "left" and abs(rect.x) < tol:
            hits.append((room, rect.y, rect.h))
        elif edge == "right" and abs(rect.x + rect.w - plot_w) < tol:
            hits.append((room, rect.y, rect.h))
    return sorted(hits, key=lambda h: h[1])


def generate_elevation_svg(plan, plot_w: float, plot_h: float, edge: str = "front",
                            floors: int = 1, floor_height: float = FLOOR_HEIGHT,
                            scale_px: float = 20) -> str:
    span = plot_w if edge in ("front", "back") else plot_h
    building_h = floors * floor_height + PARAPET_HEIGHT
    W, H = span * scale_px, building_h * scale_px
    ground_y = H  # svg y grows downward; ground line is at the bottom

    def fy(height_from_ground):  # convert a real height above ground to svg y
        return ground_y - height_from_ground * scale_px

    parts = [f'<svg viewBox="0 0 {W} {H+20}" xmlns="http://www.w3.org/2000/svg" '
              f'font-family="Helvetica, Arial, sans-serif">']
    # ground line
    parts.append(f'<line x1="0" y1="{ground_y:.1f}" x2="{W}" y2="{ground_y:.1f}" '
                  f'stroke="#1A1A1A" stroke-width="3"/>')

    for floor_i in range(floors):
        floor_base = floor_i * floor_height
        # exterior wall block for this floor
        parts.append(f'<rect x="0" y="{fy(floor_base+floor_height):.1f}" width="{W}" '
                      f'height="{floor_height*scale_px:.1f}" fill="#F2ECE3" '
                      f'stroke="#1A1A1A" stroke-width="2.5"/>')

        hits = _rooms_on_edge(plan, edge, plot_w, plot_h)
        for room, pos, size in hits:
            cx = (pos + size / 2) * scale_px
            is_entry = any(k in room.name.lower() for k in ("entrance", "foyer", "porch")) and floor_i == 0
            if is_entry:
                w = min(size * 0.5, 3.5) * scale_px
                h = DOOR_HEIGHT * scale_px
                x = cx - w / 2
                y = fy(floor_base + DOOR_HEIGHT)
                parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                              f'fill="#8B5E34" stroke="#1A1A1A" stroke-width="1.5"/>')
            else:
                w = min(size * 0.45, 4.5) * scale_px
                h = WINDOW_HEIGHT * scale_px
                x = cx - w / 2
                y = fy(floor_base + SILL_HEIGHT + WINDOW_HEIGHT)
                parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                              f'fill="#AEDFF0" stroke="#1A1A1A" stroke-width="1.5"/>')
                # mullion line
                parts.append(f'<line x1="{cx:.1f}" y1="{y:.1f}" x2="{cx:.1f}" y2="{y+h:.1f}" '
                              f'stroke="#1A1A1A" stroke-width="1"/>')

    # parapet
    parts.append(f'<rect x="0" y="{fy(floors*floor_height+PARAPET_HEIGHT):.1f}" width="{W}" '
                  f'height="{PARAPET_HEIGHT*scale_px:.1f}" fill="#E4DDD1" '
                  f'stroke="#1A1A1A" stroke-width="2"/>')
    parts.append('</svg>')
    return "\n".join(parts)


def generate_section_svg(plan, plot_w: float, plot_h: float, cut_axis: str = "vertical",
                          cut_position: float = None, floors: int = 1,
                          floor_height: float = FLOOR_HEIGHT, scale_px: float = 20) -> str:
    """cut_axis='vertical' cuts along a fixed x, showing a slice through y
    (i.e. a section looking along the x-axis); cut_position defaults to
    the plot's midline."""
    if cut_position is None:
        cut_position = (plot_w if cut_axis == "vertical" else plot_h) / 2

    span = plot_h if cut_axis == "vertical" else plot_w
    building_h = floors * floor_height + PARAPET_HEIGHT + SLAB_THICKNESS * (floors + 1)
    W, H = span * scale_px, building_h * scale_px
    ground_y = H

    def fy(height_from_ground):
        return ground_y - height_from_ground * scale_px

    parts = [f'<svg viewBox="0 0 {W} {H+20}" xmlns="http://www.w3.org/2000/svg" '
              f'font-family="Helvetica, Arial, sans-serif">']
    parts.append(f'<line x1="0" y1="{ground_y:.1f}" x2="{W}" y2="{ground_y:.1f}" '
                  f'stroke="#1A1A1A" stroke-width="3"/>')

    # rooms the cut line passes through, at ground floor plan, to label spans
    cut_hits = []
    for room, rect in plan:
        if cut_axis == "vertical":
            if rect.x <= cut_position <= rect.x + rect.w:
                cut_hits.append((room, rect.y, rect.h))
        else:
            if rect.y <= cut_position <= rect.y + rect.h:
                cut_hits.append((room, rect.x, rect.w))
    cut_hits.sort(key=lambda h: h[1])

    level = 0.0
    for floor_i in range(floors):
        # slab
        parts.append(f'<rect x="0" y="{fy(level+SLAB_THICKNESS):.1f}" width="{W}" '
                      f'height="{SLAB_THICKNESS*scale_px:.1f}" fill="#BBB" '
                      f'stroke="#1A1A1A" stroke-width="1.5"/>')
        level += SLAB_THICKNESS
        # room space for this floor (hollow, showing internal height)
        room_top = level + floor_height
        parts.append(f'<rect x="0" y="{fy(room_top):.1f}" width="{W}" '
                      f'height="{floor_height*scale_px:.1f}" fill="none" '
                      f'stroke="#1A1A1A" stroke-width="2.5"/>')
        for room, pos, size in cut_hits:
            x = pos * scale_px
            w = size * scale_px
            y = fy(room_top)
            h = floor_height * scale_px
            parts.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x:.1f}" y2="{y+h:.1f}" '
                          f'stroke="#1A1A1A" stroke-width="1.5"/>')
            parts.append(f'<text x="{x+w/2:.1f}" y="{y+h/2:.1f}" font-size="11" '
                          f'text-anchor="middle" fill="#333">{room.name}</text>')
        level = room_top

    # roof slab + parapet
    parts.append(f'<rect x="0" y="{fy(level+SLAB_THICKNESS):.1f}" width="{W}" '
                  f'height="{SLAB_THICKNESS*scale_px:.1f}" fill="#BBB" '
                  f'stroke="#1A1A1A" stroke-width="1.5"/>')
    level += SLAB_THICKNESS
    parts.append(f'<rect x="0" y="{fy(level+PARAPET_HEIGHT):.1f}" width="{6*scale_px:.1f}" '
                  f'height="{PARAPET_HEIGHT*scale_px:.1f}" fill="#E4DDD1" '
                  f'stroke="#1A1A1A" stroke-width="2"/>')
    parts.append(f'<rect x="{W-6*scale_px:.1f}" y="{fy(level+PARAPET_HEIGHT):.1f}" width="{6*scale_px:.1f}" '
                  f'height="{PARAPET_HEIGHT*scale_px:.1f}" fill="#E4DDD1" '
                  f'stroke="#1A1A1A" stroke-width="2"/>')
    parts.append('</svg>')
    return "\n".join(parts)


def generate_elevation_svg_multi(plans_by_floor: dict, plot_w: float, plot_h: float,
                                  edge: str = "front", floor_height: float = FLOOR_HEIGHT,
                                  scale_px: float = 20) -> str:
    """Like generate_elevation_svg, but takes {floor_num: plan} so each
    floor's windows/doors come from THAT floor's actual room layout,
    not copy-pasted from the ground floor."""
    floors = sorted(plans_by_floor.keys())
    span = plot_w if edge in ("front", "back") else plot_h
    building_h = len(floors) * floor_height + PARAPET_HEIGHT
    W, H = span * scale_px, building_h * scale_px
    ground_y = H

    def fy(height_from_ground):
        return ground_y - height_from_ground * scale_px

    parts = [f'<svg viewBox="0 0 {W} {H+20}" xmlns="http://www.w3.org/2000/svg" '
              f'font-family="Helvetica, Arial, sans-serif">']
    parts.append(f'<line x1="0" y1="{ground_y:.1f}" x2="{W}" y2="{ground_y:.1f}" '
                  f'stroke="#1A1A1A" stroke-width="3"/>')

    for floor_i, floor_num in enumerate(floors):
        floor_base = floor_i * floor_height
        plan = plans_by_floor[floor_num]
        parts.append(f'<rect x="0" y="{fy(floor_base+floor_height):.1f}" width="{W}" '
                      f'height="{floor_height*scale_px:.1f}" fill="#F2ECE3" '
                      f'stroke="#1A1A1A" stroke-width="2.5"/>')
        # floor separator line (skip on ground)
        if floor_i > 0:
            parts.append(f'<line x1="0" y1="{fy(floor_base):.1f}" x2="{W}" y2="{fy(floor_base):.1f}" '
                          f'stroke="#1A1A1A" stroke-width="1.5"/>')

        hits = _rooms_on_edge(plan, edge, plot_w, plot_h)
        for room, pos, size in hits:
            cx = (pos + size / 2) * scale_px
            is_entry = (floor_num == min(floors) and
                        any(k in room.name.lower() for k in ("entrance", "foyer", "porch")))
            if is_entry:
                w = min(size * 0.5, 3.5) * scale_px
                h = DOOR_HEIGHT * scale_px
                x, y = cx - w / 2, fy(floor_base + DOOR_HEIGHT)
                parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                              f'fill="#8B5E34" stroke="#1A1A1A" stroke-width="1.5"/>')
            else:
                w = min(size * 0.45, 4.5) * scale_px
                h = WINDOW_HEIGHT * scale_px
                x, y = cx - w / 2, fy(floor_base + SILL_HEIGHT + WINDOW_HEIGHT)
                parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                              f'fill="#AEDFF0" stroke="#1A1A1A" stroke-width="1.5"/>')
                parts.append(f'<line x1="{cx:.1f}" y1="{y:.1f}" x2="{cx:.1f}" y2="{y+h:.1f}" '
                              f'stroke="#1A1A1A" stroke-width="1"/>')

    parts.append(f'<rect x="0" y="{fy(len(floors)*floor_height+PARAPET_HEIGHT):.1f}" width="{W}" '
                  f'height="{PARAPET_HEIGHT*scale_px:.1f}" fill="#E4DDD1" '
                  f'stroke="#1A1A1A" stroke-width="2"/>')
    parts.append('</svg>')
    return "\n".join(parts)


if __name__ == "__main__":
    from intake import brief_to_plans
    import json

    simulated_llm_response = json.dumps({
        "plot_w": 30, "plot_h": 40,
        "rooms": [
            {"name": "Entrance/Foyer", "area": 55, "zone": "public", "floor": 0, "adjacent_to": ["Living Room"]},
            {"name": "Living Room", "area": 250, "zone": "public", "floor": 0, "adjacent_to": ["Entrance/Foyer", "Dining Room"]},
            {"name": "Dining Room", "area": 150, "zone": "public", "floor": 0, "adjacent_to": ["Living Room", "Kitchen"]},
            {"name": "Kitchen", "area": 120, "zone": "service", "floor": 0, "adjacent_to": ["Dining Room"]},
            {"name": "Guest Bedroom", "area": 160, "zone": "private", "floor": 0, "adjacent_to": []},
            {"name": "Guest Bath", "area": 45, "zone": "private", "floor": 0, "adjacent_to": ["Guest Bedroom"]},
            {"name": "Master Bedroom", "area": 210, "zone": "private", "floor": 1, "adjacent_to": ["Master Bath"]},
            {"name": "Master Bath", "area": 55, "zone": "private", "floor": 1, "adjacent_to": ["Master Bedroom"]},
            {"name": "Bedroom 2", "area": 150, "zone": "private", "floor": 1, "adjacent_to": ["Common Bath"]},
            {"name": "Bedroom 3", "area": 140, "zone": "private", "floor": 1, "adjacent_to": ["Common Bath"]},
            {"name": "Common Bath", "area": 45, "zone": "private", "floor": 1, "adjacent_to": ["Bedroom 2", "Bedroom 3"]},
            {"name": "Study", "area": 100, "zone": "public", "floor": 1, "adjacent_to": []},
        ],
    })
    results, plot_w, plot_h = brief_to_plans(simulated_llm_response)
    plans_by_floor = {fn: r["plan"] for fn, r in results.items()}

    elevation_svg = generate_elevation_svg_multi(plans_by_floor, plot_w, plot_h, edge="front")
    with open("/home/claude/layout_engine/elevation_front_gplus1.svg", "w") as f:
        f.write(elevation_svg)
    print(f"Generated 2-floor (G+1) elevation with {len(plans_by_floor)} floors.")
