# Settings (project, region, agent ID) come from shop_helper/.env
-include shop_helper/.env
export

AGENT := shop_helper
CASE ?= ineligible_return

.PHONY: web web-prod eval eval-one eval-sim eval-regressions deploy traffic to-evalcase

web:  ## Chat with the agent locally (Trace + Eval tabs) at http://localhost:8000
	uv run adk web --port 8000 .

web-prod:  ## Demo 3 (UI route): adk web showing the DEPLOYED agent's sessions
	uv run adk web --port 8000 \
		--session_service_uri=agentengine://projects/$(GOOGLE_CLOUD_PROJECT)/locations/$(AGENT_RUNTIME_REGION)/reasoningEngines/$(AGENT_ENGINE_ID) .

# The eval targets print a short report (scripts/show_results.py).
# The full adk eval output, with every detail, goes to eval.log.
eval:  ## Demo 1: static eval set (tool trajectory, response match, rubric)
	@echo "Running adk eval (about 2 min, full output in eval.log) ..."
	@uv run adk eval $(AGENT) tests/eval/shop_helper.evalset.json --print_detailed_results > eval.log 2>&1 || (tail -n 30 eval.log; exit 1)
	@uv run python scripts/show_results.py tests/eval/shop_helper.evalset.json

eval-one:  ## Demo 1 (fast, usually <1 min): one case only. make eval-one [CASE=ineligible_return]
	@echo "Running adk eval on $(CASE) (full output in eval.log) ..."
	@uv run adk eval $(AGENT) tests/eval/shop_helper.evalset.json:$(CASE) --print_detailed_results > eval.log 2>&1 || (tail -n 30 eval.log; exit 1)
	@uv run python scripts/show_results.py tests/eval/shop_helper.evalset.json

eval-sim:  ## Demo 1 bonus: user simulation eval set (about 3.5 min)
	@echo "Running adk eval with simulated users (about 3.5 min, full output in eval.log) ..."
	@uv run adk eval $(AGENT) tests/eval/sim/shop_helper_sim.evalset.json --print_detailed_results > eval.log 2>&1 || (tail -n 30 eval.log; exit 1)
	@uv run python scripts/show_results.py tests/eval/sim/shop_helper_sim.evalset.json

eval-regressions:  ## Demo 3: eval cases captured from production sessions
	@echo "Running adk eval on the regressions (full output in eval.log) ..."
	@uv run adk eval $(AGENT) tests/eval/regressions/regressions.evalset.json --print_detailed_results > eval.log 2>&1 || (tail -n 30 eval.log; exit 1)
	@uv run python scripts/show_results.py tests/eval/regressions/regressions.evalset.json

deploy:  ## Demo 2: deploy to Agent Runtime with Cloud Trace (updates in place once AGENT_ENGINE_ID is set)
	uv run adk deploy agent_engine \
		--project=$(GOOGLE_CLOUD_PROJECT) \
		--region=$(AGENT_RUNTIME_REGION) \
		--display_name="ShopHelper" \
		--otel_to_cloud \
		$(if $(AGENT_ENGINE_ID),--agent_engine_id=$(AGENT_ENGINE_ID)) \
		$(AGENT)

traffic:  ## Demo 2: send ~15 requests to the deployed agent
	uv run python scripts/send_traffic.py

to-evalcase:  ## Demo 3: make to-evalcase SESSION=<session id>
	uv run python scripts/session_to_evalcase.py $(SESSION)
