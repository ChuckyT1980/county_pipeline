# Root Cause: BUTTE_MONITOR / KERN_MONITOR launch failure

**Date diagnosed**: 2026-08-08

## What happened

Both `Agent` tool calls for BUTTE_MONITOR and KERN_MONITOR were launched
with `isolation: "worktree"` and failed immediately, before any tool use,
with the identical error:

```
Cannot create agent worktree: not in a git repository and no WorktreeCreate
hooks are configured. Configure WorktreeCreate/WorktreeRemove hooks in
settings.json to use worktree isolation with other VCS systems.
```

## Diagnosis

The error text is misleading about its own cause. Directly verified:

```
$ git rev-parse --is-inside-work-tree
true
```

`county_pipeline` genuinely is a git repository (has been throughout this
session - every commit this session succeeded normally). So "not in a
git repository" is not the actual condition that triggered this.

Per the Agent tool's own documentation, `isolation: "worktree"` requires
a `WorktreeCreate` hook to be registered in this environment's
`settings.json` to create the temporary worktree checkout. No such hook
is configured here. That is the real, sole cause: an environment/tooling
configuration gap, not a defect in county_pipeline's own code, git
state, or permissions.

## Why COUNTY_PROCESSOR_A/B/C succeeded where BUTTE/KERN_MONITOR failed

The three county-processor agents (Del Norte/Glenn, Kings/Lake,
Riverside/San Diego) were launched WITHOUT `isolation: "worktree"` and
all three ran and completed normally. This confirms the fix directly:
omit worktree isolation.

## Fix applied

Re-ran BUTTE_MONITOR and KERN_MONITOR's work directly (this session, no
subagent dispatch) rather than requesting worktree isolation again.
Isolation was not actually load-bearing for this scope: Butte and Kern
touch fully disjoint, county-prefixed files (`output/dashboard/butte_*`,
`output/dashboard/kern_*`), so there was never a real risk of concurrent
file conflicts that worktree isolation exists to prevent.

## Scope note

This is an environment configuration gap outside county_pipeline's own
codebase - fixing it permanently (adding a WorktreeCreate hook) is not a
county_pipeline code change and is out of scope for this ticket. Future
sessions needing true worktree isolation for genuinely overlapping
county work should flag this gap rather than assume worktree isolation
is available by default.
