-- nebskill run history: a structured, queryable log of every attempt made
-- while studying a reaction, alongside the existing per-attempt JSON/xyz
-- outputs (which remain the source of truth for the actual science -- this
-- is an index over them, not a replacement).

CREATE TABLE IF NOT EXISTS attempts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    reaction_id   INTEGER NOT NULL,
    rxn_key       TEXT,
    formula       TEXT,
    step          TEXT NOT NULL,      -- relax | neb | optts | irc
    attempt_dir   TEXT NOT NULL,      -- e.g. orca_n15_nebts_vpo_mv0.05
    params_json   TEXT,               -- exact parameters used, as JSON
    job_id        TEXT,
    started_at    TEXT,
    ended_at      TEXT,
    wall_time_s   REAL,
    outcome       TEXT NOT NULL,      -- converged | failed | cancelled | superseded | running
    supersedes_id INTEGER REFERENCES attempts(id),  -- links a retry to what it replaced
    notes         TEXT
);

CREATE TABLE IF NOT EXISTS metrics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id  INTEGER NOT NULL REFERENCES attempts(id),
    name        TEXT NOT NULL,        -- forward_barrier_ev, deviation_pct, n_imaginary, ...
    value       REAL,
    text_value  TEXT                  -- for non-numeric metrics (verdict, ...)
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id  INTEGER NOT NULL REFERENCES attempts(id),
    ts          TEXT,
    kind        TEXT NOT NULL,        -- diagnostic | intervention | cancellation | finding
    text        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_attempts_reaction ON attempts(reaction_id);
CREATE INDEX IF NOT EXISTS idx_metrics_attempt ON metrics(attempt_id);
CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(name);
CREATE INDEX IF NOT EXISTS idx_events_attempt ON events(attempt_id);

-- convenience view: latest converged result per reaction/step
CREATE VIEW IF NOT EXISTS latest_converged AS
SELECT a.*
FROM attempts a
WHERE a.outcome = 'converged'
  AND a.id = (
      SELECT a2.id FROM attempts a2
      WHERE a2.reaction_id = a.reaction_id AND a2.step = a.step AND a2.outcome = 'converged'
      ORDER BY a2.ended_at DESC LIMIT 1
  );
