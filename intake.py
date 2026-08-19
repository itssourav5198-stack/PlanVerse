"""
Requirement Intake Layer — v0.1
Bridges Phase 1 (client's natural-language brief) to Phase 2 (the layout
engine's Room objects).

How it works in production:
  client brief (text) --> LLM call (Claude, via your backend/n8n) using
  INTAKE_SYSTEM_PROMPT below --> LLM returns JSON matching ROOM_SCHEMA -->
  parse_llm_output() validates + converts it into engine.Room objects -->
  engine.generate_plan() runs as before.

This file is API-agnostic on purpose: swap in any LLM call (Claude API,
n8n HTTP node, etc.) as long as it's given INTAKE_SYSTEM_PROMPT and the
client brief, and its output is passed to parse_llm_output().
"""

import json
from typing import List, Dict, Any
from engine import Room, generate_plan, to_svg, aspect_ratio_report


INTAKE_SYSTEM_PROMPT = """You are a residential space-planning assistant.
Convert the client's house brief into a JSON room program.

Rules:
- Output ONLY a JSON object, no prose, no markdown fences.
- Schema:
  {
    "plot_w": <number, ft>,
    "plot_h": <number, ft>,
    "rooms": [
      {
        "name": <string>,
        "area": <number, sq ft>,
        "zone": "public" | "private" | "service",
        "floor": <integer, 0 = ground floor, 1 = first floor, ...>,
        "adjacent_to": [<room names this room should share a wall with, same floor only>]
      }, ...
    ]
  }
- zone guide: living/dining/foyer/entrance = public; bedrooms/bathrooms
  attached to bedrooms = private; kitchen/utility/store/servant = service.
- If the client wants more than one floor (duplex, G+1, G+2), split rooms
  across floors sensibly: public/service rooms usually ground floor,
  bedrooms usually upper floors, unless the client specifies otherwise.
  Set each room's "floor" field accordingly (default 0 if not mentioned).
  Sum of room areas PER FLOOR should land within ~85-95% of plot_w * plot_h.
- Standard Indian residential area guide (sq ft) unless client overrides:
  living room 180-260, dining 100-150, kitchen 90-130, master bedroom
  160-220, other bedrooms 120-160, attached bath 40-60, common bath 35-50,
  foyer 40-70, utility 30-50, puja room 20-35, study 90-120, balcony 40-80.
- Sum of room areas should land within ~85-95% of plot_w * plot_h
  (leaving room for circulation/walls) unless client specifies floors > 1,
  in which case divide the program sensibly across floors and only return
  one floor's rooms per call.
- Only include adjacent_to pairs that make functional sense (kitchen near
  dining, attached bath near its bedroom, foyer near living room, etc.)."""


def build_user_prompt(client_brief: str) -> str:
    return f"Client brief:\n{client_brief}\n\nReturn the JSON room program now."


def parse_llm_output(llm_json_text: str) -> Dict[str, Any]:
    """Validate and convert raw LLM JSON text into (plot_w, plot_h, [Room])."""
    data = json.loads(llm_json_text)

    required_top = {"plot_w", "plot_h", "rooms"}
    missing = required_top - data.keys()
    if missing:
        raise ValueError(f"LLM output missing keys: {missing}")

    rooms = []
    valid_zones = {"public", "private", "service"}
    for i, r in enumerate(data["rooms"]):
        for key in ("name", "area", "zone"):
            if key not in r:
                raise ValueError(f"room[{i}] missing '{key}': {r}")
        if r["zone"] not in valid_zones:
            raise ValueError(f"room[{i}] has invalid zone '{r['zone']}'")
        if r["area"] <= 0:
            raise ValueError(f"room[{i}] '{r['name']}' has non-positive area")
        rooms.append(Room(
            name=r["name"],
            area=float(r["area"]),
            zone=r["zone"],
            adjacent_to=r.get("adjacent_to", []),
            floor=int(r.get("floor", 0)),
        ))

    plot_area = data["plot_w"] * data["plot_h"]
    by_floor = {}
    for r in rooms:
        by_floor.setdefault(r.floor, []).append(r)
    for floor_num, floor_rooms in by_floor.items():
        total = sum(r.area for r in floor_rooms)
        if total > plot_area * 1.05:
            raise ValueError(
                f"Floor {floor_num} room areas ({total:.0f} sq ft) exceed plot area "
                f"({plot_area:.0f} sq ft) — brief needs a bigger plot or fewer rooms on that floor."
            )

    return {"plot_w": data["plot_w"], "plot_h": data["plot_h"], "rooms": rooms}


def brief_to_plans(llm_json_text: str):
    """Full pipeline: validated LLM JSON -> one generated plan PER FLOOR.
    Returns dict: {floor_num: {"plan": plan, "svg": svg, "warnings": warnings}}."""
    parsed = parse_llm_output(llm_json_text)
    by_floor = {}
    for r in parsed["rooms"]:
        by_floor.setdefault(r.floor, []).append(r)

    results = {}
    for floor_num, floor_rooms in sorted(by_floor.items()):
        plan = generate_plan(floor_rooms, parsed["plot_w"], parsed["plot_h"])
        svg = to_svg(plan, parsed["plot_w"], parsed["plot_h"])
        warnings = aspect_ratio_report(plan)
        results[floor_num] = {"plan": plan, "svg": svg, "warnings": warnings}
    return results, parsed["plot_w"], parsed["plot_h"]


# kept for backward compatibility with single-floor callers (elevation.py, render_prompts.py demos)
def brief_to_plan(llm_json_text: str):
    results, plot_w, plot_h = brief_to_plans(llm_json_text)
    ground = results[min(results.keys())]
    return ground["plan"], ground["svg"], ground["warnings"]


if __name__ == "__main__":
    # Demo: this is what the LLM (Claude) would return for a client brief like
    # "3BHK independent house, 30ft x 40ft plot, north-facing entrance,
    #  kitchen should be in the south-east corner (vastu), need a small puja room."
    demo_client_brief = (
        "3BHK duplex (G+1), 30ft x 40ft plot, north-facing entrance. Ground floor: "
        "living, dining, kitchen, one guest bedroom. First floor: master bedroom "
        "with attached bath, two more bedrooms, common bath, small study."
    )
    print("=== SYSTEM PROMPT (send this + brief to Claude API) ===")
    print(INTAKE_SYSTEM_PROMPT[:200] + " ...\n")
    print("=== CLIENT BRIEF ===")
    print(demo_client_brief, "\n")

    # Simulated LLM response — in production this string comes back from
    # the actual Claude API call using INTAKE_SYSTEM_PROMPT above.
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
    print("=== RESULT ===")
    for floor_num, r in results.items():
        label = "Ground Floor" if floor_num == 0 else f"Floor {floor_num}"
        with open(f"/home/claude/layout_engine/brief_demo_plan_floor{floor_num}.svg", "w") as f:
            f.write(r["svg"])
        print(f"{label}: {len(r['plan'])} rooms — warnings: {r['warnings'] if r['warnings'] else 'none'}")
