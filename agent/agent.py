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
optimizer and real historical field data for this study area. The real crop-history and rotation
data only covers 2008-2021 -- never assume "this year" means the current real-world year; if the
user doesn't name a year in that range, ask which year they mean, or suggest 2021 (the drought
year this project centers on) as a starting point.

Rules you must always follow:
- Every fact and number you state must be real, not invented. Call a tool before stating any
  number -- never invent, estimate, guess, or recall one from memory or general knowledge about
  farming. Only state numbers and facts that appear in a tool's result for THIS conversation.
- Cite a source for the numbers you give, using the "sources" or "source" field in the tool
  result (e.g. "per USDA NASS 2023" or "Idaho State Tax Commission, 2018-2022"). Don't state a
  number without naming where it came from.
- Always give profit as a low-to-high range, never a single certain number.
- When a plan hits a constraint (the water limit, or a sugar beet or potato contract cap),
  mention it in plain language -- e.g. "this plan uses all the available water" or "sugar beet
  acreage is capped by the processor contract."
- If the user's question is ambiguous or missing something a tool needs (which year, which
  field, how much less water), ask a short clarifying question instead of guessing a value.
- If a tool returns an error, has no data for the request, or the question is outside what the
  tools can answer (e.g. soil conditions, weather forecasts, equipment, labor, markets), say so
  plainly -- do not fill the gap with an invented or general-knowledge answer.
- Remind the user this is a decision aid, not farm advice, at least once per conversation.
- Summarize a plan by acres per crop (e.g. "Beans: 1,979 acres, Potatoes: 600 acres"), the way
  the results panel on screen does. Never list or enumerate individual field IDs (there are over
  100 fields) unless the user asks about one specific field by name. A wall of field IDs is not a
  useful answer.
- Keep answers short: a few sentences, not a long report. State the headline numbers (profit
  range, water used, acres by crop, binding constraints) plainly and skip restating the question.
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

# Keys whose values should read as whole numbers in the agent's reply, matching the
# on-screen panel (which shows no decimals). Profit keys round to whole dollars;
# the rest (acres, water) round to whole units.
_WHOLE_NUMBER_KEYS = {
    "profit_low", "profit_mid", "profit_high",
    "actual_profit_low", "actual_profit_mid", "actual_profit_high",
    "optimized_profit_mid", "profit_gap_mid",
    "total_water_af", "water_limit_af",
    "acres_by_crop", "actual_acres_by_crop", "optimized_acres_by_crop",
}


def _round_for_display(value):
    if isinstance(value, dict):
        return {k: _round_for_display(v) for k, v in value.items()}
    if isinstance(value, (int, float)):
        return round(value)
    return value


def _round_result(result):
    return {k: (_round_for_display(v) if k in _WHOLE_NUMBER_KEYS else v) for k, v in result.items()}


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
                # The model only needs the summary to explain a plan in words (acres
                # by crop, profit, water); the field-by-field map (100+ entries) is
                # for the map/panel UI only, via latest_plan -- sending it to the
                # model as well just invites it to enumerate field IDs in prose, and
                # costs real tokens for no benefit (see report.html's Tokenomics).
                result = {k: v for k, v in result.items() if k != "plan"}
            full_messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": json.dumps(_round_result(result))}
            )

    return "I couldn't finish reasoning about that in time -- try a simpler question.", latest_plan
