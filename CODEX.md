# September 8, 2026 — Small browsing previews

- `backend/app/previews.py`: durable serial ffmpeg worker, 9-second silent sampled H.264 clips at 360px/15fps, <=1 MB per clip; 1 GB separate budget including 5 MB scratch reservation. No paid AI calls.
- Automatic metadata reconciliation every minute; explicit requests first, then cached originals. Dropbox generation uses the existing verified/pinned 5 GB cache; local automatic generation never hydrates placeholders. Exact hash/size copies share an asset. Editorial metadata is never changed.
- Automatic backfill waits at capacity; explicit requests can evict unused LRU clips. Evicted assets are not automatically regenerated. Response pins, revision fences, free-disk reservations, failed-work cleanup and restart recovery protect the cache.
- `ReelPreview.tsx` mounts only on click; one inline player, loading/retry/close/full-original actions, no hover/preload downloads, stops on filter/navigation/scroll-away/tab hiding. StoragePanel shows progress, bytes and persisted pause/resume. Small-screen navigation uses a select instead of the fixed sidebar.
- `/api/v1/reels/{id}/preview` GET and `/preview/video?key=...` are agent-readable. Generation POST and `/api/v1/previews/pause` are owner-only. AGENT_API.md explicitly prohibits publishing the sampled preview in place of the claim revision's full download.
- Settings: `AUTO_PREVIEWS=true`, `PREVIEW_MAX_BYTES=1000000000`, `PREVIEW_DELAY_SECONDS=10`. Previews live at DATABASE_PATH.parent / `previews`; VM_JOBS_ENABLED controls worker startup.
- Deployed image `52ea0fed61baa4585a0163a82259a69b4f82b4853b13c47236a5de59983fdf53`; rollback `reelvault:vmtest-before-previews`; database backup `data/backups/reelvault-before-previews-20260908.db`. The live guide checksum is `68b71a170bbbb247a2942962af1b1c1ca00d1367a0cbd194e73306933585f786`.
- At first verification the 1,300-record catalog mapped to 1,239 eligible shared preview assets: 1 ready, 1,238 queued, no failures. Reel 1300 produced a silent 360px H.264 clip, 9 seconds and 152,550 bytes, from a 116,583,852-byte original. Agent range delivery passed. Editorial fields and all five publication records exactly matched the backup; the 15-minute scan interval and original 5 GB budget remain intact. Backfill continues independently of browser sessions.
- 98 backend tests passed both locally and in the Linux image; 13 frontend unit tests, build and lint passed. Chrome rendering/interaction checks used isolated synthetic media at localhost:18771 (1440x1050, 900x1100, 390x844), with no runtime errors. Browser plugin was unavailable; regular Playwright was used on the isolated fixture. Test screenshots/scripts are outside the repo at `/private/tmp/reelvault-preview-qa`. Live verification was API/media inspection, not a browser run against the private hosted URL. Safari remains unverified.
- Final private HTTPS verification from the Tailscale VM host confirmed frontend asset `index-BO9XmtJw.js` and the new storage API: 10 previews ready using 2,290,669 bytes, 1 processing, 1,228 queued, no capacity block. Docker's resolver cannot resolve the private MagicDNS name; use the VM host or a tailnet-connected client for HTTPS checks, and container loopback for internal service checks. The isolated local QA server was stopped; live backfill remains running.

# September 7, 2026 — Agent Ready → Posted handoff

- `/api/v1/queue/ready` is agent-readable and shares the dashboard's strict readiness predicate. Keyset pagination and optional platform/account filters support quick selection without reading video bytes.
- `/publications/{id}/complete` atomically records the external receipt and changes an unchanged Ready reel to Posted with its first `posted_at`. Repeated completion is safe. Late receipts preserve newer caption/media/workflow changes and return `reel_status` for explicit review.
- The agent still publishes through its own authorized external platform connection. It cannot approve/edit drafts or blindly retry uncertain uploads.
- `AGENT_API.md` now documents the complete workflow, eligibility, pagination, snapshot downloads, idempotency/lease recovery and status transition. The Docker image includes this file; `/api/v1/guide` serves the deployed copy with bearer authentication.

# September 7, 2026 — Rescan reconciliation

- Every Dropbox scan reconciles a fresh recursive metadata snapshot, including manual refresh jobs and the startup/15-minute worker. Successful scans repair stale paths/missing records; failed listings leave the catalog intact.
- Provider IDs preserve editorial metadata, summaries and completed description jobs across moves/renames. Scan results report moved/renamed counts.
- The dashboard list API defaults to available files. Missing entries remain addressable by ID and through `availability=missing`; the library index carries storage status so normal folder counts and copy lists exclude missing history.
- File visibility changes only after Dropbox has synced them. iCloud is a separate source from the hosted Dropbox archive.

# September 5, 2026 — Folder-first browsing and non-destructive exact copies

The private Tailscale VM now serves the folder-navigation update on `vmtest`.
**Home is `SnapIGTik Download`, not a recursive all-archive grid.** The Dropbox
source wraps that folder one level below `/Cody Viveiros/SnapTik_Reel_Archive`;
the local Mac source can already be the home folder itself. The frontend derives
the correct home from the unfiltered catalog index without modifying storage paths.

Each folder view shows only files directly inside it. Organizational folders have
clickable tiles, a desktop folder sidebar, direct unique-reel counts and breadcrumb
navigation. Intermediate folders with no directly indexed videos still expose their
children. Opening a different folder clears filters and selection after saving the
current workbench; a failed save prevents navigation. Search does not remove folder
navigation. Drafts/Ready/Posted and other workflow queues intentionally retain their
archive-wide scope, explicitly labeled in the UI; their sidebar counts include copies.

**Duplicate handling is presentation-only.** Only non-empty Dropbox files with a
valid matching content hash and size are grouped. The grid groups after applying
folder/search/status filters, so a copy remains available in every folder where it
exists. The shorter filename is the stable representative (lowest ID breaks ties).
The `exact copies · View` button opens an accessible native dialog listing every
record/location, including copies outside current filters, with an Open action.
Unchecking `Group exact copies` restores individual cards. Notes, captions, approvals,
descriptions, originals and database IDs are never merged or deleted. The raw/agent
APIs continue returning separate records. Similar previews, different edits/encodings,
local/unhashed media and empty files are not automatically grouped.

