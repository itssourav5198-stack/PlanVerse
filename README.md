# AI House Design Tool — v1

Client brief (text) → AI-generated 2D floor plan → elevation + section →
image-gen render prompts → optional actual renders.

## Files

| File | What it does |
|---|---|
| `engine.py` | Core layout engine — takes a room list (name, area, zone, adjacency) and a plot size, produces an accurate 2D plan (doors, walls, aspect-ratio-optimized room shapes). |
| `intake.py` | Converts a natural-language client brief into the engine's Room format. Contains the LLM prompt template + a strict JSON validator. Handles multi-floor briefs. |
| `claude_client.py` | Calls the Anthropic API using `intake.py`'s prompt. Needs `ANTHROPIC_API_KEY`. |
| `elevation.py` | Extrudes a plan (or multiple floor plans) into a front elevation and a section — rule-based (door/window height conventions), not AI. |
| `render_prompts.py` | Turns a plan into per-room interior prompts + one exterior prompt for an image-gen model. |
| `render_client.py` | Calls Hugging Face's free Inference API (Flux Schnell) with those prompts to actually generate images. Needs `HF_TOKEN`. |
| `app.py` | FastAPI backend tying the whole pipeline into one `/generate` endpoint. |
| `index.html` | Minimal test frontend — a form that calls `/generate` and renders the SVGs. Swap this for your LyroWeb frontend later. |
| `requirements.txt` | Python dependencies. |
| `.gitignore` | Keeps `.env` and generated files out of your repo. |
| `.env.example` | Template for your local secrets file. |

## Local setup

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env: add your ANTHROPIC_API_KEY and HF_TOKEN — real values, never in code
uvicorn app:app --reload --port 8000
```

Open `index.html` in a browser (or serve it) — it posts to `http://localhost:8000/generate`.

## Deploying to Vercel

1. **Push to your own GitHub repo** (see step 1 below — `.gitignore` already
   protects your `.env`).
2. On [vercel.com](https://vercel.com), **Import Project** → pick your repo.
   Vercel auto-detects the Python/FastAPI app via `vercel.json` (already
   included — it also sets `maxDuration: 60` so the Claude API call has
   enough headroom).
3. In the Vercel dashboard → **Settings → Environment Variables**, add
   `ANTHROPIC_API_KEY` and `HF_TOKEN` (never in the repo).
4. Deploy. Your API will be live at `https://your-project.vercel.app/generate`.
5. **Known Vercel limitation:** the free Hobby plan caps function duration
   at 60s even with `maxDuration` set. Plain plan generation (`generate_images:
   false`) is fast (2-5s) and comfortably fits. If you turn `generate_images:
   true` on, Hugging Face's cold start can occasionally run 20s+ — usually
   still fits in 60s, but if it ever times out under load, keep image
   generation as a separate step the client triggers after the plan loads,
   rather than bundling it into the same request.
6. Point `index.html`'s `API_URL` (or your LyroWeb frontend's fetch call)
   at the deployed URL.

## Deploying elsewhere (Render / Railway / Fly.io)

1. **Push to your own GitHub repo.** `.gitignore` already excludes `.env`,
   so your keys never get committed. Create the repo, `git init`, `git add .`,
   `git commit`, push — do this yourself; don't hand out repo tokens to
   anyone, including in a chat like this one.
2. **Pick a host with a free tier for the backend:** Render, Railway, or
   Fly.io all work with this FastAPI app as-is (no code changes needed).
   Connect your GitHub repo, set the start command to
   `uvicorn app:app --host 0.0.0.0 --port $PORT`.
3. **Set environment variables on the host's dashboard** (not in the repo):
   `ANTHROPIC_API_KEY`, `HF_TOKEN`.
4. **Frontend:** either keep using `index.html` (point `API_URL` at your
   deployed backend URL), or wire the same `/generate` endpoint into your
   LyroWeb Next.js/React frontend with a `fetch` call — same shape as in
   `index.html`'s `generate()` function.
5. **Before going live:** in `app.py`, change `allow_origins=["*"]` to your
   actual domain (e.g. `["https://lyroweb.in"]`) so random sites can't call
   your API and burn your credits.

## Known limitations (be upfront with clients about these)

- Geometry isn't locked to the image-gen step — renders are stylistically
  guided by the prompts but not pixel-constrained to the plan (you chose
  this deliberately, for more creative freedom in the renders).
- No structural/code-compliance checking — this is a drafting/ideation
  speed-up, not a substitute for a licensed structural check before
  construction.
- Single-facade elevation (front) — side/rear elevations aren't generated
  yet, add by calling `generate_elevation_svg_multi` with a different `edge`.
