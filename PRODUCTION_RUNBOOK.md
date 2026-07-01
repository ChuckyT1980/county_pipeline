# MAR-1 Phase 4E: Live Shadow Deployment Runbook

**Version:** 1.0
**Status:** Frozen Production Contract (FPC-1)

This runbook defines the exact procedural boundary for executing the MAR-1 live shadow ingestion pipeline against the Shasta and Tehama County endpoints. 

> [!WARNING]
> This system is a **measured failure geometry instrument**. It is explicitly NON-ADAPTIVE. Do NOT modify the MAR-1 decision state, add learning loops, or alter execution variables based on offline deployment gates.

## System Topology
1. **MAR-1 Runtime (Actuator):** Frozen, deterministic policy evaluator.
2. **SMC-1 (Observation Substrate):** Read-only, fixed-cadence HTTP ingestion. Append-only WAL logging.
3. **Analytical Core (H6 + DRTM + CDV):** Offline topological metrics evaluating continuous semantic deformation.
4. **Certification (SDVR-1 + DAF-1):** Strictly post-hoc measurement gating.

---

## 1. Prerequisites
- Target server must possess active DNS routing to `mptsweb.co.shasta.ca.us` and `mptsweb.co.tehama.ca.us`.
- `deployment_manifest.yaml` MUST remain unmodified.
- Execution directory must contain the full `mar1/` package.

## 2. Execution Protocol

### Step 1: Shadow Ingestion (SMC-1)
To run the live read-only shadow extraction (100 events):
```bash
python -m mar1.adapters.live_shadow_adapter
```
*Note: This adapter implements strict fixed-cadence requests. It does NOT retry on HTTP 500s or timeouts. All latency and DNS failures are recorded raw.*

### Step 2: Replay Validation
Ensure deterministic hashing between live WAL and replay logic:
```bash
python -m mar1.test.mar1_offline_auditor --run-replay
```
*Expected Output: 100/100 Replay Consistency.*

### Step 3: Analytical Core Execution (H6 + DRTM)
Extract continuous drift manifolds and regime topologies:
```bash
python -m mar1.test.mar1_h6_harness
```
*Expected Output: `h6_resilience_report.json` containing the Drift Phase Histogram ($H_S, H_T, H_C$) and systemic invariants ($\alpha(t)$, $H_T$).*

### Step 4: SDVR-1 Certification & DAF-1 Gate
Execute the final multi-manifold coherence functional:
```bash
python -m mar1.test.mar1_certification
```

---

## 3. Interpreting the Certification Output

The final script outputs the **Shadow Deployment Validation Run Score (SDVR-1)** and its **Confidence Decomposition Vector (CDV-1)**.

### SDVR-1 Score Bounds:
- `0.85 - 1.00`: Structurally robust under epistemic stress. SAFE to proceed with broader shadow expansion.
- `0.60 - 0.85`: Stable but sensitive to drift coupling.
- `< 0.60`: UNABLE TO DEPLOY. Architecture is brittle under multi-regime interference.

### CDV-1 Decomposition Attribution:
If `SDVR-1` fails, evaluate the $\mathbf{CDV}$ log-space gradient to isolate the dominant failure geometry:
- $|g_I| >> others$: **Ingestion Dominated.** (Fix SMC-1 routing or endpoints).
- $|g_D| >> others$: **Drift Dominated.** (H6 semantic rot is active; schemas have diverged continuously).
- $|g_C| >> others$: **Topology Dominated.** (DRTM flow instability; regime overlap is collapsing).
- $g_A = -\infty$: **Hard DAF-1 Violation.** Deployment forbidden by strict non-dominance rules.

## 4. Architectural Invariants
If any modifications are made to the codebase, the following invariants must be reverified mathematically. Failure to do so reintroduces feedback control loops into the observation stack.
1. $\frac{\partial \text{MAR-1 policy}}{\partial \text{history}} = 0$
2. $\text{Runtime} \cap \text{Inference} = \emptyset$
3. $CDV \not\to \text{MAR-1}$
