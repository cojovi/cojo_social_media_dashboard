# ReelVault VM test deployment

This branch adds a private, single-owner hosted mode. FastAPI serves both the built
React dashboard and the API. Dropbox owns the original videos; SQLite, thumbnails,
and a limited media cache live on the VM. Vercel is not needed for this deployment.

## Current test instance

- SSH host: `big-boy-vm` (`35.226.206.206`), user `codyv_cmacroofing_com`.
- Dedicated install directory: `/home/codyv_cmacroofing_com/reelvault-vmtest`.
- Container/image: `reelvault-vmtest` / `reelvault:vmtest`.
- Private listener: VM `127.0.0.1:18765`; no new public firewall port.
- Private HTTPS: `https://cmac-bolt-data-vm.tail8e0a20.ts.net:8443/`, served only
  through Tailscale Serve. Funnel is not enabled. The existing port-443 service is untouched.
- Persistent data: the install directory's `data/`, mounted at `/data`.
- Private configuration: `vmtest.env`; owner/agent credentials: `access.txt`.
- The VM catalog was initially empty; Dropbox populated 1,278 independent records.
  A subsequent verified import restored 1,031 missing Mac quick descriptions and
  1,037 thumbnails. The original Mac database (1,626 records) and source videos were
  not changed. Historical captions, approvals, notes, full AI analysis and usage
  history were not imported; that editorial migration remains separate.
- Gemini is configured on the current VM using the existing Mac project's key,
  transferred privately to `vmtest.env` (0600, never committed or printed). Full
  analysis uses `gemini-2.5-flash`; automatic visual quick summaries use
  `gemini-2.5-flash-lite`, with the existing $1/day quick-summary estimate limit.
  A real single-reel pilot succeeded before automatic processing was enabled.
  Fresh bootstrap environments still start with no key and automatic summaries off;
  the bootstrap script preserves this instance's existing configuration on reruns.

## Open the dashboard from any Tailscale device

