"""MCP server exposing a per-project SQLite run-history database as tools,
so the agent orchestrating a reproduction logs attempts/metrics/events
directly via tool calls -- instead of shelling out ad hoc scripts, or (worse)
leaving the narrative of what was tried/tweaked/failed only in chat scrollback.

Not a replacement for the per-attempt JSON/xyz files nebskill's pipeline
steps already write (those remain the source of truth for geometries and
energies) -- this is a queryable index over them, plus a place to record the
things those files don't carry: interventions, diagnostics, cancellations.

The database lives in the current working directory by default (next to
neb_local.yaml / outputs/, same convention as the rest of nebskill), as
nebskill_history.db. Override with NEBSKILL_HISTORY_DB.

Install with the optional `history` extra:
    pip install 'nebskill[history] @ git+https://github.com/william-dawson/nebskill.git'
Then run directly (nebskill-history-mcp is the installed console script) or
via the plugin's bundled .mcp.json.
"""
from __future__ import annotations

import json
import os
import sqlite3
from importlib import resources
from pathlib import Path

from mcp.server.mcpserver import MCPServer

DB_PATH = Path(os.environ.get("NEBSKILL_HISTORY_DB", "nebskill_history.db"))

mcp = MCPServer("nebskill-history")


def _schema_sql() -> str:
    return resources.files("nebskill").joinpath("history_schema.sql").read_text()


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_schema_sql())
    return conn


@mcp.tool()
def log_attempt(reaction_id: int, step: str, attempt_dir: str, outcome: str,
                 rxn_key: str | None = None, formula: str | None = None,
                 params: dict | None = None, job_id: str | None = None,
                 started_at: str | None = None, ended_at: str | None = None,
                 wall_time_s: float | None = None,
                 supersedes_id: int | None = None,
                 notes: str | None = None) -> dict:
    """Record one attempt at a pipeline step (relax|neb|optts|irc) for a
    reaction. Call this when planning/submitting an attempt (outcome=
    "running") and again via update_outcome once it finishes. Set
    supersedes_id to the attempt_id of a prior try this one replaces (e.g. a
    cancelled or failed run retried with different parameters). Returns
    {"attempt_id": int}."""
    conn = _conn()
    cur = conn.execute(
        "INSERT INTO attempts (reaction_id, rxn_key, formula, step, "
        "attempt_dir, params_json, job_id, started_at, ended_at, "
        "wall_time_s, outcome, supersedes_id, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (reaction_id, rxn_key, formula, step, attempt_dir,
         json.dumps(params) if params else None, job_id, started_at, ended_at,
         wall_time_s, outcome, supersedes_id, notes))
    conn.commit()
    aid = cur.lastrowid
    conn.close()
    return {"attempt_id": aid}


@mcp.tool()
def update_outcome(attempt_id: int, outcome: str,
                    ended_at: str | None = None,
                    wall_time_s: float | None = None) -> dict:
    """Update an attempt's outcome (e.g. running -> converged/failed/cancelled)
    once its job finishes."""
    conn = _conn()
    conn.execute(
        "UPDATE attempts SET outcome=?, ended_at=COALESCE(?, ended_at), "
        "wall_time_s=COALESCE(?, wall_time_s) WHERE id=?",
        (outcome, ended_at, wall_time_s, attempt_id))
    conn.commit()
    conn.close()
    return {"ok": True}


@mcp.tool()
def log_metric(attempt_id: int, name: str, value: float | None = None,
               text_value: str | None = None) -> dict:
    """Record a numeric or text metric against an attempt -- e.g.
    forward_barrier_ev, deviation_pct, n_imaginary, or verdict
    (text_value="first_order_saddle")."""
    conn = _conn()
    conn.execute(
        "INSERT INTO metrics (attempt_id, name, value, text_value) VALUES (?,?,?,?)",
        (attempt_id, name, value, text_value))
    conn.commit()
    conn.close()
    return {"ok": True}


@mcp.tool()
def log_event(attempt_id: int, kind: str, text: str,
              ts: str | None = None) -> dict:
    """Record a narrative event against an attempt: kind is one of
    diagnostic|intervention|cancellation|finding. This is the place for the
    reasoning a JSON result file can't hold -- why a parameter was changed,
    what a stalled band looked like, what was ruled out and why."""
    conn = _conn()
    conn.execute(
        "INSERT INTO events (attempt_id, ts, kind, text) VALUES (?,?,?,?)",
        (attempt_id, ts, kind, text))
    conn.commit()
    conn.close()
    return {"ok": True}


@mcp.tool()
def query(sql: str) -> list[dict]:
    """Run a read-only SELECT query against the history database and return
    rows as a list of dicts. Only SELECT statements are permitted. Useful
    tables: attempts, metrics, events; see the latest_converged view for the
    most recent converged attempt per reaction/step."""
    stripped = sql.strip().lower()
    if not stripped.startswith("select"):
        raise ValueError("Only SELECT queries are permitted through this tool.")
    conn = _conn()
    rows = [dict(r) for r in conn.execute(sql).fetchall()]
    conn.close()
    return rows


@mcp.tool()
def reaction_summary(reaction_id: int) -> dict:
    """Full history for one reaction: every attempt, its metrics, and its
    events, in one call -- the equivalent of re-reading the whole story of
    how a reaction was studied."""
    conn = _conn()
    attempts = [dict(r) for r in conn.execute(
        "SELECT * FROM attempts WHERE reaction_id=? ORDER BY id", (reaction_id,))]
    for a in attempts:
        a["metrics"] = [dict(r) for r in conn.execute(
            "SELECT name, value, text_value FROM metrics WHERE attempt_id=?", (a["id"],))]
        a["events"] = [dict(r) for r in conn.execute(
            "SELECT kind, text, ts FROM events WHERE attempt_id=?", (a["id"],))]
    conn.close()
    return {"reaction_id": reaction_id, "attempts": attempts}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