Implementation: `frontend/src/folders.ts` builds memoized folder/copy indexes;
`FolderNavigation.tsx` renders folder tiles, sidebar and breadcrumbs;
`DuplicateCopiesDialog.tsx` exposes individual copies; `App.tsx` integrates these
with filtering, selection, autosave and the existing workbench. A read-only,
owner-authenticated `GET /api/reels/library` returns a lightweight unfiltered
identity index without captions/notes or cloud downloads. `ReelResponse` now includes
`content_hash`, matching the existing database and versioned API identity fields.
No database migration or new dependency was necessary.

Live catalog verification: 1,278 records; 39 non-empty exact-copy groups containing
42 additional copies across the archive. Three zero-byte records (IDs 14, 16, 17)
were excluded from grouping. Home has 1,039 files → **1,032 unique cards**, with all
239 subfolder files excluded. `artistic/tv` has 23 files → 20 cards. IDs 1204/1205/1206
share one card represented by `Number.mp4` (1205), while the distinct 46-minute
video (1207) stays separate. Cross-folder pairs 1161/1162 and 1202/1203 retain their
respective folder memberships and appear in each other's copy list.

Verification: **68 backend tests passed locally and in the deployed Linux image;
11 frontend unit tests, production build, ESLint and whitespace checks passed.**
Read-only private HTTPS checks used the actual deployed catalog with the frontend's
folder/grouping functions, confirmed the new asset bundle, checked anonymous index
denial (401), and confirmed Dropbox connected/Gemini configured. These are API/logic
checks, not rendered browser proof: browser automation was denied because its
admin-policy verification was unavailable. No bypass or alternate browser driver
was used. See the latest section of `VM_TEST_RESULTS.md` for remaining visual checks.

The prior VM image is retained as `reelvault:vmtest-before-folder-browser`; only the
named ReelVault container was restarted. The same owner token remains valid, but
in-memory browser sessions expire on restart. The Tailscale endpoint and all private
storage/auth/cache configuration are unchanged. At verification, 1,269 descriptions
were present; no additional Gemini requests were explicitly triggered by these checks.

Known limits: navigation currently represents **indexed video folders**, not empty
or image-only directories. There is no visual/perceptual duplicate detector and no
physical storage cleanup in this change. Browser-rendered acceptance remains pending.
The branch remains uncommitted and unpushed.

# September 5, 2026 — Tailscale-only access and description recovery

The selected deployment is now **private Tailscale HTTPS, not Vercel or public hosting**:
`https://cmac-bolt-data-vm.tail8e0a20.ts.net:8443/`. Persistent Tailscale Serve proxies
to VM loopback `127.0.0.1:18765`; Funnel is not enabled and the existing public-port
services were not changed. Tailscale must be connected on the viewing device, but
the Mac and its SSH tunnel no longer need to be running. Existing tailnet ACLs apply.
`PUBLIC_ORIGIN` is the exact private HTTPS origin; cookies are Secure/HttpOnly/Strict.
Owner and agent tokens are unchanged. The old HTTP localhost address is no longer
the browser login URL. See [VM_DEPLOYMENT.md](VM_DEPLOYMENT.md) for current operations.

The missing quick descriptions were a catalog-migration gap, not lost Gemini work.
The old Mac catalog has 1,405 descriptions and 1,411 thumbnail references across
1,626 records; six summary jobs had failed and 212 were waiting for local previews.
Dropbox indexing created independent VM records with different IDs. The new
`deploy/export_mac_descriptions.py` and `backend/app/catalog_import.py` safely
reconcile root-relative paths, sizes and source modification times; verify content
hashes for already-resident files; skip uncertain matches; and import only derived
descriptions/thumbnails with destination revision guards and a pre-import SQLite backup.

Recovery added **1,031 descriptions and 1,037 thumbnails**, preserving 128 existing
matched VM descriptions and all VM editorial/provider fields. After import there
were **1,165 described of 1,278 reels**, 111 queued and two failed. Gemini was paused
during reconciliation, then resumed for remaining missing descriptions under the
existing $1/day quick-summary estimate limit. No paid AI calls were needed for the
import itself. The Mac database and all original videos were left unchanged.
The two failed jobs (VM IDs 1213 and 1257) received empty Gemini responses after
three attempts; they remain flagged rather than being assigned invented descriptions.
Original Mac captions, notes, approvals, full AI analyses and usage history were not
copied; their reconciliation remains a separate editorial migration.

Backup: VM `data/backups/reelvault-before-mac-descriptions-20260906T031545765358Z.db`.
The approximately 57 MB manifest/thumbnail bundle is in `data/imports/mac-20260906/`,
outside Git. All 65 backend tests passed locally and in the VM image. Live HTTPS
API checks verified owner login, Secure cookies, denied foreign origins, three
restored summary/thumbnail samples, all highlighted screenshot IDs, private thumbnail
protection after logout and agent range downloads. Browser-rendered follow-up checks
were blocked by the browser tool's unavailable admin-policy check; no bypass was used.

The earlier notes below describe the preceding implementation/testing stages and
are superseded by this section wherever access URLs or migration status differ.

# September 5, 2026 — Earlier `vmtest` hosted Dropbox edition

This is now a **single-owner VM test build**, not yet a publicly exposed production
service. The React dashboard is served by FastAPI, with a separate agent token and
browser login. The VM test catalog is separate from the existing Mac archive.
Read [VM_DEPLOYMENT.md](VM_DEPLOYMENT.md) for deployment and the one-time Dropbox
setup, and [AGENT_API.md](AGENT_API.md) for the exact agent contract. These sections
supersede storage/auth/deployment claims in the older historical reviews below.

## What changed and where

