"""Prints a short, readable report of the latest `adk eval` run of an eval set.

ADK saves every eval run as JSON in shop_helper/.adk/eval_history/. This reads
the newest one for the given eval set and prints one block per test case,
narrow enough to read on a projector.

Usage: uv run python scripts/show_results.py tests/eval/shop_helper.evalset.json
(or: make eval, make eval-one, ... print it automatically)
"""

import json
import sys
import textwrap
from datetime import datetime
from pathlib import Path

from google.adk.evaluation.eval_case import get_all_tool_calls
from google.adk.evaluation.eval_metrics import EvalStatus
from google.adk.evaluation.eval_result import EvalSetResult

HISTORY = Path("shop_helper/.adk/eval_history")
LABELS = {
    "tool_trajectory_avg_score": "trajectory",
    "final_response_match_v2": "response match",
    "rubric_based_tool_use_quality_v1": "rubric",
    "rubric_based_final_response_quality_v1": "rubric",
    "rubric_based_multi_turn_trajectory_quality_v1": "rubric",
    "multi_turn_task_success_v1": "task success",
}


def tools_text(invocation) -> str:
    calls = get_all_tool_calls(invocation.intermediate_data) if invocation else []
    return ", ".join(
        f"{c.name}({', '.join(f'{k}={v}' for k, v in (c.args or {}).items())})" for c in calls
    ) or "(no tools)"


def text_of(content) -> str:
    parts = content.parts if content and content.parts else []
    text = " ".join(p.text for p in parts if p.text).replace("**", "")
    return textwrap.shorten(text, width=240, placeholder=" ...")


def show(label: str, text: str) -> None:
    lines = textwrap.wrap(text, width=64) or [""]
    print(f"      {label:<9} {lines[0]}")
    for line in lines[1:]:
        print(f"      {'':<9} {line}")


def main(eval_set_file: str) -> None:
    eval_set_file = eval_set_file.split(":")[0]  # allow "file.json:case_id" like adk eval
    eval_set_id = json.loads(Path(eval_set_file).read_text())["eval_set_id"]
    runs = list(HISTORY.glob(f"*_{eval_set_id}_*.evalset_result.json"))
    if not runs:
        sys.exit(f"No saved results for '{eval_set_id}' yet. Run the eval first.")
    latest = max(runs, key=lambda path: path.stat().st_mtime)
    result = EvalSetResult.model_validate_json(latest.read_text())

    cases = result.eval_case_results
    passed = sum(c.final_eval_status == EvalStatus.PASSED for c in cases)
    run_at = datetime.fromtimestamp(result.creation_timestamp).strftime("%H:%M:%S")
    print(f"\n{eval_set_id}  ·  run at {run_at}  ·  {passed} passed, {len(cases) - passed} failed")
    print("-" * 76)

    for case in sorted(cases, key=lambda c: c.final_eval_status == EvalStatus.PASSED):
        ok = case.final_eval_status == EvalStatus.PASSED
        metrics = case.overall_eval_metric_results
        checks_tools = any(m.metric_name == "tool_trajectory_avg_score" for m in metrics)
        print(f"{'PASS' if ok else 'FAIL'}  {case.eval_id}")
        for metric in metrics:
            if metric.metric_name in LABELS:
                score = "n/a" if metric.score is None else f"{metric.score:.2f}"
                mark = "✓" if metric.eval_status == EvalStatus.PASSED else "✗"
                label = LABELS[metric.metric_name]
                print(f"      {mark} {label:<15} {score:>5}  (needs {metric.threshold:.2f})")
        # Show what happened in each turn of the conversation.
        for turn in case.eval_metric_result_per_invocation:
            show("user:", text_of(turn.actual_invocation.user_content))
            if turn.expected_invocation and checks_tools and not ok:
                show("expected:", tools_text(turn.expected_invocation))
            show("tools:", tools_text(turn.actual_invocation))
            show("agent:", text_of(turn.actual_invocation.final_response))
        print()
    print(f"Full JSON: {latest}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
