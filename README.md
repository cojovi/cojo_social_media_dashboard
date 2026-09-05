# ReelVault

A local video archive for finding something worth posting, drafting its caption, and maintaining an approved social queue. React/Vite, FastAPI, SQLite, and a Python CLI share the same catalog. Source videos stay in their existing folders; thumbnails, descriptions, notes, and captions stay on the local SSD.

## Daily workflow

1. Add videos anywhere under `REELS_FOLDER`, including subfolders.
2. Start `./start.sh`. The backend scans at startup and every fifteen minutes while it runs. The dashboard refreshes every ten seconds; **Rescan Folder** also works immediately.
3. Stable new files are indexed and queued for **quick descriptions** automatically, along with the existing undescribed backlog. Empty files and files modified in the last 60 seconds wait for a later scan.
4. Search by subject, quick tags, description, filename, caption, or notes. Filter by folder and local/offloaded/missing status. The grid initially renders 60 cards; **Show 60 more** expands it.
5. Play a promising video using Quick Look, or open its workbench and press Play. Editing and hovering do not preload the video.
6. Request **Full video review + captions** when you need audio/context and posting suggestions. Write or adopt a final caption and mark it ready.

Only `ready` + `approved` + nonblank final caption + source not marked missing enters the ready queue. Nothing publishes to social platforms automatically.

## Two different AI workflows

| Workflow | Input | Default model | Purpose |
|---|---|---|---|
| Quick description | Three 384px stills from a local video; one cached thumbnail if offloaded | `gemini-2.5-flash-lite` | One rough sentence, category, search tags; no audio |
| Full review | Original video and audio uploaded through Gemini Files API | `gemini-2.5-flash` | Detailed summary, caption, hashtags, platform and review notes |

Quick descriptions are stored in separate `quick_*` fields and never modify your draft, final caption, approval, or full AI suggestions. They run through a SQLite queue, resume after a backend restart, and can be paused under **Settings → Archive automation**. The existing full-review selection queue is browser-based: keep its tab open until it finishes.

Offloaded videos with cached thumbnails can be described without a download. Those without a preview wait in **waiting for a local preview**, then retry periodically. Download that specific file in Finder or use Quick Look when you want it processed. Automatic scans and quick descriptions never request cloud downloads, move originals, delete originals, or evict them. Finder/cloud software still manages which originals remain local.

Settings shows scan results, storage counts, queue progress, errors, and estimated API usage. **Describe missing / retry** queues unfinished work; **Pause descriptions** takes effect after the current request. The default quick-description estimate limit is $1 per UTC day. It is not a Google account spending cap and excludes full reviews; actual billing and rate limits are set by your API project.

See [the storage and cost design notes](ARCHIVE_DESIGN.md) for provider recommendations, price calculations, limitations, and the measured pilot.

## Setup

Use Python 3.10+ and a Node version supported by the installed Vite release (the verified workstation runtime is Node 26). Install FFmpeg for local frame extraction; cached-thumbnail descriptions work without it.

```bash
python -m pip install -r backend/requirements.txt
npm ci --prefix frontend
# For a NEW setup only; preserve an existing .env and its API key.
cp .env.example .env
# Set REELS_FOLDER and optionally GEMINI_API_KEY in .env.
./start.sh
```

The dashboard is at [127.0.0.1:5173](http://127.0.0.1:5173). The API is at [127.0.0.1:8000](http://127.0.0.1:8000/docs). On this workstation, requirements are installed in the Miniconda `python`; the launcher discovers it.

Without a Gemini key, browsing, scans, editing, and approvals work normally. Cloud downloads require the relevant provider to be running and signed in. macOS dataless-file detection works without PyObjC; an optional installed Foundation bridge can request iCloud downloads explicitly. Playback otherwise uses a bounded child process to trigger the provider's normal read/download behavior.

Configuration lives in `.env`; see [.env.example](.env.example). Relative paths are anchored at the repository root. The existing iCloud `SnapIGTik Download` folder is auto-detected only when `REELS_FOLDER` is omitted. An unavailable configured source is reported as an error and is never silently recreated.

## Data and recovery

- `data/reelvault.db`: catalog, editorial work, descriptions, durable jobs, recorded AI usage.
- `data/thumbnails/`: small cached previews used while originals are offloaded.
- `data/backups/`: automatic SQLite backups made before additive schema migrations of populated databases.
- `data/reelvault.worker.lock`: process lock preventing duplicate background workers.

SQLite uses WAL and a busy timeout. Missing or moved source files retain their IDs, captions, and notes. Changing a file's contents clears its cached quick description and thumbnail reference for regeneration; manual text and historical full analysis are retained. File identity still depends on absolute path: moving or renaming originals creates new records. Do not migrate the source tree merely by changing the path if you want to retain identities; plan a catalog relink first.

Back up the database with SQLite's backup API while running; do not copy only the `.db` file while WAL writes are active. To restore a migration backup, stop the backend and CLI writers, preserve the current `.db`, `-wal`, and `-shm` files, and restore the chosen backup to `DATABASE_PATH` before restarting. A restart reapplies supported additive migrations. Source videos are never part of these database backups.

## CLI

```bash
python cli/reelctl.py scan
python cli/reelctl.py list
python cli/reelctl.py show 123
python cli/reelctl.py set-post 123 "Final caption"
python cli/reelctl.py set-hashtags 123 "#roofing #dallas"
python cli/reelctl.py status 123 ready
python cli/reelctl.py analyze 123
python cli/reelctl.py describe-missing
python cli/reelctl.py describe-missing --retry
python cli/reelctl.py archive-status
python cli/reelctl.py pause-descriptions
python cli/reelctl.py pause-descriptions --resume
python cli/reelctl.py next-ready
python cli/reelctl.py export-ready --format json
```

`describe-missing` queues work for the running backend. `scan` alone indexes metadata. `archive-status` and `export-ready` produce JSON for agents. The web API exposes equivalent archive controls under `/api/archive` and the posting queue at `/api/queue/ready`.

## Verification

```bash
PYTHONPATH=backend python -m pytest backend/tests -q
npm run build --prefix frontend
npm run lint --prefix frontend
```

Tests isolate their database, source folder, and API settings. Keep the app on loopback: it is a personal local tool, without multi-user authentication. Cloud API adapters, automatic eviction, social scheduling/publishing, and rename-aware catalog relinking remain future work.