| Area | Files | Responsibility |
|---|---|---|
| Configuration | `backend/app/settings.py`, `.env.example`, `deploy/bootstrap.py` | Local/Dropbox modes, resource limits, private deployment configuration |
| Authentication | `backend/app/auth.py`, `frontend/src/AuthGate.tsx` | Owner browser sessions, separate restricted agent token, origin checks, login throttling |
| Dropbox | `backend/app/dropbox_storage.py` | Read-only PKCE/offline OAuth, team root namespace, recursive incremental metadata scans, exact-revision downloads |
| Cache | `backend/app/media_cache.py` | Exclusive process owner, five transfers, reservations, pins, LRU/TTL, byte count and content-hash verification |
| Durable jobs | `backend/app/jobs.py` | SQLite queue; five materialization workers, separate serial heavy-work worker and scan worker; restart recovery |
| Agent API | `backend/app/routes/v1.py`, `AGENT_API.md` | Keyset-paginated discovery, downloads/jobs, per-platform/account publication claims and receipts |
| Database | `backend/app/database.py` | Additive schema v2; provider IDs/revisions, transfer jobs, cache ledger, publication attempts; backup before populated migration |
| Integration | `archive.py`, `quick_summary.py`, `routes/reels.py`, `gemini_service.py`, `main.py` | Existing UI/editor/AI workflows use managed media; built frontend serving; source-version checks on analysis results |
| VM UI | `frontend/src/StoragePanel.tsx`, `api.ts`, `App.tsx` | Connection wizard, disk/cache status, persisted job results, polling instead of long UI-owned requests |
| Packaging | `Dockerfile`, `.dockerignore`, `backend/requirements-vm.txt`, `deploy/run-vmtest.sh` | Non-root isolated container; loopback port; persistent data; resource/log limits |
| Verification | `backend/tests/test_vm.py`, `frontend/tests/vm-smoke.mjs`, `deploy/seed_qa.py` | Cache/auth/sync/claims tests and actual browser verification using isolated synthetic media |

## Data flow and invariants

Mac downloads → Dropbox desktop upload → Dropbox cloud metadata → VM SQLite catalog.
Only explicit playback/download/processing fetches an original into the VM cache.
Scanning never downloads the entire archive. Quick descriptions in Dropbox mode
**can** download selected/queued videos through the bounded cache. The current VM's
automatic quick summaries are enabled with the existing $1/day application estimate
limit; fresh bootstrap environments start disabled until credentials are configured.
Local/iCloud mode retains its no-auto-hydration behavior.

- Default VM media policy: five downloads, 5 GB total reserved media, 12-hour idle
  expiration, 5 GB minimum free disk. Thumbnails/database/container images are not
  part of that media budget; overall free-disk checks remain necessary.
- Cache eviction never deletes originals. Responses and processing pin their cached
  files until finished; partial files are not served. No direct unleased cache paths
  are handed to agents.
- Dropbox file ID—not pathname—is identity. Moves retain editorial data. Replacing
  contents invalidates derived previews and approval for the new revision; manual
  text and historical full analysis are retained. Local records still use paths.
- Page failures never advance the Dropbox cursor or mark unseen files missing.
- All hosted APIs, thumbnails and docs require authentication, except minimal
  liveness/login/session checks. Agent scope does not include self-approval, Dropbox
  setup, paid analysis, or legacy mutations. Tokens never go in browser storage.
- Posting is **not implemented against any social platform**. Claims preserve a
  caption/revision snapshot and prevent a second active/completed attempt for a
  reel/platform/account. Ambiguous started attempts become uncertain and require
  external reconciliation. This cannot promise exactly-once external delivery.
- One Uvicorn process owns each cache/database. Threads provide internal concurrency;
  multiple worker processes/replicas sharing this SQLite directory are unsupported.
- Submitted full-analysis jobs survive browser closure. A browser selection list
  not yet submitted still requires that tab; interrupted paid AI jobs need manual review.

## Current stage and remaining acceptance

Core hosted implementation, container packaging, and automated VM-specific tests are
present. Owner credentials are generated privately outside Git. The test listener is
loopback-only and accessed over SSH; public DNS/HTTPS/ingress is deliberately not set up.
The new frontend tooling dependency audit is clean after compatible security updates.
Verification: 58 backend tests passed locally and in the VM image after the live
Dropbox revision-download and loopback-origin fixes. The initial build/lint, synthetic playback and restart
checks are recorded in [VM_TEST_RESULTS.md](VM_TEST_RESULTS.md); the real-account
acceptance below supersedes that initial report's pending-authorization status.

The selected Dropbox archive is `/Cody Viveiros/SnapTik_Reel_Archive`, corresponding
to the user's `Dropbox-CMACRoofing` Mac folder. OAuth is now connected. Live acceptance
on September 5 CDT (September 6 UTC) verified 1,278 indexed records and incremental
discovery of additional uploads. Five real downloads totaling 56,199,816 bytes ran
concurrently (observed peak five), passed content-hash checks, and completed in about
5.2 seconds. All five authenticated range-download requests returned the expected bytes.

The live API rejected the deprecated separate `rev` download argument with HTTP 400.
The adapter now sends `path: "rev:<revision>"`, still validating the returned file ID
and revision before accepting bytes. Regression tests cover the current wire format
and rejection of a wrong file/revision. The fix is deployed on the VM.

Real Chrome checks (1440×1000) passed owner login, connected storage UI, search,
12.6-second reel playback, restricted-agent range download, no browse-time media
preload, and zero console/page errors. A separate 1.2 GB, 46-minute archive video
exceeded the initial 30-second cold-playback test wait; it played correctly after
caching. Cold playback currently waits for the complete verified download, so large
files have startup latency. Do not describe this as streaming directly from Dropbox.
After testing: six cached files, 1.256 GB of the 5 GB media limit, approximately
20.69 GB free disk, no active transfers or reader pins. Old failed test jobs remain
in history; new requests succeeded. No Dropbox originals or editorial fields were changed.

The original Mac database was read only for an aggregate check: 1,626 catalog
records, three final captions, one record with notes. No original files, editorial
data, credentials, or database were copied into the VM test catalog. Historical
catalog relinking is not automatic and remains a separately reviewed migration.
Gemini was initially left unconfigured during deployment testing; this was corrected
on September 5 CDT using the existing Mac project's key, transferred privately into
the VM's 0600 environment file. Full AI uses `gemini-2.5-flash`; automatic visual quick
summaries use `gemini-2.5-flash-lite`. A real reel description succeeded (904 input,
56 output tokens; $0.0001128 application estimate) before automatic queueing was
enabled. The $1/day quick-summary estimate guard is unchanged, and is not a provider
billing cap or a budget for user-triggered full-video analyses.

