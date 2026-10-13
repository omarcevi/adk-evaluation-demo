"""Turns a session from the DEPLOYED agent into a regression eval case.

It uses the same ADK helper as the "Add current session" button in `adk web`,
but reads the session from Agent Runtime instead of your laptop.

Usage: uv run python scripts/session_to_evalcase.py <SESSION_ID> [USER_ID]
   or: make to-evalcase SESSION=<SESSION_ID>
"""

import asyncio
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from google.adk.cli.utils.evals import convert_session_to_eval_invocations
from google.adk.evaluation.eval_case import EvalCase, SessionInput, get_all_tool_calls
from google.adk.evaluation.eval_set import EvalSet
from google.adk.sessions import VertexAiSessionService

load_dotenv("shop_helper/.env")
AGENT_ENGINE_ID = os.environ["AGENT_ENGINE_ID"]
EVAL_SET_FILE = Path("tests/eval/regressions/regressions.evalset.json")


async def main(session_id: str, user_id: str) -> None:
    # 1. Fetch the production session (all its events) from Agent Runtime.
    session_service = VertexAiSessionService(
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.environ["AGENT_RUNTIME_REGION"],
        agent_engine_id=AGENT_ENGINE_ID,
    )
    session = await session_service.get_session(
        app_name=AGENT_ENGINE_ID, user_id=user_id, session_id=session_id
    )
    if session is None:
        sys.exit(f"Session {session_id} not found.")

    # 2. Convert its events into eval invocations: user message, tool calls, answer.
    new_case = EvalCase(
        eval_id=f"session_{session_id}",
        conversation=convert_session_to_eval_invocations(session),
        session_input=SessionInput(app_name="shop_helper", user_id=user_id, state={}),
        creation_timestamp=time.time(),
    )

    # 3. Add it to the regressions eval set (replacing an older copy of the same case).
    cases = []
    if EVAL_SET_FILE.exists():
        cases = EvalSet.model_validate_json(EVAL_SET_FILE.read_text()).eval_cases
    cases = [case for case in cases if case.eval_id != new_case.eval_id] + [new_case]
    eval_set = EvalSet(
        eval_set_id="regressions",
        name="Regressions found in production",
        eval_cases=cases,
    )
    EVAL_SET_FILE.write_text(eval_set.model_dump_json(indent=2, exclude_none=True))

    for invocation in new_case.conversation:
        tools = [f"{t.name}({t.args})" for t in get_all_tool_calls(invocation.intermediate_data)]
        print(f"user : {invocation.user_content.parts[0].text}")
        print(f"tools: {', '.join(tools) or '-'}")
        print(f"agent: {invocation.final_response.parts[0].text.strip()}")
    print(f"\nAdded eval case '{new_case.eval_id}' to {EVAL_SET_FILE}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "demo_user"))
