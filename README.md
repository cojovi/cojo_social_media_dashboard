# ReelVault

**`vmtest` now supports a private VM deployment with Dropbox storage, bounded
on-demand caching, browser login, and a versioned agent API.** Start with
[VM deployment & Dropbox setup](VM_DEPLOYMENT.md) and [Agent API](AGENT_API.md).
Open the hosted dashboard from a Tailscale-connected device at
[ReelVault](https://cmac-bolt-data-vm.tail8e0a20.ts.net:8443/) using your existing
owner token. No SSH tunnel or Vercel deployment is required.
The Mac local-mode workflow below remains supported. The VM is a separate catalog;
verified quick descriptions and thumbnails were imported without changing the Mac
database or originals. Historical editorial metadata is not yet migrated.

A local video archive for finding something worth posting, drafting its caption, and maintaining an approved social queue. React/Vite, FastAPI, SQLite, and a Python CLI share the same catalog. Source videos stay in their existing folders; thumbnails, descriptions, notes, and captions stay on the local SSD.

## Daily workflow

**Posting agents:** Give your agent [AGENT_API.md](AGENT_API.md), its agent bearer
token, and an authorized social-platform connection. It reads `/api/v1/queue/ready`,
claims a reel, downloads the approved revision, publishes externally, and confirms
success through `/api/v1/publications/{id}/complete`. Completion moves the unchanged
Ready reel to Posted automatically. The deployed guide is available to agents at
`GET /api/v1/guide`. Agents cannot approve their own drafts or directly edit captions.

**Folder browsing:** Home shows only videos directly in `SnapIGTik Download`.
Open an organizational folder using its tile or the folder sidebar; breadcrumbs
take you back up. Each view excludes descendants. Opening another folder clears
search/filter selections after saving the current workbench. Workflow queues
(Drafts, Ready, Posted, etc.) still span all folders and label that scope explicitly.

**Exact copies:** Dropbox files with the same content hash and byte size share one
grid card by default. The **exact copies · View** button lists every copy and
location, with an **Open** action for each independent record. Uncheck **Group exact
copies** to see individual cards. Grouping happens after folder/search/status
filtering, never deletes files, and never merges notes, captions or approvals.
Similar previews, different encodings/edits, and files without a trustworthy hash
are not automatically grouped. Folder navigation is based on indexed video folders;
empty or image-only directories do not yet appear.

**Moves, renames and deletions:** Dropbox rescans fetch a fresh recursive metadata
listing at startup, every 15 minutes, and when you click **Rescan Folder**. Moves
and renames within the configured archive keep the same reel ID, descriptions,
captions and notes. Deleted files and files moved outside the archive disappear
from normal grids, folder counts and copy lists. Their saved records remain under
**File availability → Missing files (history)**. Once a scan completes, the grid
and folder navigation refresh together. Changes in the desktop Dropbox folder
must finish syncing to Dropbox before the hosted dashboard can see them.

1. Add videos anywhere under `REELS_FOLDER`, including subfolders.
2. Start `./start.sh`. The backend scans at startup and every fifteen minutes while it runs. The dashboard refreshes every ten seconds; **Rescan Folder** also works immediately.
3. Stable new files are indexed and queued for **quick descriptions** automatically, along with the existing undescribed backlog. Empty files and files modified in the last 60 seconds wait for a later scan.
4. Search by subject, quick tags, description, filename, caption, or notes. Filter by folder and local/offloaded/missing status. The grid initially renders 60 cards; **Show 60 more** expands it.
5. Click **Preview** on a card for a small, silent sample, then **Open full video with audio** for complete playback. Quick Look and workbench Play also play the original. Editing and hovering do not preload videos.
6. Request **Full video review + captions** when you need audio/context and posting suggestions. Write or adopt a final caption and mark it ready.

Only `ready` + `approved` + nonblank final caption + source not marked missing enters the ready queue. Nothing publishes to social platforms automatically.

## Small video previews

Each preview is an H.264 MP4, at most 360px on its longest side, 15 fps and 1 MB.
Longer videos show three three-second samples; videos up to nine seconds play
continuously. The card labels these as sampled, with no audio. Only the selected
preview plays; closing it, switching views, scrolling it away or hiding the tab
stops playback. An unavailable preview offers retry and explicit full playback.

The server generates missing previews serially, with a ten-second rest between
clips, and discovers new catalog entries every minute. Clicked reels take priority,
then already-cached originals (including newly described reels). No AI calls are
made. Dropbox originals pass through the existing 5 GB temporary cache; scans and
hovering remain metadata-only. Local automatic work never hydrates placeholders.

**Settings → Cloud storage & VM → Small video previews** shows counts, bytes,
errors/capacity status and a persistent backfill pause/resume control. Generation
continues with the dashboard closed. `data/previews` has its own 1 GB budget,
including a 5 MB temporary encoding reservation. Exact Dropbox copies share a clip.
Backfill waits when full; an explicit Preview request can evict an unused clip.
Evicted clips stay evicted until requested, avoiding an endless regeneration loop.
Renames preserve previews; changed/missing sources invalidate them on reconciliation.
`AUTO_PREVIEWS`, `PREVIEW_MAX_BYTES`, and `PREVIEW_DELAY_SECONDS` configure this;
durable workers require `VM_JOBS_ENABLED=true` and ffmpeg/ffprobe on the server.

## Two different AI workflows

| Workflow | Input | Default model | Purpose |
|---|---|---|---|
| Quick description | Three 384px stills from a local video; one cached thumbnail if offloaded | `gemini-2.5-flash-lite` | One rough sentence, category, search tags; no audio |
| Full review | Original video and audio uploaded through Gemini Files API | `gemini-2.5-flash` | Detailed summary, caption, hashtags, platform and review notes |

Quick descriptions are stored in separate `quick_*` fields and never modify your draft, final caption, approval, or full AI suggestions. They run through a SQLite queue, resume after a backend restart, and can be paused under **Settings → Archive automation**. Full reviews now submit durable server jobs. Submitted work continues after closing the tab; keep the tab open to submit the rest of a browser selection list.

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

Tests isolate their database, source folder, and API settings. Keep local mode on loopback. Hosted mode requires `AUTH_REQUIRED=true`, distinct owner/agent tokens, and the deployment safeguards in [VM_DEPLOYMENT.md](VM_DEPLOYMENT.md). Dropbox identity-aware scanning and cache eviction are implemented; multi-user accounts, social scheduling/publishing and historical catalog relinking are not.
