from .models import CountyState, ThrottleResult

def compute_throttle(state: CountyState) -> ThrottleResult:
    reliability = state.success_rate
    drift_penalty = max(0, 1.0 - state.drift_score)
    latency_penalty = 1.0 / (1.0 + state.avg_latency_ms / 1000.0)

    multiplier = reliability * drift_penalty * latency_penalty
    base_rps = state.max_rps
    adjusted_rps = base_rps * multiplier

    blocked = adjusted_rps < 0.05

    return ThrottleResult(
        rps=adjusted_rps,
        blocked=blocked
    )
