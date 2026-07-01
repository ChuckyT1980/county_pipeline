from .models import CountyState
from .state_store import StateRepository

def load_counties(store: StateRepository) -> dict:
    counties = {
        "tehama": CountyState(
            county="tehama",
            max_rps=5,
            drift_score=0.1,
            success_rate=0.95,
            avg_latency_ms=300,
            backlog_size=0
        ),
        "shasta": CountyState(
            county="shasta",
            max_rps=3,
            drift_score=0.0,
            success_rate=0.0,
            avg_latency_ms=0,
            backlog_size=0
        )
    }
    
    # Init or restore from DB
    for name, initial_state in counties.items():
        existing = store.load_state(name)
        if existing:
            counties[name] = existing
        else:
            store.save_state(initial_state)
            
    return counties
