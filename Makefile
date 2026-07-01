.PHONY: run replay drift evolution verify health query compat

# ==========================================
# 1. THE REVENUE ENGINE (PRODUCTION)
# ==========================================

# Run the live data extraction pipeline
run:
	python run_controller.py

# ==========================================
# 2. THE OBSERVABILITY PLATFORM (VERIFICATION)
# ==========================================

# Run the deterministic replay for a specific run ID
# Usage: make replay RUN_ID=abc
replay:
	python -m scheduler.replay_engine $(RUN_ID)

# Run the drift classification engine
drift:
	python analysis/drift_engine.py $(RUN_ID)

# Track drift evolution in the immutable ledger
evolution:
	python analysis/evolution_tracker.py $(RUN_ID)

# Run the entire observability verification suite (replay -> drift -> evolution)
verify: replay drift evolution

# ==========================================
# 3. THE QUERY PLANE (INVESTOR INTERFACE)
# ==========================================

# Query the deterministic system health score for a run
health:
	python query.py system health $(RUN_ID)

# Run any custom query against the QueryPlane
# Usage: make query CMD="drift over_time FLOAT"
query:
	python query.py $(CMD)

# Run the Semantic Compatibility Test to predict breaking changes
# Usage: make compat CMD="drift.over_time" V1="v1" V2="v2"
compat:
	python query.py compat compare $(CMD) $(V1) $(V2)
