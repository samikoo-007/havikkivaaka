# Runtime data (not committed)

This directory holds local runtime files. They are gitignored except the example cal.

| File | Purpose |
|------|---------|
| `ykv_sad_cal.json` | Shared SAD→kg calibration (copy from example and capture on your unit) |
| `ykv_sad_cal_a.json` / `_b` / `_c` | Optional **per-slot** cal (preferred for A+B / A+B+C) |
| `config.json` | Admin settings (created on first run) |
| `events.sqlite3` | Waste events (SQLite WAL) |
| `exports/` | Day CSV/JSON exports |
| `day-close-stamps/` | Evening close markers (`YYYY-MM-DD.ok`) for power schedule |

If no `ykv_sad_cal*.json` is present, the live app uses factory KCP `SI` kilograms.

## SAD calibration

```bash
cp data/ykv_sad_cal.example.json data/ykv_sad_cal.json
# Then capture empty + reference load (see .cursor/skills/ykv-commissioning/)
python3 tools/ykv_sad_weight.py --capture empty
python3 tools/ykv_sad_weight.py --capture ref --ref-kg 50
# Multi-scale: copy/capture to ykv_sad_cal_a.json, ykv_sad_cal_b.json, …
```

Do **not** commit real `ykv_sad_cal*.json`, event databases, or exports — they are site-specific.
Do **not** copy another site’s cal file onto a new YKV+platform pair.
