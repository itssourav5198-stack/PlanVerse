"""
LLM client — v0.2
Switched from Anthropic (paid) to Google Gemini (free tier).

Get a free key: https://aistudio.google.com -> "Get API key"
Set it as GEMINI_API_KEY in your environment (Vercel dashboard, or .env locally).

Function signature is unchanged (get_room_program(brief) -> raw JSON string)
so app.py and intake.py don't need any edits.
"""

import os
import google.generativeai as genai

from intake import INTAKE_SYSTEM_PROMPT

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

# Flash is fast, free-tier-friendly, and plenty for structured JSON output.
_model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    system_instruction=INTAKE_SYSTEM_PROMPT,
    generation_config={
        "response_mime_type": "application/json",  # forces valid JSON back
        "temperature": 0.2,
    },
)


def get_room_program(brief: str) -> str:
    """
    Takes the client's natural-language brief, returns raw JSON text
    (same contract as before — intake.py's parse_llm_output() still
    validates/parses it downstream).
    """
    response = _model.generate_content(brief)
    return response.text
