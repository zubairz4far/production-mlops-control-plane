from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,
    version TEXT NOT NULL,
    artifact_uri TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL,
    dataset_sha256 TEXT NOT NULL,
    code_sha TEXT NOT NULL,
    eval_samples INTEGER NOT NULL,
    metrics_json TEXT NOT NULL,
    stage TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(model_name, version)
);

CREATE TABLE IF NOT EXISTS promotion_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id INTEGER NOT NULL REFERENCES models(id),
    champion_model_id INTEGER REFERENCES models(id),
    decision TEXT NOT NULL,
    reasons_json TEXT NOT NULL,
    policy_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS deployments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    environment TEXT NOT NULL,
    revision INTEGER NOT NULL,
    model_id INTEGER NOT NULL REFERENCES models(id),
    state TEXT NOT NULL,
    traffic_pct REAL NOT NULL,
    previous_deployment_id INTEGER REFERENCES deployments(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(environment, revision)
);

CREATE TABLE IF NOT EXISTS drift_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deployment_id INTEGER NOT NULL REFERENCES deployments(id),
    psi REAL NOT NULL,
    ks_stat REAL NOT NULL,
    mean_shift_sigma REAL NOT NULL,
    sample_size INTEGER NOT NULL,
    severity TEXT NOT NULL,
    decision TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS audit_events_no_update
BEFORE UPDATE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit events are immutable');
END;

CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
BEFORE DELETE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit events are immutable');
END;
"""


class Store:
    def __init__(self, path: str | Path = ":memory:") -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.connection.executescript(SCHEMA)
            self.connection.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.lock:
            try:
                self.connection.execute("BEGIN IMMEDIATE")
                yield self.connection
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise

    def fetchone(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object] | None:
        with self.lock:
            row = self.connection.execute(sql, params).fetchone()
        return dict(row) if row is not None else None

    def fetchall(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        with self.lock:
            rows = self.connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def dumps(value: object) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def loads(value: str) -> object:
        return json.loads(value)
