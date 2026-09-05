# September 5, 2026 — Lower-frequency archive scans

- Changed the configured and default recursive scan interval to 15 minutes, retaining startup and manual scans.
- Quick descriptions continue independently of the scan interval. Gemini Batch API remains a future option for nonurgent jobs; the existing frame-based queue already costs only cents per thousand descriptions.

# September 4, 2026 — Archive discovery and economical descriptions

- Reviewed source, CLI, documentation, configuration, live catalog, and source metadata.
- Fixed startup/periodic discovery and detached scans from media reads.
- Added durable quick descriptions from small frames/cached thumbnails with Gemini 2.5 Flash-Lite, usage estimates, daily budget, pause/resume and retry.
- Added missing/offloaded/local status, summary/tag search, background UI refresh, and bounded card rendering.
- Removed hover/editor preloads and automatic cloud thumbnail hydration.
- Preserved the database with an automatic migration backup; added WAL and indexes.
- Fixed save/analysis responses overwriting newer form input; hardened ready validation and kept full AI quality notes.
- Added tests and ran a successful low-cost live pilot. See README and ARCHIVE_DESIGN for current operations and limitations.

---

# ReelVault Progress Log

## 2026-06-29 — Post-move recovery & dashboard upgrades

### Environment & data
- Confirmed `./data/reelvault.db` and `./data/thumbnails` follow the project via relative paths; `REELS_FOLDER` stays absolute (iCloud).
- Rebuilt index after old project `data/` was lost: `reelctl scan` repopulated ~1,267 reels from iCloud.
- Installed missing Python deps (`fastapi`, `uvicorn`, `google-genai`, etc.); reinstalled frontend `node_modules` (fixed broken `lightningcss` after move).

### Draft saving (workbench)
- **Bug:** Manual caption / hashtags / notes appeared to not persist (DB was empty; UI reloaded stale list).
- **Fix:** Auto-save (~600ms), save-on-close, fresh fetch on open, in-place list update (no full reload).
- Cards now show draft text + Draft/Notes badges; search includes internal notes.

### ALL ARCHIVE — folder view
- Left **Folders** panel on All Reels tab: All, Root, and nested subfolders from `REELS_FOLDER` with counts.
- Cards show folder path label.

### Quick Look
- **ScanEye** button on each card → full-screen overlay, **audio on**, Esc to close.
- Hover preview unchanged (muted in-card).

### Thumbnails (iCloud)
- On-demand iCloud download + macOS `qlmanage` fallback before ffmpeg.
- `POST /api/reels/thumbnails/backfill` + per-reel `POST /api/reels/{id}/thumbnail`.
- Auto backfill on dashboard load; Quick Look triggers thumb gen for missing files.

### Batch Gemini analysis
- **Select Reels** mode → multi-select → **Generate AI Analysis**.
- Client-side queue: one reel at a time, 2.5s gap; bottom-right queue panel with status.
- Single sparkle button adds to same queue.
- Backend: iCloud prefetch before analyze (120s timeout).

### Ops
- Localhost stopped (ports 8000 / 5173). All saved metadata persists in `data/reelvault.db`.
- Restart: `./start.sh` → http://localhost:5173

### Key files touched
- `frontend/src/App.tsx`, `frontend/src/folders.ts`, `frontend/src/useAnalysisQueue.ts`, `frontend/src/api.ts`
- `backend/app/models.py`, `scanner.py`, `thumbnails.py`, `icloud.py` (new), `routes/reels.py`
