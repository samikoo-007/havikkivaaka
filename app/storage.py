"""SQLite storage for plate-waste events and day totals."""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Collection


@dataclass
class DayStats:
    count: int
    total_g: float
    avg_g: float
    max_g: float
    min_g: float | None = None
    smile_count: int = 0
    ok_count: int = 0
    frown_count: int = 0


class Storage:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        # WAL survives unclean power loss better than default DELETE journal;
        # keep FULL sync so a flush-honest disk rolls back an open txn.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
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
                  day TEXT NOT NULL,
                  scale_id TEXT NOT NULL DEFAULT 'a'
                );
                """
            )
            cols = {
                str(r[1])
                for r in conn.execute("PRAGMA table_info(events)").fetchall()
            }
            if "scale_id" not in cols:
                conn.execute(
                    "ALTER TABLE events ADD COLUMN scale_id TEXT NOT NULL DEFAULT 'a'"
                )

    def add_event(
        self,
        grams: float,
        feedback: str,
        *,
        scale_id: str = "a",
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        day = date.today().isoformat()
        sid = (scale_id or "a").strip().lower()[:8] or "a"
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO events (ts, grams, feedback, day, scale_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (now, grams, feedback, day, sid),
            )

    def day_stats(
        self,
        day: str | None = None,
        *,
        scale_ids: Collection[str] | None = None,
    ) -> DayStats:
        day = day or date.today().isoformat()
        with self._connect() as conn:
            if scale_ids is None:
                where = "day = ?"
                params: list[Any] = [day]
            else:
                ids = [str(s).strip().lower() for s in scale_ids if str(s).strip()]
                if not ids:
                    return DayStats(0, 0.0, 0.0, 0.0, None)
                placeholders = ",".join("?" for _ in ids)
                where = f"day = ? AND scale_id IN ({placeholders})"
                params = [day, *ids]
            row = conn.execute(
                f"""
                SELECT COUNT(*) AS c,
                       COALESCE(SUM(grams), 0) AS total,
                       COALESCE(AVG(grams), 0) AS avg,
                       COALESCE(MAX(grams), 0) AS mx,
                       MIN(grams) AS mn,
                       COALESCE(SUM(CASE WHEN feedback = 'smile' THEN 1 ELSE 0 END), 0) AS smiles,
                       COALESCE(SUM(CASE WHEN feedback = 'ok' THEN 1 ELSE 0 END), 0) AS oks,
                       COALESCE(SUM(CASE WHEN feedback = 'frown' THEN 1 ELSE 0 END), 0) AS frowns
                FROM events WHERE {where}
                """,
                params,
            ).fetchone()
        c = int(row["c"])
        return DayStats(
            count=c,
            total_g=float(row["total"]),
            avg_g=float(row["avg"]) if c else 0.0,
            max_g=float(row["mx"]) if c else 0.0,
            min_g=float(row["mn"]) if c and row["mn"] is not None else None,
            smile_count=int(row["smiles"]),
            ok_count=int(row["oks"]),
            frown_count=int(row["frowns"]),
        )

    def list_events(
        self,
        day: str | None = None,
        limit: int = 200,
        offset: int = 0,
        *,
        scale_ids: Collection[str] | None = None,
    ) -> list[dict[str, Any]]:
        day = day or date.today().isoformat()
        limit = max(1, min(int(limit), 2000))
        offset = max(0, int(offset))
        with self._connect() as conn:
            if scale_ids is None:
                where = "day = ?"
                params: list[Any] = [day, limit, offset]
            else:
                ids = [str(s).strip().lower() for s in scale_ids if str(s).strip()]
                if not ids:
                    return []
                placeholders = ",".join("?" for _ in ids)
                where = f"day = ? AND scale_id IN ({placeholders})"
                params = [day, *ids, limit, offset]
            rows = conn.execute(
                f"""
                SELECT id, ts, grams, feedback, day, scale_id
                FROM events WHERE {where}
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()
        return [
            {
                "id": int(r["id"]),
                "ts": r["ts"],
                "grams": float(r["grams"]),
                "feedback": r["feedback"],
                "day": r["day"],
                "scale_id": r["scale_id"] or "a",
            }
            for r in rows
        ]

    def export_day_rows(self, day: str | None = None) -> list[dict[str, Any]]:
        day = day or date.today().isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, ts, grams, feedback, day, scale_id
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
                "scale_id": r["scale_id"] or "a",
            }
            for r in rows
        ]

    def export_day_csv(self, day: str | None = None) -> str:
        rows = self.export_day_rows(day)
        buf = io.StringIO()
        writer = csv.DictWriter(
            buf,
            fieldnames=["id", "ts", "grams", "feedback", "day", "scale_id"],
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
        plate_stats: DayStats | None = None,
        kitchen_stats: DayStats | None = None,
    ) -> str:
        day = day or date.today().isoformat()
        rows = self.export_day_rows(day)
        stats = self.day_stats(day)
        total_kg = stats.total_g / 1000.0
        payload: dict[str, Any] = {
            "day": day,
            "site_id": site_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "count": stats.count,
                "total_g": round(stats.total_g, 1),
                "total_kg": round(total_kg, 3),
                "avg_g": round(stats.avg_g, 1),
                "max_g": round(stats.max_g, 1),
                "min_g": round(stats.min_g, 1) if stats.min_g is not None else None,
                "smile_count": stats.smile_count,
                "ok_count": stats.ok_count,
                "frown_count": stats.frown_count,
                "co2_kg": round(total_kg * float(co2_factor_kg_per_kg), 3)
                if co2_factor_kg_per_kg
                else None,
            },
            "events": rows,
        }
        if plate_stats is not None:
            payload["plate"] = {
                "count": plate_stats.count,
                "total_g": round(plate_stats.total_g, 1),
                "total_kg": round(plate_stats.total_g / 1000.0, 3),
            }
        if kitchen_stats is not None:
            payload["kitchen"] = {
                "count": kitchen_stats.count,
                "total_g": round(kitchen_stats.total_g, 1),
                "total_kg": round(kitchen_stats.total_g / 1000.0, 3),
            }
        return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

    def clear_day(self, day: str | None = None) -> int:
        """Delete today's events so day counters reset to zero."""
        day = day or date.today().isoformat()
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM events WHERE day = ?", (day,))
            return int(cur.rowcount)
