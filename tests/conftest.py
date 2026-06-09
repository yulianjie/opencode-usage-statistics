import json
import sqlite3

import pytest


def _msg(mid, session_id, ts, provider, model, role, mode, cost, tokens):
    data = {
        "role": role,
        "mode": mode,
        "providerID": provider,
        "modelID": model,
        "cost": cost,
        "tokens": tokens,
    }
    return (mid, session_id, ts, json.dumps(data))


@pytest.fixture
def sample_db(tmp_path):
    """A minimal opencode.db with message + session tables and known token data."""
    path = tmp_path / "opencode.db"
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE session (id TEXT PRIMARY KEY, title TEXT)")
    conn.execute(
        "CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER, data TEXT)"
    )
    conn.executemany(
        "INSERT INTO session (id, title) VALUES (?, ?)",
        [("ses_a", "Session A"), ("ses_b", "Session B")],
    )
    rows = [
        _msg("m1", "ses_a", 1_700_000_000_000, "anthropic", "claude-sonnet-4-6", "assistant", "build", 0.05,
             {"total": 1000, "input": 800, "output": 200, "reasoning": 0, "cache": {"read": 100, "write": 50}}),
        _msg("m2", "ses_a", 1_700_000_100_000, "anthropic", "claude-sonnet-4-6", "assistant", "build", 0.03,
             {"total": 500, "input": 400, "output": 100, "reasoning": 0, "cache": {"read": 0, "write": 0}}),
        _msg("m3", "ses_b", 1_700_100_000_000, "openai", "gpt-4o", "assistant", "build", 0.10,
             {"total": 2000, "input": 1500, "output": 500, "reasoning": 0, "cache": {"read": 200, "write": 0}}),
        # user message with no tokens -> must be dropped
        _msg("m4", "ses_a", 1_700_000_050_000, "anthropic", "claude-sonnet-4-6", "user", "build", None,
             {"total": 0}),
        # unpriced model
        _msg("m5", "ses_b", 1_700_100_100_000, "mystery", "unknown-model", "assistant", "build", None,
             {"total": 300, "input": 300, "output": 0, "reasoning": 0, "cache": {"read": 0, "write": 0}}),
    ]
    conn.executemany(
        "INSERT INTO message (id, session_id, time_created, data) VALUES (?, ?, ?, ?)", rows
    )
    conn.commit()
    conn.close()
    return path
