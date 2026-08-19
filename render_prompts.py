"""
Render Prompt Generator — v0.1 (Phase 4, prep layer)
Converts the accurate geometry (plan + elevation) into structured prompts
for an image-gen model (Flux/SDXL via Replicate, or Rendair-style API).

Why this is a separate layer instead of "just call the API":
  - No GPU/image-gen API key is available in this sandbox, so nothing
    here has been executed against a real model — that would be faked.
  - What IS real and useful: turning room zone/area/adjacency + style
    input into per-room and per-facade prompts precise enough that a
    ControlNet-guided pass (using the SVG plan/elevation as the control
    image) stays faithful to your actual geometry instead of hallucinating
    a different room shape.

Production wiring (when you deploy):
  render_prompt = build_interior_prompt(room, style)
  image = replicate_client.run(
      "black-forest-labs/flux-canny-dev",  # or an SDXL ControlNet variant
      input={"control_image": svg_room_crop_as_png, "prompt": render_prompt}
  )
"""

from dataclasses import dataclass
from typing import List, Dict
from engine import Room, Rect


ZONE_STYLE_HINTS = {
    "public": "welcoming, well-lit, generous ceiling feel",
    "private": "calm, warm, cozy lighting",
    "service": "clean, functional, durable finishes",
}

ROOM_TYPE_HINTS = {
    "living": "sofa seating arrangement, coffee table, TV unit or feature wall",
    "dining": "dining table sized for the room, sideboard if space allows",
    "kitchen": "modular kitchen with counter, hob, chimney, overhead cabinets",
    "master bedroom": "bed with headboard wall, wardrobe, reading nook if space allows",
    "bedroom": "bed, study table, wardrobe",
    "bath": "vanity, shower/tub zone, tiled walls",
    "foyer": "console table, mirror, shoe storage",
    "entrance": "console table, mirror, shoe storage",
    "puja": "wooden temple unit, subtle uplighting",
    "utility": "washing machine, drying rack, storage shelves",
    "study": "desk, bookshelf, task lighting",
}


def _room_type_hint(room_name: str) -> str:
    name = room_name.lower()
    for key, hint in ROOM_TYPE_HINTS.items():
        if key in name:
            return hint
    return "furniture appropriate to the room's function"


def build_interior_prompt(room: Room, style: str = "contemporary Indian, warm minimal") -> str:
    zone_hint = ZONE_STYLE_HINTS.get(room.zone, "")
    type_hint = _room_type_hint(room.name)
    return (
        f"Interior render of a {room.name.lower()}, approx {room.area:.0f} sq ft, "
        f"{style} style. {zone_hint}. Include: {type_hint}. "
        f"Natural daylight, photorealistic, architectural photography, "
        f"true to the room's actual proportions — do not alter wall positions."
    )


def build_exterior_prompt(plot_w: float, plot_h: float, floors: int = 1,
                           style: str = "contemporary Indian residential, warm minimal",
                           materials: str = "textured plaster facade, wood-tone accents, large glass windows") -> str:
    return (
        f"Exterior front elevation render of a {floors}-storey house, "
        f"plot approx {plot_w:.0f}ft x {plot_h:.0f}ft, {style}. "
        f"Materials: {materials}. Photorealistic architectural visualization, "
        f"golden-hour lighting, landscaped front, true to the given elevation "
        f"outline — do not alter window/door positions or building massing."
    )


def build_all_prompts(plan, plot_w: float, plot_h: float, floors: int = 1,
                       style: str = "contemporary Indian, warm minimal") -> Dict:
    return {
        "exterior": build_exterior_prompt(plot_w, plot_h, floors, style),
        "interiors": {room.name: build_interior_prompt(room, style) for room, _ in plan},
    }


if __name__ == "__main__":
    from intake import brief_to_plan
    import json

    simulated_llm_response = json.dumps({
        "plot_w": 30, "plot_h": 40,
        "rooms": [
            {"name": "Entrance/Foyer", "area": 55, "zone": "public", "adjacent_to": ["Living Room"]},
            {"name": "Living Room", "area": 240, "zone": "public", "adjacent_to": ["Entrance/Foyer", "Dining Room"]},
            {"name": "Dining Room", "area": 140, "zone": "public", "adjacent_to": ["Living Room", "Kitchen"]},
            {"name": "Kitchen", "area": 120, "zone": "service", "adjacent_to": ["Dining Room", "Utility"]},
            {"name": "Master Bedroom", "area": 200, "zone": "private", "adjacent_to": ["Master Bath"]},
            {"name": "Master Bath", "area": 55, "zone": "private", "adjacent_to": ["Master Bedroom"]},
        ],
    })
    plan, _, _ = brief_to_plan(simulated_llm_response)
    prompts = build_all_prompts(plan, 30, 40, style="contemporary Indian, warm minimal")

    print("=== EXTERIOR PROMPT ===")
    print(prompts["exterior"], "\n")
    print("=== SAMPLE INTERIOR PROMPTS ===")
    for name, p in list(prompts["interiors"].items())[:3]:
        print(f"[{name}]\n{p}\n")

    with open("/home/claude/layout_engine/render_prompts.json", "w") as f:
        json.dump(prompts, f, indent=2)
    print("Saved render_prompts.json")