The owner's `localhost:18765` tab revealed an overly strict origin comparison against
`127.0.0.1:18765`. The guard now allows only equivalent loopback hostnames at the
configured scheme/port. Null/unrelated origins, other ports/schemes, and arbitrary
Host/forwarded-host headers cannot expand that list. Public HTTPS configurations
continue to use one exact origin. Live owner login requests succeed for both local
addresses, with the existing token unchanged. Browser sessions expire on restart.
Rendered follow-up verification was blocked by the browser tool's unavailable
admin-policy check; no alternate-browser bypass was attempted. Earlier rendered
checks above remain historical evidence, not proof of this follow-up browser run.

Remaining production work includes a domain/TLS decision, credential rotation,
scheduled off-VM backups, sustained real-account load testing, dependency update
policy, and any historical catalog migration. This is intentionally a personal-use
beta, not multi-tenant SaaS or a complete social scheduler.

---

# September 4, 2026 archive upgrade — historical local-mode behavior

Read [README.md](README.md) for operation and [ARCHIVE_DESIGN.md](ARCHIVE_DESIGN.md) for the review, storage recommendation, pricing, and limitations. The August review below is retained as a historical baseline and no longer describes all current behavior.

Current architecture additions:

- `backend/app/archive.py`: backend-owned startup/periodic scan loops, a SQLite quick-description queue, process lock, crash leases, retry/backoff, pause, and estimate limits.
- `backend/app/quick_summary.py`: three small local frames or one cached thumbnail; visual-only labels via Flash-Lite; no automatic hydration.
- `backend/app/usage.py`: recorded input/output/thinking tokens and model-specific paid-tier estimates. Old calls are not retroactively costed.
- `backend/app/routes/archive.py`: archive status, queue missing/retry, pause/resume.
- `frontend/src/ArchivePanel.tsx`: storage, scan, queue and usage visibility.
- Database: explicit additive migration with backup of populated pre-upgrade databases, WAL, busy timeout, foreign keys for job deletion, `summary_jobs`, `ai_usage`, `archive_state`, and per-reel storage/quick-description fields.

Operational invariants:

- Preserve manual captions, final captions, notes, and approval during scans and AI work.
- Scan only metadata. Never hydrate all sources for discovery or thumbnail backfill.
- Do not silently create a missing configured source folder.
- A partial/failed scan must not mark its unseen entries missing.
- Quick descriptions must identify their evidence source; a thumbnail description is not a full video review.
- Missing files retain catalog history. Absolute path remains the identity; provider migration needs deliberate relinking.
- Quick jobs survive browser/backend restarts. The older **full video review** selection queue still requires its browser tab to stay open.
- The quick daily limit is an app estimate limit, not an account billing cap. No automatic fallback to a more expensive model.
- The source can stay in iCloud; no files have been moved or automatically evicted. Direct Dropbox/Drive API cache adapters are future work.
- Main source on this Mac: iCloud `SnapIGTik Download`. Defaults scan at startup and every 900 seconds (15 minutes), settle new writes for 60 seconds, and automatically queue undescribed backlog/new arrivals. Dashboard refresh: ten seconds.
- Current ready queue additionally excludes files marked missing and rejects whitespace-only captions. PATCH/CLI validation shares the model layer.
- No broad source-folder static mount. Originals are served by reel ID with bounded explicit hydration. Keep the server local; no authentication has been added.

Validation for this upgrade: backend tests include scanning/settling, missing/partial sources, placeholders, unchanged/changed content, cached-thumbnail use, queue leases/deduplication/retries, pause/budget gates, migration preservation, and ready-state rules. Frontend build and lint pass. Browser checks use an isolated QA database to verify search, storage filtering, no automatic video requests, slow-save editing, and pause/resume. A three-request real Gemini pilot succeeded, estimated at $0.0003608 total.

Historical review follows.

---

# ReelVault Codebase Guide

> Last reviewed: August 4, 2026  
> Review basis: all project source and configuration files, all documentation, the live SQLite schema and aggregate contents, binary/media metadata, generated/cache directories, the CLI surface, the FastAPI routes, the frontend production build, ESLint, and the backend test suite.

## Executive summary

ReelVault is a local-first social-video archive and editorial workbench. It indexes video files already stored on disk or in iCloud Drive without copying them, generates cached thumbnails, lets a user draft and approve social captions, optionally asks Google Gemini to analyze videos and propose copy, and exposes a deliberately strict “ready” queue for future posting automation. The same SQLite database is used by a React dashboard, a FastAPI API, and a Typer CLI.

This is not currently a social-network publishing bot. It does not authenticate with Instagram, TikTok, Facebook, YouTube, or LinkedIn, schedule posts, or upload content to those platforms. Its boundary ends at preparing and exposing approved content.

The project is beyond a generated skeleton and is being used with real data. It is best described as a functional, local, single-user MVP with several post-MVP usability additions. The core archive/edit/approval path works and is tested; the frontend builds; the database is healthy and populated. It is not production-hardened, packaged, or ready for multi-user or network-exposed use.

## What problem it solves

The intended workflow is:

1. Point ReelVault at an existing tree of reel/video files.
2. Recursively index supported files in SQLite without moving or duplicating them.
3. Browse, search, filter, preview, and organize the archive.
4. Save a manual caption, hashtags, internal notes, status, and approval state per reel.
5. Optionally upload one reel at a time to Gemini for a summary, suggested caption, hashtags, category, and platform recommendation.
6. Explicitly copy AI suggestions into user-controlled fields; AI output never automatically replaces manual copy.
7. Expose only records satisfying all three publishing gates:
   - `status = 'ready'`
   - `approved = true`
   - `final_post_text` is non-empty
8. Allow a future agent or integration to read that safe queue through the API or CLI.

The visual product is a dark synthwave/retro-arcade dashboard. `Color_Scheme.png` is the palette reference only: deep plum/black, cyan, magenta, orange, and purple glow. The implementation intentionally avoids reproducing the reference image's dense fake analytics layout.

## Current stage and observed state

### Stage assessment

**Current stage: functional personal-use MVP / early beta.**

Evidence that it is functional rather than merely scaffolded:

- The backend has real scanning, persistence, thumbnail generation, iCloud-aware hooks, AI integration, validation endpoints, and tests.
- The frontend has a complete archive browser and workbench, not a starter screen.
- The CLI implements the documented agent-facing workflow.
- The live database passes SQLite's integrity check.
- The frontend production build succeeds.
- All six backend tests pass under the installed Miniconda Python 3.13 environment.
- The data cache shows sustained use against a large personal reel collection.

Evidence that it remains MVP-level:

- There is no root Git repository/history in this workspace, no root `.gitignore`, and no release/deployment pipeline.
- The frontend is concentrated in a 1,470-line `App.tsx` rather than decomposed into tested components.
- ESLint currently reports 12 errors and 4 warnings.
- The backend has no migrations, pagination, authentication, job system, or stale-record reconciliation.
- Operational documentation is partially stale and some Vite starter artifacts remain.
- The app assumes a trusted local machine and should not be exposed to a LAN or the public internet.

### Live data snapshot on August 4, 2026

The checked-in/local `data/reelvault.db` currently contains:

| Measure | Observed value |
|---|---:|
| Indexed reels | 1,415 |
| `.mp4` records | 1,401 |
| `.mov` records | 14 |
| Total referenced video size | about 19.4 GiB |
| Draft status | 1,412 |
| Ready status | 3 |
| Approved records | 4 |
| Manual drafts | 4 |
| Final posts | 3 |
| Records with notes | 1 |
| Gemini-analyzed records | 3 |
| Postable records | 3 |
| DB records with thumbnail references | 1,306 |
| JPEG files in thumbnail cache | 1,306 |

The first stored discovery timestamp is May 22, 2026; the newest is August 4, 2026. `PROGRESS.md` records a June 29 recovery at roughly 1,267 reels, but the live database is newer and larger, so the database is the more current source for operational state.

Important data-health observations:

- The database has no duplicate file paths and currently has no record that violates the three-part ready-queue predicate.
- One approved record is still a draft. Approval and readiness are modeled separately, so that is not inherently unsafe; it is excluded from the ready queue.
- 261 database records currently point to video paths that do not exist on disk.
- Five records reference thumbnail filenames that are not present; four thumbnail files are not referenced by any current record.
- The configured source folder currently contains 1,159 supported video files. Of 1,414 database paths under that root, 1,154 currently exist and 260 are stale; one additional stale record points to the workspace's former iCloud location. Five supported files in the source are not yet represented by an existing matching database path. This confirms that scanning adds/updates records but never removes records for deleted or moved files.
- SQLite uses the default `DELETE` journal mode, has no foreign keys (there is only one table), and has only the implicit unique index on `filepath`.

The live database and thumbnail cache are user data, not fixtures. Back them up before any cleanup or migration work.

## Architecture

```text
Existing video tree (currently iCloud Drive)
        |
        | recursive scan; no video copies
        v
FastAPI scanner + ffprobe/ffmpeg/Quick Look
        |
        +--------> data/thumbnails/*.jpg
        |
        v
data/reelvault.db (SQLite, single `reels` table)
        ^                    ^
        |                    |
React/Vite dashboard     Typer/Rich CLI
        |
        +---- optional per-video upload ----> Gemini Files API
                                               |
                                               +-- JSON suggestions saved to AI fields
                                                   and uploaded file deleted afterward
```

The backend is the web application's source of truth. The CLI imports the same backend modules directly and reads/writes the same configured database; it does not call the HTTP API.

### Backend stack

- Python 3.10-3.13 is the documented range; the verified working interpreter is Miniconda Python 3.13.13.
- FastAPI provides the local HTTP API.
- Raw `sqlite3` provides persistence; there is no ORM or migration framework.
- `ffprobe` extracts duration.
- `ffmpeg` and macOS `qlmanage` generate thumbnails.
- `google-genai` implements Gemini Files API upload and multimodal analysis.
- `python-dotenv` loads the root `.env`.

### Frontend stack

- React 19 + TypeScript 6 + Vite 8.
- Tailwind CSS 4 through the Vite plugin.
- `lucide-react` for icons.
- No router or state-management library; the application uses local React state and tab state inside `App.tsx`.
- Vite proxies `/api`, `/videos`, and `/thumbnails` to FastAPI during development.

### Persistence model

`backend/app/database.py` creates a single `reels` table if it does not exist. Each row combines four concerns:

- File identity/metadata: filename, unique absolute filepath, extension, size, duration, timestamps, thumbnail.
- Editorial state: status, approval, manual caption, final caption, hashtags, notes.
- AI state: summary, suggested caption/hashtags, category, platform, analysis timestamp.
- Lifecycle state: posted and archived timestamps.

There are five intended statuses: `draft`, `needs_review`, `ready`, `posted`, and `archived`.

There are no database-level `CHECK` constraints for status or ready-state validity. The ready queue itself is safe because its SQL always re-applies all three gates, even if a malformed record enters the table.

## Repository map

### Root

- `.env` — active local configuration. It may contain a real Gemini key. Never print or commit it.
- `.env.example` — configuration template; presently aligned with the active variable names.
- `README.md` — primary setup and feature guide. Useful, but it predates some later folder, Quick Look, autosave, iCloud, and batch-analysis work.
- `DETAIL.md` — original build specification and acceptance criteria. Treat it as product intent, not a precise description of current code.
- `PROGRESS.md` — June 29 recovery and feature log. It describes the most recent documented development session but is behind the current live database.
- `SESSION_NOTES.md` — May 26 Gemini model migration notes.
- `ChatGPT-Reel Archive Dashboard.md` — exported design conversation and original prompt history. It is provenance/reference material, not runtime documentation.
- `Color_Scheme.png` — 1536×1024 palette/mood reference.
- `cody.txt` — informal startup notes; it contains a typo referring to `stt.sh` even though the real launcher is `start.sh`.
- `start.sh` — local development orchestrator. Loads `.env`, chooses a Python with `uvicorn` and `typer`, starts FastAPI with reload, starts Vite, opens the browser on macOS, and cleans up child processes on exit.
- `.pytest_cache/` and `.DS_Store` files — generated local artifacts with no application role.

### `backend/`

