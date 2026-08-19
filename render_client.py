"""
Image Render Client — v0.1 (Phase 4, actual API call)
Wires render_prompts.py's prompts to Hugging Face's Inference API
(Flux Schnell by default — fast + free-tier friendly).

SETUP (do this once, outside any chat):
  1. Create a file named .env next to this script (never commit it):
       HF_TOKEN=hf_your_new_token_here
  2. pip install requests python-dotenv --break-system-packages

Usage:
  python3 render_client.py            # renders the exterior + first 2 interiors as a smoke test

The token is NEVER hardcoded here — it's read from the environment at
runtime via os.environ, loaded from .env locally by python-dotenv.
"""

import os
import base64
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # fine if dotenv isn't installed; env var can be set another way

HF_MODEL_URL = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell"


def render_image(prompt: str, out_path: str) -> bool:
    """Call Hugging Face Inference API with a prompt, save the PNG to out_path.
    Returns True on success, False on failure (prints the reason either way)."""
    token = os.environ.get("HF_TOKEN")
    if not token:
        print("ERROR: HF_TOKEN not set. Put it in a .env file (HF_TOKEN=hf_...) "
              "next to this script, never in code or chat.")
        return False

    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = requests.post(HF_MODEL_URL, headers=headers,
                              json={"inputs": prompt}, timeout=60)
    except requests.RequestException as e:
        print(f"ERROR: request failed — {e}")
        return False

    if resp.status_code == 503:
        print("Model is loading on Hugging Face's side (cold start) — retry in ~20s.")
        return False
    if resp.status_code == 401:
        print("ERROR: 401 unauthorized — token missing/invalid/revoked. "
              "Generate a fresh one and update .env.")
        return False
    if resp.status_code != 200:
        print(f"ERROR: HF API returned {resp.status_code} — {resp.text[:200]}")
        return False

    with open(out_path, "wb") as f:
        f.write(resp.content)
    print(f"Saved {out_path}")
    return True


if __name__ == "__main__":
    from render_prompts import build_all_prompts
    from intake import brief_to_plans
    import json

    simulated_llm_response = json.dumps({
        "plot_w": 30, "plot_h": 40,
        "rooms": [
            {"name": "Living Room", "area": 250, "zone": "public", "floor": 0, "adjacent_to": []},
            {"name": "Master Bedroom", "area": 210, "zone": "private", "floor": 1, "adjacent_to": []},
        ],
    })
    results, plot_w, plot_h = brief_to_plans(simulated_llm_response)
    ground_plan = results[0]["plan"]
    prompts = build_all_prompts(ground_plan, plot_w, plot_h, floors=len(results))

    os.makedirs("/home/claude/layout_engine/renders", exist_ok=True)
    render_image(prompts["exterior"], "/home/claude/layout_engine/renders/exterior.png")
    for name, prompt in prompts["interiors"].items():
        safe_name = name.lower().replace(" ", "_").replace("/", "_")
        render_image(prompt, f"/home/claude/layout_engine/renders/{safe_name}.png")
