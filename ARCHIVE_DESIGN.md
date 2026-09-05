# Archive workflow, storage, and AI costs

Reviewed September 4, 2026. This document records the product decisions behind the archive upgrade; `DETAIL.md` and the exported ChatGPT conversation remain the original design history.

## The product

ReelVault should act as a searchable memory for the user's video collection: discover what arrived, describe it cheaply, keep useful metadata accessible even when originals are offloaded, and help choose and prepare something to post. Detailed copywriting belongs near the decision to post. Discovery and organizational labeling should require little attention or disk space.

The existing foundation is useful: a local SQLite catalog, nested folder navigation, video previews, separate manual/AI/final copy, workflow statuses, and a CLI for agents. The most consequential gaps were operational rather than visual:

- No startup or recurring scan; a fresh launch could show an old catalog.
- Scanning coupled directory enumeration to slow video probing and thumbnail generation.
- Missing thumbnails, automatic backfill, and hover playback could hydrate originals unnecessarily.
- PyObjC was absent, causing the old iCloud helper to assume every placeholder was local.
- One Gemini workflow uploaded full videos and generated marketing copy even when a rough label was enough.
- No API token accounting and no durable quick-description queue.
- Search did not include even the existing AI summaries.
- Missing files were retained without a visible missing-file status.
- Slow save responses and completed AI analysis could replace newer form input.

The upgrade separates metadata scanning, lightweight description, explicit playback, and detailed editorial work. It preserves the synthwave interface and the existing manual-copy workflow.

## Evidence from this collection

The configured source was already `/Users/cojovi/Library/Mobile Documents/com~apple~CloudDocs/SnapIGTik Download`. Before the upgrade, the database had 1,415 entries, 1,306 thumbnail references, and three full AI analyses. A read-only inventory found 1,274 supported videos, 1,110 carrying macOS's dataless/offloaded flag, 215 disk paths absent from the catalog, and 352 database paths absent from disk. These are a point-in-time snapshot; arrivals and sync changes continue.

The first upgraded scan took 0.08 seconds and indexed 211 new paths. It scanned 1,271 stable files, deferred three zero-byte files, and marked 351 entries missing under the configured root. Some preexisting records outside that root remain unknown. The catalog therefore includes more rows than the current source tree; missing entries retain their editorial history.

The first three real quick-description requests used 2,712 input tokens and 224 output tokens in total. At published paid rates, that is **$0.0003608 total**, or approximately **$0.12 per 1,000 comparable descriptions**. They used three local frames per video. Their summaries covered superhero scenes and fantasy visuals without forcing a roofing marketing angle. This is a small pilot, not a promise that every video will cost or perform identically.

## Dropbox vs Google Drive vs iCloud

My recommendation for a future archive backend is **Dropbox through its API, with a bounded local download cache**. This is an engineering judgment about the integration, not a measured guarantee that Dropbox's Finder client never stalls.

| Choice | Space-saving behavior | Fit for agents |
|---|---|---|
| iCloud Drive | Originals can be offloaded; Finder/provider retrieves them | Works with this local index, but hydration depends on macOS and can stall. The app now detects dataless files without Foundation and uses timeouts for explicit playback requests. |
| Google Drive | Stream files to minimize local copies; mirroring retains a full copy | Good option with direct Drive API downloads by file ID. Desktop streaming still depends on the provider being active, and Google documents application compatibility limitations. |
| Dropbox | Online-only files retain small placeholders and download on demand | A strong fit with file IDs, revisions, recursive listing/cursors, and direct download endpoints. File IDs survive moves and renames, avoiding the catalog's current path identity problem. |

