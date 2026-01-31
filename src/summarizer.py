"""Summarizer using OpenRouter Kimi for experience extraction."""

import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


# Minimal prompt template - optimized for token efficiency
KIMI_PROMPT = """Extract pattern from this problem-solving session:

Task: {task}

Failed attempts:
{failures}

Successful attempt:
{success}

Return JSON only:
{{
  "pattern": "what worked that was missing from failures (5-10 words)",
  "keywords": ["relevant", "search", "terms"],
  "insight": "brief actionable insight (10-15 words)"
}}"""


def build_failures_text(failures: list[dict]) -> str:
    """Build minimal failures text."""
    if not failures:
        return "- none"
    return "\n".join(
        f"- {f['desc']} → {f['error']}"
        for f in failures
    )


def build_success_text(success: dict) -> str:
    """Build minimal success text."""
    return f"- {success['desc']}: {success['result']}"


def extract_experience(episode_data: dict) -> dict[str, Any]:
    """
    Send episode to Kimi and extract experience pattern.

    Returns dict with: pattern, keywords, insight

    Raises:
        ValueError: If OPENROUTER_API_KEY is not set
        RuntimeError: If API call fails or response parsing fails
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENROUTER_API_KEY not set in environment. "
            "Please set it in your MCP config or environment."
        )

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )

    # Build minimal prompt
    prompt = KIMI_PROMPT.format(
        task=episode_data["task"],
        failures=build_failures_text(episode_data["failures"]),
        success=build_success_text(episode_data["success"]) if episode_data["success"] else "- none"
    )

    try:
        response = client.chat.completions.create(
            model="google/gemma-3-4b-it:free",  # Free model on OpenRouter
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=200,
        )

        content = response.choices[0].message.content.strip()

        if not content:
            raise RuntimeError("Empty response from API")

        # Try to parse JSON from response
        import json
        # Handle potential markdown code blocks
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]

        return json.loads(content)

    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse API response as JSON: {e}\nResponse was: {content[:200]}")
    except Exception as e:
        raise RuntimeError(f"API call failed: {type(e).__name__}: {e}")
