# vmtest verification — September 5, 2026

## September 7: agent Ready Queue → Posted

- Added agent-readable `/api/v1/queue/ready` with the dashboard's shared eligibility rules, ID pagination and optional platform/account exclusions. The generic v1 Ready filter now uses the same strict predicate.
- A confirmed `/publications/{id}/complete` atomically records the receipt and moves the unchanged Ready reel to Posted. Repeated completion is safe; newer media/caption/hashtag/workflow changes are preserved and reported through `reel_status`.
- Updated `AGENT_API.md` with the complete pick/claim/materialize/download/start/external-publish/complete flow, field contracts, leases, idempotency and crash recovery. The Docker image now packages the guide and serves it at authenticated `/api/v1/guide`.
- 84 backend tests passed on the Mac and in the deployed Linux image. New tests cover agent authentication, strict queue filtering/pagination, target claims, actual fixture materialization/download, completion, counts, retained notes, idempotency, stale snapshots and uncertain success. Diff checks passed; frontend code/assets were unchanged in this update.
- Rendered QA: Browser plugin unavailable; regular Playwright/Chrome against isolated localhost `http://127.0.0.1:18770/`, 1440×1000. Owner login → Ready Queue 1 → agent claim/start/simulated-success receipt → ordinary UI refresh → Ready Queue 0 / Posted 1 → Posted card with preserved caption. Page identity/content, no framework overlay, zero browser console errors and the exact interaction passed. Screenshots: `/private/tmp/reelvault-agent-qa/01-ready.png` and `02-posted.png`.
- No real social upload, claim or completion was performed. External publishing still requires the agent's authorized platform connection. Real reel 1232 remains Ready; real editorial data and publication records matched the pre-deployment backup.
- Recovery: image `reelvault:vmtest-before-agent-posting`; database `data/backups/reelvault-before-agent-posting-20260907.db`.

## September 7: rescan reconciliation

- Deployed fresh recursive Dropbox reconciliation for startup, 15-minute scans and the manual refresh job. Moves/renames keep their provider-linked record; missing files are hidden from normal lists, folder counts and duplicate-copy navigation and remain in explicit history.
- 73 backend tests passed on the Mac and inside the deployed Linux image; 13 frontend unit tests, production build, lint and diff checks passed. New regressions exercise moves, renames, parent-folder moves, deletion, restoration, unsupported-extension renames, retained descriptions/captions/jobs, and incomplete-provider failures.
- Browser plugin not available in this session. Regular Playwright/Chrome tested an isolated localhost fixture at `http://127.0.0.1:18769/` with the actual built UI, API, job worker and periodic scanner. No hosted browser security restriction was bypassed; no real videos were moved/deleted for QA.
- Desktop 1440×1000: page identity, meaningful content, no framework overlay, no browser console errors, zero automatic original-video requests, manual rescan → updated Home → destination folder, explicit missing-file history, and periodic rename → automatic UI refresh all passed. Screenshots are in `/private/tmp/reelvault-rescan-qa/` on the Mac.
- A 390×844 check found existing main-sidebar clipping. Responsive layout was not changed by this fix; mobile visual acceptance is not claimed.
- The live deployment's manual scan completed successfully against 1,279 videos. Default list and library storage status were verified, and the served asset is `index-BWusQmUo.js`. All catalog IDs, captions, notes, approvals, workflow states, AI descriptions and thumbnail references matched the pre-update database backup.
- At diagnosis the Mac Dropbox paths, Dropbox cloud paths and hosted catalog paths matched. The user's specific stale item remains unverified pending an example filename; the patch addresses confirmed missing-history visibility and makes scans repair stale catalog state.
- Recovery: previous image `reelvault:vmtest-before-rescan-fix`; SQLite backup `data/backups/reelvault-before-rescan-fix-20260907.db`. Originals were untouched.
- Corrected the VM bootstrap and live override from 60 to 900 seconds to retain the user's earlier 15-minute preference. Startup/manual scans remain immediate.

## Latest: private folder browser and exact-copy grouping

The Tailscale deployment at `https://cmac-bolt-data-vm.tail8e0a20.ts.net:8443/`
now serves the folder-first library. This section supersedes the original setup
results below: Dropbox is connected, Gemini is configured, and the catalog contains
1,278 records with 1,269 quick descriptions at this verification point.

- 68 backend tests pass locally and inside the deployed Linux image. Three new
  tests cover the lightweight read-only library index, grid/detail hash exposure,
  retained editorial fields, and owner-only/no-store access.
- 11 frontend unit tests pass (`npm run test:unit --prefix frontend`), covering
  Dropbox-wrapped and Mac-root home destinations, direct-only nested views,
  zero-direct-file parents, breadcrumbs, case/Unicode/prefix boundaries, exact
  duplicate identities, malformed/empty hashes, independent copy IDs, filter order,
  stable navigation under search, and empty catalogs.
- TypeScript/Vite production build, ESLint and `git diff --check` pass.
- Read-only live HTTPS checks run the actual frontend folder/grouping functions
  against the deployed API data. Home: 1,039 direct files → 1,032 cards, zero
  subfolder records included. `artistic/tv`: 23 files → 20 cards. All 1,278 IDs
  remain present; no original-file, editorial or catalog deletion was performed.
- The highlighted Number group (1204/1205/1206) retains all IDs and produces one
  representative card (1205). The distinct long video 1207 stays visible. Identical
  cross-folder pairs 1161/1162 and 1202/1203 retain their separate folder membership.
