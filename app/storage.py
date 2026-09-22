"""SQLite storage for plate-waste events and day totals."""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class DayStats:
    count: int
    total_g: float
    avg_g: float
    max_g: float
    smile_count: int = 0
    frown_count: int = 0


class Storage:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  ts TEXT NOT NULL,
                  grams REAL NOT NULL,
                  feedback TEXT NOT NULL,
                  day TEXT NOT NULL
                );
                """
            )

    def add_event(self, grams: float, feedback: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        day = date.today().isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO events (ts, grams, feedback, day) VALUES (?, ?, ?, ?)",
                (now, grams, feedback, day),
            )

    def day_stats(self, day: str | None = None) -> DayStats:
        day = day or date.today().isoformat()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS c,
                       COALESCE(SUM(grams), 0) AS total,
                       COALESCE(AVG(grams), 0) AS avg,
                       COALESCE(MAX(grams), 0) AS mx,
                       COALESCE(SUM(CASE WHEN feedback = 'smile' THEN 1 ELSE 0 END), 0) AS smiles,
                       COALESCE(SUM(CASE WHEN feedback = 'frown' THEN 1 ELSE 0 END), 0) AS frowns
                FROM events WHERE day = ?
                """,
                (day,),
            ).fetchone()
        c = int(row["c"])
        return DayStats(
            count=c,
            total_g=float(row["total"]),
            avg_g=float(row["avg"]) if c else 0.0,
            max_g=float(row["mx"]) if c else 0.0,
            smile_count=int(row["smiles"]),
            frown_count=int(row["frowns"]),
        )

    def list_events(
        self,
        day: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        day = day or date.today().isoformat()
        limit = max(1, min(int(limit), 2000))
        offset = max(0, int(offset))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, ts, grams, feedback, day
                FROM events WHERE day = ?
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (day, limit, offset),
            ).fetchall()
        return [
            {
                "id": int(r["id"]),
                "ts": r["ts"],
                "grams": float(r["grams"]),
                "feedback": r["feedback"],
                "day": r["day"],
            }
            for r in rows
        ]

    def export_day_rows(self, day: str | None = None) -> list[dict[str, Any]]:
        day = day or date.today().isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, ts, grams, feedback, day
                FROM events WHERE day = ?
                ORDER BY id ASC
                """,
                (day,),
            ).fetchall()
        return [
            {
                "id": int(r["id"]),
                "ts": r["ts"],
                "grams": float(r["grams"]),
                "feedback": r["feedback"],
                "day": r["day"],
            }
            for r in rows
        ]

    def export_day_csv(self, day: str | None = None) -> str:
        rows = self.export_day_rows(day)
        buf = io.StringIO()
        writer = csv.DictWriter(
            buf,
            fieldnames=["id", "ts", "grams", "feedback", "day"],
            lineterminator="\n",
        )
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
        return buf.getvalue()

    def export_day_json(
        self,
        day: str | None = None,
        *,
        site_id: str | None = None,
        co2_factor_kg_per_kg: float = 0.0,
    ) -> str:
        day = day or date.today().isoformat()
        rows = self.export_day_rows(day)
        stats = self.day_stats(day)
        total_kg = stats.total_g / 1000.0
        payload = {
            "day": day,
            "site_id": site_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "count": stats.count,
                "total_g": round(stats.total_g, 1),
                "total_kg": round(total_kg, 3),
                "avg_g": round(stats.avg_g, 1),
                "max_g": round(stats.max_g, 1),
                "smile_count": stats.smile_count,
                "frown_count": stats.frown_count,
                "co2_kg": round(total_kg * float(co2_factor_kg_per_kg), 3)
                if co2_factor_kg_per_kg
                else None,
            },
            "events": rows,
        }
        return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

    def clear_day(self, day: str | None = None) -> int:
        """Delete today's events so day counters reset to zero."""
        day = day or date.today().isoformat()
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM events WHERE day = ?", (day,))
            return int(cur.rowcount)
