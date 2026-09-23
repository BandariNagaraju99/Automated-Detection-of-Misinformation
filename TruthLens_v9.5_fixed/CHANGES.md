# TruthLens v9.5 — Fix Changelog

## Problems Fixed

### 1. "18 Days Ago" Stale Article Bug
**Root cause:** The RSS fetch accepted any article regardless of age; old articles
stayed in FAISS index between refreshes with their original timestamps, so even
after a rebuild they showed as days/weeks old.

**Fix (`rag_engine.py`):**
- `_fetch_one_feed()` now **skips articles older than 7 days** entirely.
- Future timestamps (clock drift) are clamped to `now`.
- Articles are **deduplicated by URL** before indexing.
- Articles are **sorted by freshness** (newest first) in the index.

### 2. Too Much UNCERTAIN
**Root cause:** For temporal queries like "Hyderabad rain today", the cached index
had no fresh articles → low avg_sim → UNCERTAIN, even when real live results existed.

**Fix (`predictor.py` + `rag_engine.py`):**
- `'today'` and `'tomorrow'` queries **always force a live Google News search**
  (no longer optional / threshold-dependent).
- When live results are found fresh, a small `+8%` boost to `final_real` is applied.
- Staleness damping in `search()` now uses per-temporality multipliers.

### 3. Today / Tomorrow / Weekday / Month Awareness
**Fix (`analyzer.py`):**
- `detect_temporal()` now returns `'today' | 'tomorrow' | 'yesterday' | 'week' | 'month' | 'recent' | 'any'`
  (previously only had 4 buckets, no `'tomorrow'` or `'month'`).
- Added extensive word lists for weekday names, month names, Hindi temporal words.
- `temporal_label()` returns a human-friendly string with the **actual calendar date**.
- `get_linguistic_score()` now passes `temporality` through to the predictor.

**Fix (`rag_engine.py`):**
- `_staleness_factor()` has a per-temporality policy:
  - `today` → articles >24h get heavy penalty; >48h get 0.15×
  - `tomorrow` → forecasts/predictions preferred (fresh ≤12h full weight)
  - `week` → 7-day window
  - `month` → 30-day window
  - `any` → gentle falloff

**Fix (`predictor.py`):**
- `FORCE_LIVE_TEMPORALITIES = {'today', 'tomorrow'}` always triggers live search.
- Explanation includes temporal context: *"Query time context: today (Sunday, 05 Apr 2026)"*.

### 4. New RSS Feeds (V6, TV9 India, Telugu sources)
**Fix (`rag_engine.py` — `RSS_FEEDS` list):**
```
V6 News Telugu    https://www.v6news.tv/feed/
TV9 Telugu        https://tv9telugu.com/feed/
TV9 India         https://www.tv9hindi.com/feed
Sakshi TV         https://www.sakshi.com/rss.xml
ABN Telugu        https://www.andhrabhoomi.net/rss.xml
India Met Dept    https://city.imd.gov.in/citywx/rss/hyd.xml  (Hyderabad IMD)
```
Source tiers updated accordingly (Tier 2 for Telugu channels).
`max_workers` for ThreadPoolExecutor increased from 6 → 8 to handle more feeds.
`entry[:15]` → `entry[:20]` for wider per-feed coverage.

### 5. UI: Freshness Indicators
**Fix (`templates/index.html`):**
- Live **date/time clock** in a top bar (day, date, IST time, tomorrow's date).
- `time_ago` now shows actual publish age (e.g. "2h ago", "Yesterday", "3d ago",
  or a full date if older than 1 week).
- Evidence cards have **colored left-edge stripes**:
  🟢 green = <6h, 🟡 amber = <24h, 🔴 red = older
- **Freshness summary bar** above evidence: "🔥 3 <6h · ⏰ 2 <24h · 📅 1 older".
- Temporal context chip shown above results: "⏱️ TODAY — Live search active" etc.
- Source badge row lists all 15 RSS sources; new Telugu feeds marked ✦.
- Reasoning text split into separate lines (no more single dense string).
- Sample chip rows expanded with Telugu and temporal examples.

## Files Changed
| File | Status |
|------|--------|
| `analyzer.py`        | ✅ Fixed |
| `predictor.py`       | ✅ Fixed |
| `rag_engine.py`      | ✅ Fixed |
| `templates/index.html` | ✅ Fixed |
| `app.py`             | Unchanged |
| `model.py`           | Unchanged |
| `train.py`           | Unchanged |
| `requirements.txt`   | Unchanged |

## Files NOT Included (keep your originals)
- `ann.pth` — 579 MB trained model weights
- `WELFake_Dataset.csv` — 245 MB training dataset