Sources: [Drive streaming and mirroring](https://support.google.com/drive/answer/13401938), [Drive on macOS](https://support.google.com/drive/answer/12178485), [Drive API downloads](https://developers.google.com/workspace/drive/api/guides/manage-downloads), [Dropbox online-only files](https://help.dropbox.com/sync/make-files-online-only), and [Dropbox file IDs and recursive listing](https://developers.dropbox.com/dbx-file-access-guide).

The important architectural improvement is **direct download by stable cloud file ID**, independent of Finder placeholder hydration. Keep SQLite, thumbnails, summaries, and tags on the SSD; store originals remotely; download a selected original into a size-limited cache; remove only that disposable cache copy after use. Verify the remote upload/revision before ever discarding a newly ingested local original.

A provider migration has not been performed. No Dropbox OAuth application/account or Drive folder was selected for this repository. Simply changing `REELS_FOLDER` after moving the library would create new path-based records and leave old captioned records behind. A proper migration should inventory and match files, relink existing IDs, retain a reversible manifest, verify cloud copies, and then configure cache/eviction behavior.

For the current iCloud collection, the immediate improvement is substantial: scanning, opening the editor, and hovering no longer pull down originals. Cloud files without cached previews wait until one is available. Full playback still depends on the cloud client, and an explicit read may time out. Originals are not automatically evicted after a quick description.

## What makes the descriptions cheap

Shortening the prompt alone leaves the full video input bill largely intact. The new workflow reduces what gets sent:

- Local videos: sample at 15%, 50%, and 85% of duration, scaled to at most 384×384. If duration is unavailable, use the opening frame.
- Offloaded or missing videos: use one existing local thumbnail when present.
- Model: `gemini-2.5-flash-lite`, verified accessible with the configured key.
- Prompt: one short visual sentence, one category, 3–6 simple search tags. No marketing copy, audio claims, names, or invented unseen events.
- Configuration: thinking disabled, output capped at 256 tokens; no search grounding, caching service, or video upload.
- Persistence: keep results, avoid duplicate queued requests, and retry transient errors with limits and backoff.

Sparse stills can miss the point of a spoken reel or a fast joke. Cached-thumbnail descriptions are even rougher and are labeled accordingly in the workbench. This is useful organizational metadata, not a full-content review. The separate full-review button still examines video/audio and proposes captions when that detail matters.

## Rates and examples

At the verified standard paid-tier Gemini rates:

| Model | Text/image/video input per million tokens | Audio input per million | Output per million, including thinking |
|---|---:|---:|---:|
| Gemini 2.5 Flash-Lite | $0.10 | $0.30 | $0.40 |
| Gemini 2.5 Flash | $0.30 | $1.00 | $2.50 |

[Google's pricing](https://ai.google.dev/gemini-api/docs/pricing) and [Flash-Lite launch details](https://developers.googleblog.com/en/gemini-25-flash-lite-is-now-stable-and-generally-available/) support these rates. Model availability was checked against the configured API key; the [deprecation schedule](https://ai.google.dev/gemini-api/docs/deprecations) currently lists no shutdown date for these two stable models.

Quick-description estimate: about $0.10–$0.30 for 1,000 ordinary clips under the current still-image approach; the pilot extrapolates to $0.12. The conservative request allowance is 2,000 input tokens plus 256 output tokens, or $0.0003024 per request on Flash-Lite. The daily limit is calculated from recorded usage before issuing another request. It is an estimate-based app limit, not a provider-enforced billing cap; requests interrupted before usage is returned, other API clients, taxes, and full reviews are outside it.

For comparison, an illustrative **1,000 full 30-second videos** at 258 visual tokens/second and 32 audio tokens/second, plus 500 prompt and 500 output tokens per video, would cost about **$4.68** on Flash; 60-second clips under the same assumptions would cost about **$7.96**. Lower video resolution changes that estimate, and extra output/thinking adds cost. Google's [video tokenization documentation](https://ai.google.dev/gemini-api/docs/video-understanding) explains the frame/audio accounting. The old app recorded no token usage, so its historical bill cannot be reconstructed precisely from the catalog.

The Gemini **Batch API gives a 50% discount** for asynchronous processing with a target turnaround up to 24 hours. It could reduce the new quick-description cost further, but saving a few cents adds a second batch submission/result-recovery system. This version uses a resumable local queue of standard requests so new arrivals get descriptions promptly. A local queue is not the discounted Batch API. See [Google's Batch API documentation](https://ai.google.dev/gemini-api/docs/batch-api).

A paid Drive or Dropbox storage subscription does not itself determine Gemini API charges. Gemini usage is attached to the Google API project/tier. Check its billing console for actual charges and account limits. The app shows usage recorded since this upgrade; it does not read your account bill.

## Follow-on work

The most useful next change is a provider adapter with stable IDs and a managed cache, after choosing the destination account/folder. Next would be a posting-plan view: surface approved unused clips, mark content themes, and schedule a modest cadence. Actual platform posting requires explicit account integration and a claim/idempotency mechanism so two agents do not publish the same item. Neither scheduling nor publishing is implied by a quick description or a ready status.
