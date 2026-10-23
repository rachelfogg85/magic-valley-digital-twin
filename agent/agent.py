"""AI agent: turns a plain-language water-scenario question into optimizer runs and
explains the results in plain language.

Uses the OpenAI Python SDK pointed at the Portkey gateway (course-provided
PORTKEY_API_KEY, model gpt-6-luna) with tool use. The agent may only state numbers
that come back from a tool call -- it never invents one.
"""
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

import tools as agent_tools

ROOT = Path(__file__).resolve().parents[1]

# Look for .env in this folder first, then one level up -- course rule.
for env_path in (ROOT / ".env", ROOT.parent / ".env"):
    if env_path.exists():
        load_dotenv(env_path)
        break

PORTKEY_BASE_URL = os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1").rstrip("/")
MODEL = "gpt-6-luna"

SYSTEM_PROMPT = """You help a Magic Valley, Idaho farmer or University of Idaho Extension agent
explore crop-planting scenarios for a water-limited growing season, using a real linear-program
optimizer and real historical field data for this study area.

Rules you must always follow:
- Call a tool before stating any number. Never invent, estimate, or recall a number from memory.
- Only state numbers that appear in a tool's result.
- Always give profit as a low-to-high range, never a single certain number.
- When a plan hits a constraint (the water limit, or a sugar beet or potato contract cap),
  mention it in plain language -- e.g. "this plan uses all the available water" or "sugar beet
  acreage is capped by the processor contract."
- Remind the user this is a decision aid, not farm advice, at least once per conversation.
- If asked something the tools can't answer, say so plainly instead of guessing.
"""


def key_is_set():
    return bool(os.getenv("PORTKEY_API_KEY", "").strip())


def build_client():
    api_key = os.getenv("PORTKEY_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("PORTKEY_API_KEY is not set.")
    return OpenAI(
        api_key=api_key,
        base_url=PORTKEY_BASE_URL,
        default_headers={"x-portkey-provider": "openai"},
    )


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "run_optimizer",
            "description": (
                "Run the crop-planning optimizer for a water scenario. Returns the "
                "recommended crop per field, total profit (low/mid/high), total water "
                "used, acres by crop, which constraints are binding, and what was "
                "actually planted that year for comparison."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "water_pct": {
                        "type": "number",
                        "description": "Percent of a normal year's water supply available, e.g. 70 for a 30% cut.",
                    },
                    "year": {
                        "type": "integer",
                        "description": "Year to plan for (used for crop-rotation history), e.g. 2021.",
                    },
                    "price_case": {
                        "type": "string",
                        "enum": ["low", "mid", "high"],
                        "description": "Which price assumption to optimize under. Default mid.",
                    },
                },
                "required": ["water_pct", "year"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_field_history",
            "description": "Get the real recorded crop history for one field across every year on record.",
            "parameters": {
                "type": "object",
                "properties": {"field_id": {"type": "string", "description": "Field id, e.g. F01."}},
                "required": ["field_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_to_actual",
            "description": (
                "Compare the optimizer's recommended plan for a water scenario to what "
                "was actually planted (and its estimated profit) in that year."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "water_pct": {"type": "number"},
                    "year": {"type": "integer"},
                },
                "required": ["water_pct", "year"],
            },
        },
    },
]

TOOL_FUNCTIONS = {
    "run_optimizer": agent_tools.run_optimizer,
    "get_field_history": agent_tools.get_field_history,
    "compare_to_actual": agent_tools.compare_to_actual,
}


def chat(messages):
    """messages: list of {"role": "user"|"assistant", "content": str} (prior turns).
    Returns (reply_text, latest_plan_or_None)."""
    client = build_client()
    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

    latest_plan = None
    for _ in range(6):  # hard cap so a tool-call loop can never run forever
        resp = client.chat.completions.create(
            model=MODEL, messages=full_messages, tools=TOOL_SCHEMAS,
            reasoning_effort="none",  # gpt-6-luna only supports function tools via
                                      # chat.completions with reasoning disabled;
                                      # the alternative is the separate /v1/responses API
        )
        msg = resp.choices[0].message
        full_messages.append(msg.model_dump(exclude_none=True))

        if not msg.tool_calls:
            return msg.content or "", latest_plan

        for call in msg.tool_calls:
            fn = TOOL_FUNCTIONS[call.function.name]
            args = json.loads(call.function.arguments or "{}")
            result = fn(**args)
            if isinstance(result, dict) and "plan" in result:
                latest_plan = result
            full_messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)}
            )

    return "I couldn't finish reasoning about that in time -- try a simpler question.", latest_plan