- `app/settings.py` — loads `.env`, anchors relative paths at the project root, cleans shell-escaped paths, and normalizes legacy `gemini-1.5-pro` to `gemini-2.5-flash`.
- `app/database.py` — creates the database directory/table and yields row-dictionary SQLite connections.
- `app/models.py` — all SQL CRUD, filtering, metadata-preserving upsert, ready queue, counts, and missing-thumbnail queries.
- `app/schemas.py` — Pydantic response/update models.
- `app/scanner.py` — recursive video discovery, stat metadata, duration probing, metadata upsert, and thumbnail backfill.
- `app/icloud.py` — optional PyObjC/Foundation checks and on-demand iCloud downloads.
- `app/thumbnails.py` — deterministic hash-suffixed cache names, Quick Look generation, PNG-to-JPEG conversion, ffmpeg fallback, and iCloud prefetch call.
- `app/gemini_service.py` — Gemini upload/poll/analyze/parse/delete lifecycle. It requests structured JSON and preserves malformed text in a fallback result.
- `app/main.py` — app initialization, logging, permissive local CORS, static video/thumbnail mounts, routers, and root metadata endpoint.
- `app/routes/health.py` — environment/health summary.
- `app/routes/reels.py` — scan, stats, list/filter, thumbnail, video, update, AI, and lifecycle endpoints.
- `app/routes/queue.py` — strict ready queue endpoint.
- `tests/` — six tests covering schema creation, nonduplicating scan, field persistence, ready validation, Gemini-offline behavior, and legacy model normalization.
- `requirements.txt` — unconstrained-minimum backend dependencies. There is no lock file.
- `__pycache__/` — generated Python bytecode for 3.13/3.14; not source.

### `frontend/`

- `src/App.tsx` — nearly the entire UI and interaction layer: navigation, filters, cards, preview, editing, autosave, lifecycle actions, folder tree, settings, selection, queue status, Quick Look, and toasts.
- `src/api.ts` — TypeScript API contracts and fetch wrapper.
- `src/folders.ts` — derives a nested folder tree from absolute reel paths and performs client-side subtree filtering.
- `src/useAnalysisQueue.ts` — in-memory sequential Gemini queue with a 2.5-second gap, duplicate prevention, per-item state, and completion reporting.
- `src/index.css` — Tailwind import, theme tokens, fonts, animations, scanlines, global layout, and shared synthwave utilities.
- `src/main.tsx` — React mount under Strict Mode.
- `src/App.css` — unused Vite starter CSS; it is not imported.
- `src/assets/hero.png`, `react.svg`, and `vite.svg` — unused starter assets.
- `public/favicon.svg` and `public/icons.svg` — public SVG assets; the favicon is referenced, while `icons.svg` is not referenced by source.
- `index.html` — Vite shell. Its title is still the generic `frontend`.
- `package.json` / `package-lock.json` — frontend scripts and locked dependency tree. Package name/version are still `frontend` / `0.0.0`.
- `vite.config.ts` — React, Tailwind, port, and backend proxy configuration.
- TypeScript and ESLint configs — strict compilation and modern React lint rules.
- `frontend/README.md` — untouched Vite template documentation, not ReelVault documentation.
- `node_modules/` — installed generated dependencies, about 164 MB.
- `dist/` — generated production build, about 316 KB after the verified build.

### `cli/`

- `reelctl.py` — 396-line Typer/Rich command-line interface. It amends `sys.path` to import `backend/app`, initializes the same database, and implements scan/list/show/edit/approve/status/analyze/queue/export commands.

### `data/`

- `reelvault.db` — active SQLite user database, about 807 KB.
- `thumbnails/` — active JPEG cache, roughly 78 MB and 1,306 files at review time.

### `reels/`

- Contains only the tiny three-second `roofing_before_after.mp4` sample in this workspace.
- It is not the active source while `.env` points `REELS_FOLDER` to the iCloud Drive collection.

## Implemented user experience

### Archive and navigation

The left sidebar exposes All Reels, Drafts, Needs Review, Ready Queue, Posted, Archived, and Settings. Status counts come from the backend. All Reels also has a client-derived folder panel with nested counts and subtree selection.

Search covers filename, full path, manual caption, final caption, hashtags, and notes. Additional filters select records with/without final captions and with/without AI summaries. Status tabs are server-filtered; folder filtering is applied client-side to the returned list.

Each reel card includes a portrait thumbnail, blurred ambient backdrop, duration, status, approval badge, relative folder, caption/notes preview, hashtags, Quick Look, AI action, and conditional Ready action. Hovering replaces the image with a muted looping video stream.

### Workbench and saving

Selecting a reel opens a fixed-width workbench containing video playback, file metadata, status, approval, manual caption, hashtags, internal notes, AI output, final caption, and lifecycle actions.

The editor:

- Fetches a fresh record when opened.
- Tracks a baseline and computes field changes.
- Autosaves approximately 600 ms after edits.
- Saves before closing or switching records.
- Supports Cmd/Ctrl+S.
- Updates the visible card in place and refreshes counts.
- Keeps manual, AI-suggested, and final captions separate.

### Video and thumbnails

The backend recognizes `.mp4`, `.mov`, `.m4v`, `.avi`, `.webm`, and `.mkv`. It recursively walks the configured source, normalizes paths to Unicode NFC, uses absolute filepath as the unique identity, and updates only file metadata on rescan. Editorial and AI fields are preserved.

Duration is reused once nonzero, otherwise obtained through `ffprobe` when the file is believed to be local. Thumbnail names combine the video stem and the first eight characters of an MD5 of the full path, preventing most same-name collisions. Generation tries macOS Quick Look first and ffmpeg at 0.5 seconds then 0.0 seconds.

The dashboard starts an automatic missing-thumbnail backfill once per page load, in batches of 12. It stops when none remain or a batch generates zero. A Quick Look request also attempts a missing thumbnail.

### Gemini analysis

Gemini is optional. With no key the rest of the application remains available, health reports offline mode, and AI controls are hidden or return clear errors.

With a key, the backend:

1. Ensures the selected file is locally available if Foundation support exists.
2. Uploads the file through the Gemini Files API.
3. Polls processing for up to five minutes.
4. Requests JSON using the configured model (`gemini-2.5-flash` in the current environment).
5. Saves the summary, proposed caption/hashtags, category, platform, and analysis time.
6. Deletes the uploaded Gemini file in a `finally` block.

The browser queue is client-side and sequential. It processes one video at a time with a 2.5-second pause, so closing or refreshing the page loses queued work. It is not a durable backend job queue.

The current AI prompt is opinionated toward roofing/construction/home-services marketing unless the video clearly concerns another subject.

## HTTP API

