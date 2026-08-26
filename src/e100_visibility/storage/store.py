"""SQLite-backed history of every run, so trend/position-over-time reporting
works without re-querying any LLM provider.

SQLite (stdlib ``sqlite3``, one file) was chosen over plain JSON files: this
tool's whole point is comparing "this run" against "the previous run for the
same market", which is a query (``ORDER BY id DESC LIMIT 1 OFFSET 1``)
rather than a full directory scan, and it stays a single portable file with
no extra dependency -- matching the sibling dropdomain-scout tool's cache.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ..analysis.schema import AnalysisResult
from ..models import Observation

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    market_language TEXT NOT NULL,
    market_country TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    timestamp TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    query TEXT NOT NULL,
    language TEXT NOT NULL,
    country TEXT NOT NULL,
    answer_text TEXT,
    citations_json TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    fetch_error TEXT,
    analysis_method TEXT,
    analysis_error TEXT,
    mentioned INTEGER,
    position INTEGER,
    total_brands INTEGER,
    brands_in_order_json TEXT,
    context TEXT,
    context_category TEXT,
    sentiment TEXT,
    has_source_link INTEGER,
    competitors_above_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_observations_run_id ON observations(run_id);
CREATE INDEX IF NOT EXISTS idx_runs_market ON runs(market_language, market_country);
"""


class RunStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def __enter__(self) -> "RunStore":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    def start_run(self, *, started_at: str, language: str, country: str) -> int:
        cursor = self._conn.execute(
            "INSERT INTO runs (started_at, market_language, market_country) VALUES (?, ?, ?)",
            (started_at, language, country),
        )
        self._conn.commit()
        return cursor.lastrowid

    def save_observation(self, observation: Observation) -> None:
        analysis = observation.analysis
        self._conn.execute(
            """
            INSERT INTO observations (
                run_id, timestamp, provider, model, query, language, country,
                answer_text, citations_json, raw_json, fetch_error,
                analysis_method, analysis_error,
                mentioned, position, total_brands, brands_in_order_json,
                context, context_category, sentiment, has_source_link,
                competitors_above_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation.run_id,
                observation.timestamp,
                observation.provider,
                observation.model,
                observation.query,
                observation.language,
                observation.country,
                observation.answer_text,
                json.dumps(list(observation.citations)),
                json.dumps(observation.raw),
                observation.fetch_error,
                analysis.method if analysis else None,
                analysis.error if analysis else None,
                int(analysis.mentioned) if analysis else None,
                analysis.position if analysis else None,
                analysis.total_brands if analysis else None,
                json.dumps(list(analysis.brands_in_order)) if analysis else None,
                analysis.context if analysis else None,
                analysis.context_category if analysis else None,
                analysis.sentiment if analysis else None,
                int(analysis.has_source_link) if analysis else None,
                json.dumps(list(analysis.competitors_above)) if analysis else None,
            ),
        )
        self._conn.commit()

    def previous_run_id(self, *, language: str, country: str, before_run_id: int) -> int | None:
        row = self._conn.execute(
            """
            SELECT id FROM runs
            WHERE market_language = ? AND market_country = ? AND id < ?
            ORDER BY id DESC LIMIT 1
            """,
            (language, country, before_run_id),
        ).fetchone()
        return row["id"] if row else None

    def observations_for_run(self, run_id: int) -> list[Observation]:
        rows = self._conn.execute(
            "SELECT * FROM observations WHERE run_id = ? ORDER BY id ASC",
            (run_id,),
        ).fetchall()
        return [_row_to_observation(row) for row in rows]


def _row_to_observation(row: sqlite3.Row) -> Observation:
    analysis = None
    if row["analysis_method"] is not None or row["analysis_error"] is not None:
        analysis = AnalysisResult(
            mentioned=bool(row["mentioned"]) if row["mentioned"] is not None else False,
            position=row["position"],
            total_brands=row["total_brands"] or 0,
            brands_in_order=tuple(json.loads(row["brands_in_order_json"] or "[]")),
            context=row["context"] or "",
            context_category=row["context_category"] or "not_mentioned",
            sentiment=row["sentiment"] or "neutral",
            has_source_link=bool(row["has_source_link"]) if row["has_source_link"] is not None else False,
            competitors_above=tuple(json.loads(row["competitors_above_json"] or "[]")),
            method=row["analysis_method"] or "heuristic",
            error=row["analysis_error"],
        )

    return Observation(
        run_id=row["run_id"],
        timestamp=row["timestamp"],
        provider=row["provider"],
        model=row["model"],
        query=row["query"],
        language=row["language"],
        country=row["country"],
        answer_text=row["answer_text"],
        citations=tuple(json.loads(row["citations_json"] or "[]")),
        raw=json.loads(row["raw_json"] or "{}"),
        fetch_error=row["fetch_error"],
        analysis=analysis,
    )
