"""
Web API — v0.1 (Phase 5, deployment layer)
FastAPI wrapper around the full pipeline:
  client brief --> Claude (room program) --> layout engine (per-floor plans)
  --> elevation/section --> render prompts --> (optional) image renders

Run locally:
  pip install -r requirements.txt
  uvicorn app:app --reload --port 8000

Then POST to http://localhost:8000/generate with JSON:
  {
    "brief": "3BHK independent house, 30x40 plot, north-facing entrance",
    "generate_images": false
  }

Deploy: this is a standard FastAPI app — works as-is on Render, Railway,
Fly.io (all have free tiers) or on your own LyroWeb server. Set
ANTHROPIC_API_KEY and HF_TOKEN as environment variables on whichever
platform you deploy to (not in code, not in the repo).
"""

import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from claude_client import get_room_program
from intake import parse_llm_output, INTAKE_SYSTEM_PROMPT
from engine import generate_plan, to_svg, aspect_ratio_report
from elevation import generate_elevation_svg_multi, generate_section_svg
from render_prompts import build_all_prompts

app = FastAPI(title="AI House Design Tool")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this to your LyroWeb domain before going live
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateRequest(BaseModel):
    brief: str
    generate_images: bool = False  # set True to also call Hugging Face for renders


@app.get("/")
def health():
    return {"status": "ok", "service": "ai-house-design-tool"}


@app.post("/generate")
def generate(req: GenerateRequest):
    try:
        raw_json = get_room_program(req.brief)
        parsed = parse_llm_output(raw_json)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not parse requirements: {e}")

    plot_w, plot_h = parsed["plot_w"], parsed["plot_h"]
    by_floor = {}
    for r in parsed["rooms"]:
        by_floor.setdefault(r.floor, []).append(r)

    floors_out = {}
    plans_by_floor = {}
    for floor_num, floor_rooms in sorted(by_floor.items()):
        plan = generate_plan(floor_rooms, plot_w, plot_h)
        plans_by_floor[floor_num] = plan
        floors_out[floor_num] = {
            "plan_svg": to_svg(plan, plot_w, plot_h),
            "warnings": aspect_ratio_report(plan),
            "rooms": [{"name": r.name, "area": r.area, "zone": r.zone} for r, _ in plan],
        }

    elevation_svg = generate_elevation_svg_multi(plans_by_floor, plot_w, plot_h, edge="front")
    section_svg = generate_section_svg(plans_by_floor[min(plans_by_floor)], plot_w, plot_h)
    prompts = build_all_prompts(plans_by_floor[0], plot_w, plot_h, floors=len(plans_by_floor))

    result = {
        "plot_w": plot_w,
        "plot_h": plot_h,
        "floors": floors_out,
        "elevation_svg": elevation_svg,
        "section_svg": section_svg,
        "render_prompts": prompts,
    }

    if req.generate_images:
        from render_client import render_image
        import tempfile, base64
        images = {}
        with tempfile.TemporaryDirectory() as tmp:
            ext_path = os.path.join(tmp, "exterior.png")
            if render_image(prompts["exterior"], ext_path):
                with open(ext_path, "rb") as f:
                    images["exterior"] = base64.b64encode(f.read()).decode()
        result["images_base64"] = images  # empty dict if HF call failed — check logs

    return result


# Vercel's Python runtime looks for a variable named `app` in this file's
# entrypoint (app.py) and serves it as an ASGI app directly — no extra
# handler wrapper needed for FastAPI as of the current @vercel/python runtime.