The effective API surface is:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Paths, Gemini state/model, and source-folder state |
| `POST` | `/api/reels/scan` | Synchronous recursive scan/upsert |
| `GET` | `/api/reels/stats` | Counts by workflow status |
| `GET` | `/api/reels` | List with status, approval, search, final-post, and AI filters |
| `POST` | `/api/reels/thumbnails/backfill` | Generate a bounded batch of missing thumbnails |
| `GET` | `/api/reels/{id}` | Fetch one record |
| `PATCH` | `/api/reels/{id}` | Update editable/editor and AI fields |
| `POST` | `/api/reels/{id}/thumbnail` | Generate one thumbnail |
| `GET` | `/api/reels/{id}/video` | Serve one source video by ID |
| `POST` | `/api/reels/{id}/analyze` | Run Gemini analysis synchronously |
| `POST` | `/api/reels/{id}/use-ai-caption` | Copy AI caption into final caption |
| `POST` | `/api/reels/{id}/use-ai-hashtags` | Copy AI hashtags into active hashtags |
| `POST` | `/api/reels/{id}/mark-ready` | Validate final text, approve, and mark ready |
| `POST` | `/api/reels/{id}/mark-posted` | Mark posted and timestamp it |
| `POST` | `/api/reels/{id}/archive` | Archive and timestamp it |
| `GET` | `/api/queue/ready` | Strictly filtered agent-facing posting queue |

FastAPI also exposes `/docs`, `/redoc`, and `/openapi.json`. `/videos` statically mounts the entire configured source tree and `/thumbnails` mounts the cache; the current UI mostly uses the ID-based video route.

The original `DETAIL.md` asks for `POST /api/scan`, but the implemented and frontend-used path is `POST /api/reels/scan`.

## CLI

Run commands from the project root:

```bash
python cli/reelctl.py --help
python cli/reelctl.py scan
python cli/reelctl.py list
python cli/reelctl.py show 123
python cli/reelctl.py set-post 123 "Final caption"
python cli/reelctl.py set-hashtags 123 "#roofing #dallas"
python cli/reelctl.py approve 123
python cli/reelctl.py status 123 ready
python cli/reelctl.py analyze 123
python cli/reelctl.py next-ready
python cli/reelctl.py export-ready --format json
python cli/reelctl.py export-ready --format csv --output exports/ready.csv
```

`status ... ready` requires a final caption and auto-approves. JSON/CSV export includes every database column for records in the strict queue. Rich's presentation makes most commands human-friendly; `export-ready` is the cleanest machine-readable command.

## Configuration and startup

Supported root environment variables:

| Variable | Meaning | Current/default pattern |
|---|---|---|
| `REELS_FOLDER` | Existing source video tree | Current local `.env` points to an iCloud Drive folder |
| `DATABASE_PATH` | SQLite file | `./data/reelvault.db` |
| `THUMBNAILS_FOLDER` | Generated image cache | `./data/thumbnails` |
| `GEMINI_API_KEY` | Optional secret | Blank disables AI gracefully |
| `GEMINI_MODEL` | Configurable model name | `gemini-2.5-flash` |
| `APP_HOST` | FastAPI bind host | `127.0.0.1` |
| `APP_PORT` | FastAPI port | `8000` |
| `FRONTEND_PORT` | Vite port | `5173` |

Relative paths are resolved against the repository root, not the current shell directory.

Normal setup:

```bash
pip install -r backend/requirements.txt
npm install --prefix frontend
cp .env.example .env
# Edit .env, especially REELS_FOLDER and optionally GEMINI_API_KEY.
./start.sh
```

The launcher currently finds the installed Miniconda `python` after the default Homebrew `python3` fails dependency preflight. Direct backend/test commands should therefore use the environment where requirements were installed. The active verified interpreter path at review time was:

```text
/Users/cojovi/homebrew/Caskroom/miniconda/base/bin/python
```

For individual services:

```bash
PYTHONPATH=backend python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
npm run dev --prefix frontend
```

## Verification results

### Backend

Verified command, using the installed Miniconda environment:

```bash
PYTHONPATH=backend /Users/cojovi/homebrew/Caskroom/miniconda/base/bin/python -m pytest backend/tests -vv
```

Result: **6 passed** in about 61 seconds. Warnings:

- Starlette reports its `httpx` TestClient integration as deprecated in favor of `httpx2`.
- Pydantic reports class-based `Config` as deprecated; `ConfigDict` is the forward-compatible replacement.

The scan test is slow because its fake `.mp4` can still enter real Quick Look/ffmpeg thumbnail attempts. The suite does not mock external media tools.

### Frontend build

```bash
npm run build --prefix frontend
```

Result: **passes**. The output is roughly 244 KB JavaScript and 49 KB CSS before gzip. Vite emitted one CSS warning because the Google Fonts `@import` follows Tailwind's import; CSS imports must precede other rules. Node also emitted a `module.register()` deprecation warning from the toolchain.

### Frontend lint

```bash
npm run lint --prefix frontend
```

Result: **fails with 12 errors and 4 warnings**. Main categories:

- Eleven uses of explicit `any`/unsafe typing, including error handling and tab/filter objects.
- React's `set-state-in-effect` rule flags the loading and tab-reset effects.
- Four missing-hook-dependency warnings around `loadData`, `addToast`, the editing record, and thumbnail backfill inputs.

### Database and media

- `PRAGMA integrity_check`: `ok`.
- All 1,306 cached thumbnail files identify as JPEG images.
- `Color_Scheme.png` is a valid 1536×1024 RGBA PNG.
- The local sample reel is a valid three-second MP4.
- FFmpeg 8.1.1, ffprobe 8.1.1, and macOS `qlmanage` are installed.

## Important invariants and safety properties

The strongest implemented safety property is the ready-queue query itself. Both API and CLI ultimately use SQL that requires ready status, approval, and nonblank final copy. Future posting agents should consume `/api/queue/ready` or `reelctl export-ready`, not infer readiness from a single field.

Other useful properties:

- File path is unique and normalized to Unicode NFC.
- Rescanning updates only file-derived metadata and preserves editorial/AI work.
- Gemini results stay in separate fields until the user explicitly adopts them.
- Gemini uploads are deleted after inference, including most failure paths.
- Missing Gemini configuration, ffprobe, ffmpeg, or Quick Look generally degrades gracefully.
- Archive is a state transition, not file deletion.

## Known gaps and risks

### High priority

1. **The generic PATCH endpoint can bypass workflow validation.** `PATCH /api/reels/{id}` accepts `status` and `approved` directly, and the UI's status selector autosaves through it. A caller can create `status='ready'` without a final caption. The strict queue remains safe because its query rechecks all gates, but the record/UI state can become misleading. Centralize validation in the model/service layer and reject invalid status values.