- 39 non-empty exact-copy groups contain 42 additional copies globally. Three
  zero-byte entries are deliberately excluded from automatic grouping.
- Live HTML references `/assets/index-DR4obyfK.js`; that asset responds successfully
  and includes the new grouping control. Anonymous library index access returns
  401. Dropbox connectivity and Gemini configuration remain true.
- The old application image is retained under `reelvault:vmtest-before-folder-browser`.

**Rendered browser QA is blocked**, not passed. The browser tool denied navigation
because its admin-enforced security policy could not be verified. No alternate
browser driver or indirect workaround was used. The screenshots farther below are
historical evidence for the original setup, not evidence for these new components.

Pending visual acceptance after refreshing/signing in:

1. Home shows `SnapIGTik Download`, folder tiles, and no artistic/subfolder cards.
2. Open `artistic`, then `tv`; breadcrumbs go back correctly and the grid changes
   to direct folder contents. Folder navigation remains visible during a search.
3. Search `Number`: the 9:17 copies share a card; the 46:28 clip remains distinct.
   `3 exact copies · View` lists three names/IDs, each opening its own workbench.
4. Uncheck `Group exact copies` to reveal every record. Recheck to regroup; folder
   changes and grouping toggles clear batch selection. Existing editor changes save
   before navigation. Verify copy-dialog keyboard focus, Escape and close button.
5. Check layout at desktop and narrow widths. Below the desktop-sidebar breakpoint,
   folder tiles and breadcrumbs still provide navigation.

No new browser screenshots or browser-console success are claimed for this update.

## Original setup results (historical)

## Outcome

The private Dropbox-mode container is healthy on VM loopback port 18765.
The dashboard, authentication, job infrastructure and synthetic media flow are
verified. **Real Dropbox access is still pending the owner's developer-app setup
and OAuth consent.** No real cloud-transfer or paid Gemini success is claimed.

## Automated checks

- 44 backend tests passed locally and inside the actual Linux VM image.
- Coverage includes existing archive regressions; Dropbox move/revision/replacement
  identity; failed sync preserving cursor/catalog; PKCE token exchange and namespace
  headers with simulated HTTP; five simultaneous downloads; full-size reservations;
  LRU/TTL with active reader pins; byte-count/hash mismatch cleanup; minimum free
  disk accounting; single-process ownership; authenticated byte-range responses;
  agent permissions; keyset pagination; durable jobs; publication target locks,
  caption/revision snapshots, expiry, uncertainty and idempotent completion.
- TypeScript/production build and ESLint passed.
- Compatible frontend tooling security updates applied; `npm audit` reported zero
  known vulnerabilities after updating the lockfile.
- `git diff --check` passed. Private access credentials are mode 0600 and Git-ignored.

The test runtime emits Starlette/httpx and anyio deprecation warnings. The local
Node runtime emits a build-tool deprecation warning. These are not test failures
or browser console errors; address them during the next dependency maintenance pass.

## Browser evidence

Target flow: an unauthenticated visitor sees only login, the owner signs in and
configures storage, browsing does not preload originals, and an authorized agent
can prepare/download a chosen reel without gaining approval privileges.

Browser plugin not available: regular Playwright with headless Google Chrome,
1440×1000 viewport, accessing the actual VM through SSH. No network mocks, saved
browser authentication state or credential-bearing traces were used.

1. Dropbox-mode instance (`http://127.0.0.1:18765`): correct title, rendered login,
   unauthenticated API denial, successful owner login, visible storage/cache policy,
   prefilled Dropbox path, readable disabled connection button, and logout denial.
2. Separate synthetic-media instance (`http://127.0.0.1:18766`): actual generated
   H.264 test clip played through the dashboard; byte-range attachment returned
   206 and the exact requested 100 bytes; an agent materialization job completed;
   agent attempt to approve a reel returned 403.
3. Zero browser console/page errors in both flows. No automatic video requests on
   initial archive load. Visual review caught and fixed the new connection button's
   theme-color contrast before final verification.
4. A QA container restart retained its catalog and completed materialization job
   `bd2d5e3f87df474aad6aa923355de53b`.

Screenshots on the workstation:

- `/private/tmp/reelvault-vmtest-qa/01-login.png`
- `/private/tmp/reelvault-vmtest-qa/02-storage.png`
- `/private/tmp/reelvault-vmtest-media-qa/03-playback.png`

Run the hosted smoke check with `npm run test:vm --prefix frontend` while the SSH
tunnel is open. Credentials are read from ignored `.vmtest/access.txt` without
printing token values. Synthetic-media mode additionally uses the environment
variables documented at the top of `frontend/tests/vm-smoke.mjs`.

## Deployment and preservation

The deployed service runs as the VM user (not root), with loopback-only binding,
resource caps, a read-only container root, rotated logs and persistent data. The
final health check was healthy. Observed idle memory was approximately 87 MiB;
the storage UI reported approximately 21.94 decimal GB free after image creation.
Those are point-in-time observations, not capacity guarantees.

Other VM applications were not restarted or reconfigured. The temporary QA container
was stopped/removed after verification; its small synthetic clip and QA SQLite
database remain recoverable in the dedicated `qa-data/` directory. The main
`reelvault-vmtest` service remains running. No original Mac media, metadata or
editorial work was modified or copied into the test catalog.

The real archive remains empty on the VM until Dropbox is connected. Pending:
real account/folder sync, actual Dropbox playback/download, five-real-file transfer
acceptance, optional Gemini setup, and any historical catalog migration. Public
HTTPS and scheduled off-VM backup automation are not configured.
