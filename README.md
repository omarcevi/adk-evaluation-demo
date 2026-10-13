# ShopHelper: AI Agents in Production demo

A tiny order-support agent built with Google ADK, used to show three things live:

1. **Evaluation**: an eval set catches a bug in the agent's instructions.
2. **Observability**: the deployed agent sends traces to Cloud Trace (a slow tool, a failing tool).
3. **Closing the loop**: a bad production session becomes a regression eval case, then gets fixed.

```
shop_helper/agent.py          the agent: 1 LlmAgent, 4 tools, in-memory mock data
tests/eval/                   static eval set + test_config.json         (make eval / eval-one)
tests/eval/sim/               user simulation eval set + test_config.json (make eval-sim)
tests/eval/regressions/       cases captured from production              (make eval-regressions)
scripts/send_traffic.py       ~15 requests to the DEPLOYED agent           (make traffic)
scripts/session_to_evalcase.py  production session -> eval case            (make to-evalcase)
scripts/show_results.py       short, readable report of the latest eval run
```

Versions: `google-adk` 2.11.0, Python 3.12, model `gemini-3.8-flash`.

## Git tags (the demo states)

| Tag | Agent state |
|---|---|
| `demo1-start` | Instruction never says "check eligibility first", so it creates returns for ineligible orders. |
| `demo1-fixed` | Two-line instruction fix. Still has the order ID bug (`#1001` is "not found"). This is what gets deployed. |
| `demo3-fixed` | Order IDs are normalized in the tool, plus the captured regression case. |

`git diff demo1-start demo1-fixed` and `git diff demo1-fixed demo3-fixed -- shop_helper` show only the fix.

## One-time setup

```bash
uv sync
gcloud auth login
gcloud auth application-default login
cp shop_helper/.env.example shop_helper/.env   # then set GOOGLE_CLOUD_PROJECT
```

Google Cloud project needs:
- Billing enabled.
- APIs: Vertex AI (`aiplatform.googleapis.com`), Cloud Resource Manager, Cloud Build, Cloud Storage,
  Cloud Trace (`cloudtrace.googleapis.com`), Telemetry (`telemetry.googleapis.com`), Cloud Logging.
- Your user: Owner, or at least Vertex AI User + Cloud Trace User + Logs Viewer.

Why there are two locations in `.env`: Gemini 3 models are only served from the `global` endpoint,
while Agent Runtime runs in a region. The agent pins `location="global"` on its model, and
`make deploy` uses `AGENT_RUNTIME_REGION`.

## Before the stream (about 20 minutes)

1. **Deploy the fixed agent** (about 4 minutes):
   ```bash
   git checkout demo1-fixed
   make deploy
   ```
   The first time, copy the number at the end of `Deployed to Agent Platform: .../reasoningEngines/<ID>`
   into `shop_helper/.env` as `AGENT_ENGINE_ID=<ID>`. Later `make deploy` runs update that same agent.
2. **Send traffic** (about 3 minutes): `make traffic`. It prints every session ID. Note one session
   that asked about `#1001` (the agent answers "I couldn't find an order...").
3. **Check the console**: open Trace Explorer (see Demo 2) and confirm the traces are there.
   They usually show up within a minute or two.
4. **Warm up the evals and keep a backup of the output** (about 5 minutes):
   ```bash
   git checkout demo1-start && make eval 2>&1 | tee ~/eval-demo1-start.txt
   git checkout demo1-fixed && make eval 2>&1 | tee ~/eval-demo1-fixed.txt
   ```
5. **Start clean**: `rm -f tests/eval/regressions/regressions.evalset.json && git checkout demo1-start`.
   Open tabs: your editor, a terminal, Trace Explorer, and the Agent Runtime page.

## Reading eval results

Every `make eval*` target prints a short report, one block per test case with failures first.
The full `adk eval` output is in `eval.log`. ADK also saves every run as JSON in
`shop_helper/.adk/eval_history/`. To print the latest run again, use
`uv run python scripts/show_results.py tests/eval/shop_helper.evalset.json`.

## Demo 1: Evaluation

```bash
git checkout demo1-start
```

1. Show `shop_helper/agent.py`: 4 plain Python functions as tools, the instruction, mock orders.
   Point at the return rule: it just says "call create_return_request".
2. Optional live chat: `make web`, open http://localhost:8000, select `shop_helper`, and type
   `I want to return order ORD-1004, the jacket doesn't fit.` The agent happily creates a return
   for a 45-day-old order. Show the **Trace** tab next to the chat.
3. Show `tests/eval/shop_helper.evalset.json` (one user message, expected tool calls, reference
   answer) and `tests/eval/test_config.json` (three criteria):
   - `tool_trajectory_avg_score`: the exact tool calls, threshold 1.0
   - `final_response_match_v2`: an LLM judge compares the answer to the reference
   - `rubric_based_tool_use_quality_v1`: an LLM judge checks a plain-English rule
4. `make eval` (about 2 minutes). **Audience sees:** `3 passed, 2 failed`.
   Short on time? `make eval-one` runs only `ineligible_return` (usually under a minute) and shows the same failure.
   Failing cases come first. For `ineligible_return`:
   - ✗ trajectory, ✗ response match, ✗ rubric
   - `expected: check_return_eligibility(...)` but `tools: create_return_request(...)`
   - `agent:` "...your return ID is RET-1004"
   `eligible_return` fails too, on trajectory and rubric: the outcome happened to be right, but it skipped the required check.