2. **Scanning never marks or removes missing source files.** The current 261 stale paths are the concrete result. Add `is_missing`/`last_seen_at` fields and a reconciliation step; avoid hard deletion by default because rows contain user-authored work.

3. **The app is intentionally local but not secured.** CORS allows every origin, there is no authentication, the entire reels directory is statically mounted, and mutating endpoints are open. Keep `APP_HOST=127.0.0.1`; do not expose it through port forwarding, a public tunnel, or a nontrusted LAN without an auth and serving redesign.

4. **Secrets and user data lack root ignore rules.** This directory is not currently a Git repository, but if it becomes one, `.env`, `data/reelvault.db`, `data/thumbnails`, `.DS_Store`, caches, and possibly `reels/` could be committed accidentally. Add a root `.gitignore` before initializing or publishing a repository.

5. **iCloud behavior is only partially provisioned.** `icloud.py` needs PyObjC's `Foundation`, but it is not in `requirements.txt` and is missing from the verified runtime. In that condition the helper assumes files are available and cannot explicitly request downloads. Make PyObjC a documented macOS optional dependency or implement a supported fallback and surface availability in health.

### Medium priority

6. **Long work runs inside synchronous request handlers.** Folder scans, thumbnail batches, iCloud waits, Gemini uploads, five-minute polling, and model calls can occupy server workers. The browser queue is not durable. Move these operations to tracked background jobs if reliability matters.

7. **No pagination or virtualization.** The API returns full rows and the UI renders all matching cards. It works at the current scale but sends many large text fields and creates a heavy DOM. Add lightweight list projections, pagination, and/or virtualized cards.

8. **SQLite concurrency is minimally configured.** There is no WAL mode, busy timeout, retry policy, transaction/service boundary, backup command, or schema migration system. This matters because the CLI and API are intended to share the file concurrently.

9. **Frontend maintainability and lint debt.** `App.tsx` owns most behavior and presentation. Split it into archive, card, folder tree, workbench, settings, toast, and queue components; then fix hook dependencies and remove `any`.

10. **Test coverage is backend-only and narrow.** There are no frontend tests, end-to-end browser tests, CLI tests, Gemini mocks, malformed-response route tests, iCloud tests, thumbnail fallback tests, filter tests, or stale-file tests.

11. **API error wrapping can obscure intended status codes.** Broad `except Exception` blocks can catch `HTTPException` raised inside a `try` and turn it into a 500. Keep expected validation exceptions outside broad wrappers or explicitly re-raise them.

12. **Data model omits AI quality notes.** The Gemini prompt requests `quality_notes`, and the parser returns it, but the schema/table/save logic discard it. Add a field if human-review guidance is part of the product requirement.

### Lower priority / cleanup

13. Replace Vite starter identity: package name/version, page title, `frontend/README.md`, unused `App.css`, unused starter images, and unused public `icons.svg`.
14. Move the Google Fonts import before Tailwind or self-host fonts to eliminate the build warning and avoid an online font dependency in an otherwise local-first UI.
15. Pin backend versions with a reproducible lock file and document the preferred virtual environment.
16. Add database indexes if filtered queries become slow, especially on `status`, `approved`, and `updated_at`.
17. Validate and normalize hashtags/platform/category outputs rather than storing arbitrary strings.
18. Use timezone-aware UTC timestamps; current code uses naive local `datetime.now().isoformat()` values.
19. Clarify whether direct approval without ready status is desired, and reset `posted_at`/`archived_at` when moving records back to earlier states if lifecycle accuracy matters.
20. Consider whether hover-previewing remote/iCloud videos should require an explicit action to avoid many concurrent file fetches.

## Recommended next milestones

### Milestone 1: stabilize the existing MVP

- Add a root `.gitignore` and define which local data is backed up versus versioned.
- Centralize status/approval/final-caption validation.
- Add stale-file reconciliation without deleting editorial data.
- Fix frontend lint and the CSS import warning.
- Record iCloud capability in health and document/install the optional dependency.
- Update the README and replace starter metadata/docs/assets.

### Milestone 2: make operations dependable

- Add migrations, WAL/busy timeout, backups, and recovery instructions.
- Introduce a durable analysis/thumbnail job model with progress and retry.
- Add pagination/list projections and frontend virtualization.
- Add API, CLI, frontend component, and end-to-end tests.

### Milestone 3: prepare automation safely

- Define a minimal machine-readable ready-item contract rather than exporting every DB column.
- Add claim/lease/idempotency semantics so two agents cannot post the same reel.
- Add platform/post identifiers and a verified posted transition.
- Add authentication and eliminate broad static mounts before any network exposure.
- Only then integrate actual social-platform publishing or scheduling.

## Guidance for future Codex/agent work

- Treat `DETAIL.md` as the original specification, `PROGRESS.md`/`SESSION_NOTES.md` as historical context, and source plus the live database as current truth.
- Do not alter or delete `data/reelvault.db`, `data/thumbnails`, the configured iCloud source, or `.env` unless the user explicitly asks.
- Never expose the Gemini API key in logs, patches, or documentation.
- Preserve manual captions and notes during scans, migrations, and AI operations.
- Preserve the ready-queue predicate at every automation boundary.
- Use the Miniconda environment or install `backend/requirements.txt` into an explicit virtual environment before running backend commands.
- Run both backend tests and the frontend build for cross-stack changes; run lint and report existing versus newly introduced failures.
- Avoid using the live database in tests. Existing tests correctly redirect paths before importing settings.
- If changing the schema, implement an explicit migration; `CREATE TABLE IF NOT EXISTS` will not add columns to existing databases.
- If testing scans against the live source, remember that the operation can trigger thumbnail generation and iCloud downloads even though it does not copy videos into the project.

## Bottom line

ReelVault already accomplishes its central promise: it turns a large local/iCloud video collection into a searchable editorial archive with persistent drafts, optional Gemini assistance, explicit human approval, and a safe outbound queue. The project is useful today on its owner's Mac. Its next phase should focus less on adding features and more on protecting the real data now accumulated around it: enforce workflow rules centrally, reconcile missing files, harden local operations, reduce frontend debt, and establish reproducible version control and backups before adding a real posting agent.
