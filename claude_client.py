"""
Claude API Client — v0.1
Calls Anthropic's API with INTAKE_SYSTEM_PROMPT + the client's brief,
returns the raw JSON text for intake.parse_llm_output() to validate.

SETUP: put ANTHROPIC_API_KEY=sk-ant-... in your .env file (never in code).
"""

import os
import json
import requests
from intake import INTAKE_SYSTEM_PROMPT, build_user_prompt

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-6"


def get_room_program(client_brief: str) -> str:
    """Calls Claude with the intake system prompt, returns raw JSON text
    (still needs intake.parse_llm_output() to validate/convert)."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. Put it in your .env file, never in code or chat."
        )

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": MODEL,
        "max_tokens": 2000,
        "system": INTAKE_SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": build_user_prompt(client_brief)}],
    }
    resp = requests.post(ANTHROPIC_URL, headers=headers, json=payload, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"Claude API error {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    text = "".join(block["text"] for block in data["content"] if block["type"] == "text")
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


if __name__ == "__main__":
    brief = "2BHK apartment layout, 20ft x 30ft, south-facing entrance."
    try:
        result = get_room_program(brief)
        print(result)
    except RuntimeError as e:
        print(e)
