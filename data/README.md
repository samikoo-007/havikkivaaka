# Runtime data (not committed)

This directory holds local runtime files. They are gitignored except the example cal.

| File | Purpose |
|------|---------|
| `ykv_sad_cal.json` | Live SAD→kg calibration (copy from example and capture on your unit) |
| `config.json` | Admin settings (created on first run) |
| `events.sqlite3` | Waste events |
| `exports/` | Day CSV/JSON exports |

## SAD calibration

```bash
cp data/ykv_sad_cal.example.json data/ykv_sad_cal.json
# Then capture empty + reference load (see .cursor/skills/ykv-commissioning/)
python3 tools/ykv_sad_weight.py --capture empty
python3 tools/ykv_sad_weight.py --capture ref --ref-kg 50
```

Do **not** commit real `ykv_sad_cal.json`, event databases, or exports — they are site-specific.
