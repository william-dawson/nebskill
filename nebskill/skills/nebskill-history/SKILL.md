---
name: nebskill-history
description: >
  Logs the story of a reaction reproduction -- every attempt, its parameters,
  outcome, key metrics, and the reasoning behind interventions/retries -- to a
  queryable per-project SQLite database via the bundled nebskill-history MCP
  server. Use alongside relax/neb/optts/irc so the agent records what was
  tried, what failed, what was tweaked, and the final result, instead of that
  narrative only living in chat scrollback.
allowed-tools: Bash Read
---

## Why this exists

Each pipeline step already writes a structured JSON result (`neb_result.json`,
`ts_opt_orca.json`, `irc_orca.json`, `report.json`) into its attempt
directory -- that stays the source of truth for geometries and energies.
What those files *don't* capture is the narrative: why a run was cancelled
and retried with different parameters, what a stalled band's diagnostics
looked like, what was ruled out and why. A text writeup captures that for one
reaction; it can't answer "which reactions needed more than one NEB attempt"
or "what's the average barrier deviation across everything reproduced so
far." The history database is a queryable index over exactly that.

## Prerequisites

```bash
pip install 'nebskill[history] @ git+https://github.com/william-dawson/nebskill.git'
nebskill-history-mcp --help 2>/dev/null || echo "(it's an MCP server, not a CLI -- verify the mcp package imports instead)"
python3 -c "import mcp.server.mcpserver"
```
If the import fails, the `history` extra isn't installed — `pip install
'nebskill[history]'`. The MCP server itself (`nebskill-history-mcp`) is
declared in the plugin's `.mcp.json` and connects automatically once
installed; its tools (`log_attempt`, `log_metric`, `log_event`,
`update_outcome`, `query`, `reaction_summary`) then appear as regular tool
calls — no separate setup.

## Database location

`nebskill_history.db` in the current working directory (same convention as
`outputs/`, `neb_local.yaml`) — override with `NEBSKILL_HISTORY_DB` if
needed. Created automatically on first use.

## When to log

- **`log_attempt`** when planning/submitting a relax|neb|optts|irc attempt
  (`outcome="running"`), and again via **`update_outcome`** once the job
  finishes. Pass `supersedes_id` when a retry replaces a cancelled or failed
  prior attempt at the same step, so the chain is explicit rather than just
  three unrelated rows.
- **`log_metric`** for each key number worth querying on later:
  `forward_barrier_ev`, `deviation_pct` (vs. the dataset reference),
  `n_imaginary`, `verdict` (as `text_value`), `connects_reactant_product`.
- **`log_event`** for the reasoning a JSON file can't hold — a
  `diagnostic` (e.g. "climbing-image index reassigned 5->7->4->8->3 during
  convergence"), an `intervention` and why it was chosen (see
  `/nebskill:nebskill-monitoring-convergence`), a `cancellation` reason, or a
  `finding` (e.g. a barrier turning out far lower than the dataset reference).

## Querying

`query` takes any read-only `SELECT`. A few starting points:

```sql
-- Every reaction's final barrier deviation from the dataset reference
SELECT reaction_id, rxn_key, m.value AS deviation_pct
FROM attempts a JOIN metrics m ON m.attempt_id = a.id
WHERE a.step='neb' AND a.outcome='converged' AND m.name='deviation_pct';

-- Attempts that needed more than one try at the same step
SELECT reaction_id, step, COUNT(*) n
FROM attempts GROUP BY reaction_id, step HAVING n > 1;

-- Fully verified reactions (converged optts, first-order saddle)
SELECT DISTINCT a.reaction_id
FROM attempts a JOIN metrics m ON m.attempt_id=a.id
WHERE a.step='optts' AND m.name='verdict' AND m.text_value='first_order_saddle';
```

`reaction_summary(reaction_id)` returns the whole story for one reaction in
one call — every attempt with its metrics and events attached — useful when
picking a reaction back up after a break.