5. Fix it: `git diff demo1-start demo1-fixed` (two lines in the instruction), then `git checkout demo1-fixed`.
6. `make eval` again. **Audience sees:** `5 passed, 0 failed`.
   (Or `make eval-one` again: `ineligible_return` now passes.)
7. "Look what else is possible": show `tests/eval/sim/shop_helper_sim.evalset.json`. There is no
   script, only a goal and a persona (an impatient customer who writes under 12 words).
   `make eval-sim` takes about 3.5 minutes. Start it and talk over it, or show the backup output.
   Criteria: `multi_turn_task_success_v1` and `rubric_based_multi_turn_trajectory_quality_v1`.

## Demo 2: Deploy + tracing

Already deployed before the stream. Show how:

1. `Makefile`, target `deploy`: `adk deploy agent_engine ... --otel_to_cloud`. The CLI still says
   "agent_engine"; the product is now called Agent Runtime.
2. `shop_helper/.env`: `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=true`. Without it, `--otel_to_cloud`
   hides tool arguments and responses in spans (a good default for real user data).
3. Console, Agent Runtime: https://console.cloud.google.com/vertex-ai/agents/agent-engines
   Click **ShopHelper** to show that it's a managed deployment (there's a Playground tab to chat).
4. Console, **Trace Explorer**: https://console.cloud.google.com/traces/explorer
   - Set the time range to cover the `make traffic` run.
   - Filter by span name `execute_tool get_shipping_eta`. Every one takes about **2.5 s**.
   - Open one of those traces. **Audience sees the waterfall:** `invoke_agent shop_helper` →
     `call_llm` / `generate_content gemini-3.8-flash` → `execute_tool get_shipping_eta`, and the
     tool is clearly the biggest bar. "This is how you find your slow dependency."
5. Optional: run `make traffic` live (about 3 minutes) and refresh Trace Explorer.

## Demo 3: Closing the loop

Still on `demo1-fixed`.

1. Trace Explorer: filter on spans with **error** status (or span name `execute_tool get_order_status`).
   Open a trace for `#1001`. **Audience sees:**
   - The `execute_tool get_order_status` span is marked as an error, with `error.type = TOOL_ERROR`.
   - Its attributes: `gcp.vertex.agent.tool_call_args = {"order_id": "1001"}` and
     `gcp.vertex.agent.tool_response = {"error": "Order 1001 not found."}`.
   - The order exists. The customer just wrote `#1001` instead of `ORD-1001`.
2. Click the root span `invoke_agent shop_helper` and copy `gen_ai.conversation.id`. That's the session ID.
3. Turn the production session into an eval case:
   ```bash
   make to-evalcase SESSION=<session id>
   ```
   It prints the conversation and writes `tests/eval/regressions/regressions.evalset.json`, in the
   same EvalSet format `adk web` uses. Show `tests/eval/regressions/test_config.json`: a rubric says
   "finds the order, never says it doesn't exist". The captured answer is the *bad* one, so we judge
   with a rubric instead of comparing to it.
4. `make eval-regressions`. **Audience sees:** `0 passed, 1 failed`, and the agent saying it couldn't find order #1001.
5. Fix the tool:
   ```bash
   git checkout demo3-fixed -- shop_helper/agent.py
   git diff --cached
   ```
   `_clean_order_id` now turns `#1001`, `1001` and `ord-1001` into `ORD-1001`.
6. `make eval-regressions`. **Audience sees:** `1 passed, 0 failed`, and the agent now gives the order status. Optional: `make eval` still passes 5/5.
7. Closing line: this case now runs on every change, so this bug can't come back silently.

**Built-in alternative (no script):** `make web-prod` opens `adk web` connected to the deployed
agent's sessions. Click the **User ID** at the top and set it to `demo_user`. Pick the session,
open the **Eval** tab, create an eval set, then click **Add current session**. It's saved as
`shop_helper/<eval set>.evalset.json`. Run it with:
`uv run adk eval shop_helper shop_helper/<eval set>.evalset.json --config_file_path tests/eval/regressions/test_config.json`.
`make to-evalcase` uses the same ADK helper (`convert_session_to_eval_invocations`).

## If something breaks live

- **Wrong state / messed-up files:** `git checkout -f <tag>` (`demo1-start`, `demo1-fixed` or
  `demo3-fixed`). `-f` throws away local changes, including a captured regressions file in the way.
- **Session capture fails** (wrong ID, or the session belongs to another user): `git checkout -f demo3-fixed`
  includes a pre-captured `#1001` case, so you can still run `make eval-regressions`.
  For sessions from other users: `uv run python scripts/session_to_evalcase.py <session id> <user id>`.
- **`429 RESOURCE_EXHAUSTED` / eval hangs while retrying:** Gemini quota is busy. Wait 30 seconds and
  rerun, or show the backup output from `~/eval-*.txt`. Never run two evals at the same time.
- **Eval is too slow on stream:** `make eval-one` runs only `ineligible_return` (usually under a minute).
  Any other case works too, e.g. `make eval-one CASE=shipping_eta`.
- **No traces in Trace Explorer:** widen the time range (last 1 day) and check the project picker.
- **Deploy fails live:** don't deploy live. It takes about 4 minutes. Use the pre-deployed agent.
- **`make traffic` prints `error: RESOURCE_EXHAUSTED`:** quota again, so just rerun it.

## After the stream

Agent Runtime bills while the agent exists. Delete it from the Agent Runtime console page, or:

```bash
uv run python -c "import vertexai; vertexai.Client(project='<project>', location='us-central1').agent_engines.delete(name='projects/<project>/locations/us-central1/reasoningEngines/<ID>', force=True)"
```