Connect Tailscale on the device and open
[ReelVault](https://cmac-bolt-data-vm.tail8e0a20.ts.net:8443/). Use the existing
**Owner access token** from private `access.txt` (Mac copy: ignored `.vmtest/access.txt`).
No SSH tunnel or running Mac is required. Access remains subject to the tailnet's
existing access-control rules. Neither the archive nor the API is published to the internet.

On this instance, `PUBLIC_ORIGIN` is the exact HTTPS address above and
`COOKIE_SECURE=true`. Browser cookies remain HttpOnly and SameSite=Strict. The old
HTTP localhost address is no longer the login URL. Sessions expire on service restart;
the existing owner token is unchanged. Gemini and Dropbox secrets stay on the VM.

The private reverse proxy is persistent (`--bg`), and `tailscaled` is enabled at boot:

```bash
sudo tailscale serve --bg --https=8443 http://127.0.0.1:18765
tailscale serve status --json
```

Do not run `tailscale funnel` or reset unrelated Serve configurations. To remove only
this endpoint, use `sudo tailscale serve --https=8443 off`. Docker still binds only
the loopback address. SSH administration uses VM Tailscale IP `100.123.164.112`;
the public SSH IP currently times out. Device key expiry must still be maintained.

## Recovering existing Mac descriptions

The initial VM build did not carry over the old catalog's derived annotations. The
Mac database actually held 1,405 quick descriptions, 1,411 thumbnail references,
six failed jobs and 212 waiting-for-local-preview jobs. The two catalogs' numeric
IDs are unrelated and must never be used as a migration join.

`deploy/export_mac_descriptions.py` builds a manifest from a read-only Mac database
and a VM metadata snapshot. It requires an unambiguous root-relative path, identical
size and modification time (within one second for provider timestamp precision).
Resident Dropbox files also have their content hash verified. Offloaded originals
are not opened or hydrated. Modified/unmatched/ambiguous files are skipped.

`backend/app/catalog_import.py` defaults to dry-run. With the service stopped,
`--apply` rechecks every destination Dropbox ID/revision/path/size/hash, validates
thumbnail hashes and paths, makes a full SQLite backup, and fills only missing quick
description fields and thumbnails. Existing VM descriptions, editorial fields,
approvals and provider identities are preserved. Imported description jobs are
marked done, avoiding another paid request. The manifest is retained as provenance.

The September 5 CDT import added 1,031 descriptions and 1,037 thumbnails, preserving
128 already-described matched VM records. Immediately after import the VM had
1,165 described reels, 111 queued and two failed. Normal automatic processing was
resumed for the remaining undescribed records under the unchanged $1/day estimate limit.
The two failed records (VM IDs 1213 and 1257) returned no Gemini description after
three attempts; they were not silently labeled or repeatedly retried by the migration.
The bundle occupies about 57 MB, not a copy of the original videos.

VM recovery backup:
`data/backups/reelvault-before-mac-descriptions-20260906T031545765358Z.db`.
Import bundle: `data/imports/mac-20260906/`. Neither belongs in Git. Verified HTTPS
checks include owner login, Secure cookies, rejected foreign origins, restored
summaries/private thumbnails, logout, and agent byte-range downloads. All 65 backend
tests pass locally and in the VM image. Rendered verification remains blocked by the
browser tool's unavailable admin-policy check; it was not bypassed.

## Dropbox: one-time setup (about five minutes)

1. Open the [Dropbox developer app creation page](https://www.dropbox.com/developers/apps/create).
2. Choose **Scoped access**, then **Full Dropbox**, and a unique app name such as
   `CMAC ReelVault Archive`. Full Dropbox is required to use your existing folder
   instead of a new isolated `Apps/...` folder. It grants account-wide capability;
   ReelVault limits its catalog to your configured folder, and requests no write scopes.
3. In **Permissions**, enable only `account_info.read`, `files.metadata.read`, and
   `files.content.read`. Save/submit the permission changes.
4. Copy the **App key** from Settings. Do not copy the app secret, create a generated
   access token, or add a redirect URL. This app uses the offline OAuth authorization
   code flow with PKCE and Dropbox's displayed one-time code.
5. Open **ReelVault → Settings → Cloud storage & VM**. Enter that app key. The
   prefilled Dropbox-relative folder is `/Cody Viveiros/SnapTik_Reel_Archive`.
6. Click **Create authorization link**, follow the link, sign into the intended
   `Dropbox-CMACRoofing` account and approve the read-only permissions. Paste the
   displayed one-time code back into ReelVault, then click **Finish connection**.
7. The first metadata scan starts immediately; subsequent scans run every 15 minutes. Manual rescans run immediately.
   Browse the archive, open one reel, and test its download before processing a backlog.

Your Mac download location remains:

```text
/Users/cojovi/Library/CloudStorage/Dropbox-CMACRoofing/Cody Viveiros/SnapTik_Reel_Archive
```

Finish downloading each video outside the archive folder, then move it in, where
possible; this avoids Dropbox publishing successive incomplete versions. Wait for
Dropbox to report that the upload is complete. The VM can only see data already
uploaded to Dropbox—not files merely present on the Mac. Subfolders are recursive.

Team-space support reads the linked account's root namespace. If Dropbox reports a
folder/namespace error, check that the selected account and cloud-relative path
match in Dropbox's web UI; a team administrator may also restrict developer apps.
The current build intentionally refuses silently switching an already-linked
account. Ask for a planned relink if the account/root is wrong.

Refresh tokens are stored only in `data/secrets/dropbox.json` (directory 0700, file
0600). They are never returned to the browser/agent, logged, or saved in SQLite.
See [Dropbox's OAuth guide](https://developers.dropbox.com/oauth-guide) and
[change detection guide](https://developers.dropbox.com/detecting-changes-guide).

## Resource policy

| Setting | Default | Behavior |
|---|---:|---|
| `MAX_CONCURRENT_DOWNLOADS` | 5 | Process-wide upper limit, shared by UI/jobs/AI |
| `CACHE_MAX_BYTES` | 5,000,000,000 | 5 GB including full reservations for partial downloads |
| `CACHE_TTL_SECONDS` | 43,200 | 12 hours idle; active readers are never evicted |
| `MIN_FREE_DISK_BYTES` | 5,000,000,000 | Check before admission and during writes |
| `SCAN_INTERVAL_SECONDS` | 900 | Fresh recursive Dropbox metadata reconciliation (15 minutes) |
| `AUTO_QUICK_SUMMARY` | true on current VM | New/missing descriptions are queued after scans; fetches media through the bounded cache |
| `QUICK_SUMMARY_DAILY_BUDGET_USD` | 1 | Application estimate guard for quick summaries, not a provider billing cap or full-analysis budget |

All size settings use bytes (decimal GB in the UI). The cache is expendable, not an
archive replica. Downloads reserve the entire expected size before starting,
deduplicate by Dropbox ID + revision, verify the exact byte count and Dropbox
content hash, and atomically promote a partial file only after verification.
LRU/TTL eviction removes only inactive cache entries, never Dropbox originals.
Full-cache/low-disk requests fail clearly instead of evicting active readers.

The 5 GB budget covers cached original videos and in-flight media, not the database,
durable thumbnail collection, Docker images, rotated logs, or other VM applications.
Frame sampling is done through memory pipes; no second full-video processing copy is
created. Keep monitoring overall free space: other applications can still fill the
disk, and no application can guarantee space against unrelated system writes.

The container has a 1.5 GB memory cap, 1.5 CPU cap, 256 PID cap, read-only root,
128 MB temporary filesystem, dropped capabilities, non-root user, and rotated logs.
It is excluded from Watchtower auto-updates. No existing VM service is reconfigured.

## Build and deploy an update

From the Mac repository, run tests, `npm ci --prefix frontend`, and
`npm run build --prefix frontend`. Upload only the files needed by the Dockerfile:
`Dockerfile`, `.dockerignore`, `AGENT_API.md`, `backend/app`, `backend/tests`, backend requirements,
`frontend/dist`, and `deploy/`. Never upload `.env`, `.git`, `node_modules`, originals,
or the live Mac database as part of the application package.

In the dedicated VM install directory:

```bash
python3 deploy/bootstrap.py                 # Preserves existing configuration
sudo docker build -t reelvault:vmtest .
bash deploy/run-vmtest.sh
sudo docker logs --tail 60 reelvault-vmtest
```

The script replaces only the named test container; persistent `data/` is preserved.
It is a short-downtime update, not blue/green deployment. A new image does not
rebuild or resynchronize all videos. There is no GitHub auto-deploy configured.

Run exactly **one Uvicorn process** per database/cache. An OS-level cache owner lock
rejects a second process. Work is threaded internally. Restart recovery removes
incomplete cache files and retries safe interrupted jobs; interrupted AI work is
marked failed for review to avoid an automatic second paid request. Browser sessions
expire on restart. Full-review jobs already submitted to the server continue when
the tab closes, but the browser's not-yet-submitted selection list does not.

## Recovery and exposure boundaries

Back up SQLite with its backup API (not a raw copy of a live WAL database). Keep
versioned backups of `data/reelvault.db`, thumbnails, and the separately protected
Dropbox refresh-token/configuration files. Cache media need not be backed up. The
database migration makes a backup before adding columns to populated older catalogs;
this is not a scheduled disaster-recovery system. Backup automation is not yet set up.

Before public HTTPS: choose a domain, configure an isolated reverse-proxy route,
set `PUBLIC_ORIGIN` to the exact HTTPS origin and `COOKIE_SECURE=true`, review
ingress/rate limits, rotate test owner/agent tokens, and validate externally. Do not
simply publish the HTTP port. Current cookies are already Secure for the private
Tailscale HTTPS endpoint; public internet hosting is not part of the selected deployment.

Live acceptance completed September 5 CDT: Dropbox authorization and folder sync,
five simultaneous real-file downloads, integrity verification, authenticated range
downloads, and actual short-reel browser playback. The catalog contained 1,278 records
at the final check, with new uploads discovered incrementally. The initial download
test revealed a deprecated Dropbox revision argument; the corrected revision-path
request and regression tests are deployed. Failed initial tests remain in job history.

### Small preview storage (September 8 update)

The dedicated `data/previews` directory persists small silent H.264 clips. Default
settings: `AUTO_PREVIEWS=true`, `PREVIEW_MAX_BYTES=1000000000`, and
`PREVIEW_DELAY_SECONDS=10`. One serial encoder creates at most nine seconds at 360px
and 15 fps, with a 1 MB per-asset ceiling. It reserves 5 MB for temporary segments
and the final file, including that reservation in the preview budget and the
original cache's free-disk checks. The existing 5 GB original cache is separate;
database, thumbnails, backups and container images are outside both budgets.

Backfill discovers catalog additions every minute, prioritizes explicit requests
and resident originals, and persists through restarts. It reads Dropbox originals
through the verified, pinned media cache. It never calls Gemini. Original downloads
remain eligible for the existing 12-hour/LRU cleanup after processing. Completed
previews have no idle TTL; background work waits at capacity instead of evicting
and regenerating endlessly. Requested previews can evict unused clips. Exact copies
share assets by Dropbox hash/size; stale or missing source assets are retired.

Use **Settings → Small video previews** for counts, bytes, capacity information and
pause/resume. The current encoder finishes before pausing; manual requests still
run. `AUTO_PREVIEWS=false` disables automatic work at the server level. Keep
`VM_JOBS_ENABLED=true` for on-demand generation. The container already includes
ffmpeg/ffprobe. Jobs and pause preference are stored in SQLite, and temporary owned
encoding directories are removed during restart recovery. Run one process per
database/cache, as before. Originals larger than the media cache budget cannot
receive a server-generated preview without adjusting that original budget.

Cold **full-video** playback waits for a complete verified cache download. A 1.2 GB archive video
outlasted a 30-second first-play test, then played normally once cached. Short-reel
playback passed. Cache usage after testing was 1.256 GB, with no active pins/downloads.
Follow-up acceptance restored Gemini and fixed a real `localhost`/`127.0.0.1` login
origin mismatch. All 58 backend tests pass locally and in the VM image. Live owner
login requests succeed for both loopback origins; untrusted origins remain blocked.
One Flash-Lite description completed with 904 input tokens and 56 output tokens,
an application-estimated $0.0001128. Automatic descriptions were then enabled with
the existing models and $1/day quick-summary estimate limit. Full-video AI was not
invoked in this follow-up. Rendered browser re-verification was blocked by the
browser tool's unavailable admin-policy check; no alternate browser bypass was used.

Historical catalog migration, sustained load testing, public HTTPS, and scheduled
off-VM backups remain separate next steps.

See [AGENT_API.md](AGENT_API.md) for the external agent contract.
See [VM_TEST_RESULTS.md](VM_TEST_RESULTS.md) for the initial pre-connection verification;
the live acceptance above and the current [CODEX.md](CODEX.md) supersede its pending
Dropbox-authorization notes.
