# Reel Archive Dashboard

**User:** Anonymous  
**Created:** 5/22/2026 0:26:24  
**Updated:** 5/22/2026 3:41:24  
**Exported:** 5/22/2026 3:42:54  
**Link:** [https://chatgpt.com/c/6a0fe8e8-5638-83ea-bbf3-e38023a55b9e](https://chatgpt.com/c/6a0fe8e8-5638-83ea-bbf3-e38023a55b9e)  

## Prompt:
5/22/2026, 12:26:23 AM

i pasted a brain dump below, this is my talking out loud so disregard the inperfections, but im explaining a dashboard sorta, reel archive, reel file definer or sorts.  review what i pasted below and let me know if you understand.

Let's start working on the prompt for a uh, um, a tool to, um, uh, a tool for all the reels backed up that we have. So the folder that has 100 reels in it. This program/app/dashboard will be all the reels in that folder, but then you have the ability to attribute each reel with with a couple things. One being is it ready? So that'd be like some sort of maybe checkbox or something. The other one would be, uh, the post. So the text that goes with the post. And I don't know, do we want one for like relevant hashtags? That'd be separate. That might be good for, um, cataloging if we ever want to search. Um, the dashboard has to be able to save everything. So if I write out all these, um, social media post texts for specific videos, if the dashboard gets shut down and reopened, it's still got to be there. Um, also, if there's a way to integrate a little bit of command line interface commands. So AI can use it. For example, when I open it, I of course want a beautiful web UI and I can work edit, change things from there. But some command line interface tools will be good. So you can also, um, change, modify, edit via the CLI. So let's do a little bit of work and testing on that and see what we can get with so we can more efficiently, um, utilize the folder with all the dog on reels in it and have some sort of long queue. So we know if we allow our AI agent to post things, um, it'll be posting things that are already somewhat confirmed and approved.

## Response:
5/22/2026, 12:26:24 AM

Yes, I understand exactly what you’re describing.

You want a **local reel archive / approval dashboard** for a folder full of backed-up reels, probably 100+ videos, where each reel becomes an item in a queue/catalog.

The app would let you:

1. **Browse every reel in a folder**
   - See video previews/thumbnails.
   - Click into a reel.
   - Search/filter/sort the archive.

2. **Attach metadata to each reel**
   - `Ready / Approved` checkbox.
   - Post caption/text.
   - Hashtags.
   - Maybe notes, platform, category, date planned, status, etc.

3. **Persist everything**
   - Anything you type must be saved.
   - Closing/reopening the dashboard should keep all captions, hashtags, approval states, etc.
   - Probably via SQLite, JSON DB, or a local database file.

4. **Create a posting queue**
   - Approved reels become part of a “ready to post” queue.
   - AI agents should only pull from reels that are marked approved/ready.
   - Prevents the agent from posting random unfinished junk. Very important. No rogue robot intern behavior.

5. **Have both Web UI and CLI access**
   - Web dashboard for you to visually manage everything.
   - CLI commands so an AI agent can read/update the archive, for example:
     - list reels
     - mark reel as ready
     - update caption
     - add hashtags
     - get next approved reel
     - export queue
     - lock/post/archive a reel

6. **AI-agent friendly**
   - The CLI/API lets OpenClaw/Hermes/whatever agent interact with the reel database safely.
   - Agent can help write captions, classify reels, generate hashtags, and eventually post only approved items.

So the core idea is:

**A local media asset manager + social caption database + approval queue + AI-accessible CLI.**

The first version should probably be a simple local app:

**Backend:** Node/Express or Python/FastAPI  
**Database:** SQLite  
**Frontend:** React dashboard  
**CLI:** `reelctl` command-line tool  
**Storage:** Points to your existing reels folder, does not need to duplicate the videos

The key data model would be something like:

```txt
Reel
- id
- filename
- filepath
- thumbnail_path
- duration
- caption
- hashtags
- status: draft / ready / posted / archived
- approved: true/false
- notes
- created_at
- updated_at
- posted_at
```

Yes — I understand it. This is actually a pretty solid internal tool idea. Next step would be turning this brain dump into a **clean Cursor/OpenClaw build prompt** so an agent can scaffold the first working version.

## Prompt:
5/22/2026, 12:31:44 AM

yes sounds like you got me perfectly, and just to be clear, it needs to allow me the options to prewrite the social media post for that reel. so saving that for each reel needs to be an option.  also factor in where i can attach my gemini API key in the .env file, the reason for that is i also want it to offer a button/option/ability (how its executed, ill let you use your best judgement) for gemini to review the reel and not only. summarize it in a generic sense, but then converting that summary to a potential social media post in my tone.  

could those extras be added?

## Response:
5/22/2026, 12:31:45 AM

> **Providing concise answer with Gemini API insights**
>
> The user seems to be asking a conceptual question. I can say that extras can be added, especially with Gemini API. I don’t think I need a web search here since the details won’t need to be fully up-to-date. I'll mention .env, Gemini API key, and optional model, along with button flows and safety measures.
>
> Thought for 4s

Yes — those extras absolutely fit, and they should be part of the **core design**, not bolted on later.

The app should support **manual prewritten social posts per reel**, plus **AI-generated suggestions** from Gemini.

I’d add these pieces:

```txt
Per Reel Fields
- Reel file / video preview
- Ready / approved checkbox
- Status: draft / needs review / ready / posted / archived
- Manual social post text
- AI suggested post text
- Hashtags
- AI suggested hashtags
- Reel summary
- Notes
- Platform target: Facebook / Instagram / TikTok / YouTube Shorts / LinkedIn
- Tone/style selector
- Last AI review date
```

For Gemini, the `.env` should have something like:

```env
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-1.5-pro
REELS_FOLDER=/path/to/reels
DATABASE_PATH=./data/reels.db
```

In the dashboard, I’d make the Gemini feature work like this:

```txt
Button: Analyze Reel with Gemini

When clicked:
1. Sends the selected video/reel to Gemini.
2. Gemini creates a plain-English summary.
3. Gemini identifies what the reel is about.
4. Gemini generates a social media post in your preferred tone.
5. Gemini generates hashtags.
6. Saves the results to that reel’s record.
7. Does NOT overwrite your manually written post unless you approve it.
```

That last part matters. The AI should create a **suggestion**, not stomp over your handwritten caption like a caffeinated intern with admin rights.

I’d separate the fields like this:

```txt
manual_post_text
ai_summary
ai_suggested_post_text
ai_suggested_hashtags
final_post_text
```

Then you can have buttons like:

```txt
Use AI Post as Final
Regenerate AI Post
Copy Final Post
Mark Ready
Mark Posted
```

CLI commands could also support it:

```bash
reelctl analyze "reel-001.mp4"
reelctl set-post "reel-001.mp4" "Your caption text here"
reelctl approve "reel-001.mp4"
reelctl next-ready
reelctl export-ready
```

So yes, the upgraded concept is:

**A local reel archive dashboard where each reel has a saved post draft, AI-generated summary, AI-generated caption, hashtags, approval status, and a CLI/API layer so your agents can safely work with it.**

This is very buildable. The best version would be a **React dashboard + FastAPI backend + SQLite database + Gemini integration + CLI tool**.

## Prompt:
5/22/2026, 12:45:13 AM

![e86b80e3-49b3-4c36-8586-9e43ad2e2a58.png](https://chatgpt.com/backend-api/estuary/content?id=file_00000000509c71fd9f4865503047f7d9&ts=494288&p=fs&cid=1&sig=b27e43f78b4aeaa764f0b42407eaf4cafb56e3339c342ce38cc894d8be3ce498&v=0)

i do NOT by any means want the outcome to look like the image attached, i just want that color scheme.  and keep the synthwave vibe and feel.  some themes and scheme i also like are: steampunk and pixel art. moreso retro pixel art from the old school arcde games (neo-geo, sega, nes, snes, etc).

with all that being said can you write me a very detailed, thorough, and reobust prompt to instruct an ai on how to build this

## Response:
5/22/2026, 12:45:14 AM

> **Crafting a detailed AI prompt**
>
> The user wants a thorough AI prompt for building a project, without needing to analyze the image. They’ve uploaded it for the color scheme, but I can infer that visually and focus on it in the prompt. I'll include the exact tech stack: React, FastAPI, SQLite, and Gemini. The UI, CLI, and API requirements should be clear, along with video upload, .env handling, file scanning, thumbnails, and ffmpeg. I'll present this all in a clean, concise format with no writing block.
>
> **Writing detailed AI prompt including database and API instructions**
>
> The user wants a detailed AI prompt for building an MVP, including a DB schema with statuses and fields, and ensuring safety with only approved postings. I'll specify the use of a configurable GEMINI_MODEL and mention using the latest official SDK, though no need for API key specifics. Important to clarify the color palette (deep plum, neon cyan, etc.) without referencing the attached image's aesthetic. Avoid silent failures and provide clear tests and launch instructions.
>
> Thought for 10s

Yes. Here’s a strong **copy/paste build prompt** for Cursor, OpenClaw, Claude Code, Hermes, etc.

```txt
You are building a local-first web app/dashboard called “ReelVault” or “Reel Queue” for managing a folder full of backed-up social media reels.

This app is NOT a social media posting bot yet. It is a reel archive, caption-writing dashboard, AI analysis tool, and approval queue. The main purpose is to help me organize many reel/video files, prewrite social media posts for each reel, generate AI-assisted summaries/captions/hashtags, and mark only approved reels as ready for future posting.

IMPORTANT VISUAL DIRECTION:
I am attaching/providing an image only for the COLOR SCHEME and general neon/synthwave vibe. DO NOT make the app look like that image. Do NOT build a dense analytics dashboard full of fake charts, radial gauges, random metrics, or nonsense sci-fi widgets.

Use the image only as color inspiration:
- deep black / very dark plum background
- neon cyan accents
- hot pink / magenta accents
- orange / sunset gradient accents
- purple glow
- soft neon borders
- subtle synthwave atmosphere

The UI should feel like:
- synthwave
- retro-futuristic
- retro arcade
- old-school pixel art influence
- light steampunk accents if tasteful
- Neo Geo / Sega / NES / SNES inspired vibes
- dark, colorful, functional, and modern

But the layout must remain clean, useful, and professional. This is a real production tool, not a fake Dribbble dashboard.

Core stack:
- Frontend: React + Vite + TypeScript
- Styling: Tailwind CSS
- Backend: Python FastAPI
- Database: SQLite
- CLI: Python Typer CLI
- Video handling: local file scanning, thumbnails, metadata extraction using ffmpeg/ffprobe if available
- AI: Gemini API integration using environment variables
- Local-first: the app runs on my machine and indexes an existing folder of reels without duplicating the videos

Project goal:
Build a working MVP that scans a local folder of reels/videos, displays each reel in a beautiful web dashboard, allows me to write and save social media post text for each reel, allows Gemini to analyze a reel and generate a summary/caption/hashtags, and allows both the web UI and CLI to read/update the same SQLite database.

Environment variables:
Create a .env.example file with:

REELS_FOLDER=/absolute/path/to/reels
DATABASE_PATH=./data/reelvault.db
THUMBNAILS_FOLDER=./data/thumbnails
GEMINI_API_KEY=
GEMINI_MODEL=gemini-1.5-pro
APP_HOST=127.0.0.1
APP_PORT=8000
FRONTEND_PORT=5173

The Gemini model must be configurable. Do not hardcode the model. If no GEMINI_API_KEY exists, the app should still work, but AI buttons should show a clear warning instead of crashing.

Main user workflow:
1. I point the app to a folder containing many reels.
2. The backend scans the folder and adds video files to the database.
3. The dashboard shows all reels in a searchable, filterable grid/list.
4. I can click a reel and open a detail/editor panel.
5. I can preview the video.
6. I can write a manual social media post/caption for that reel.
7. I can add hashtags.
8. I can add notes.
9. I can set status:
   - draft
   - needs_review
   - ready
   - posted
   - archived
10. I can mark a reel as approved/ready.
11. Everything I type is saved and still exists after closing/reopening the app.
12. Gemini can analyze a reel and generate:
   - plain English summary
   - potential social media caption in my tone
   - suggested hashtags
   - content category
   - suggested platform fit
13. Gemini output must NOT overwrite my manual post automatically.
14. There should be a button like “Use AI Caption as Final Post” if I want to accept the AI version.
15. A future AI agent should be able to safely use the CLI/API to find only approved/ready reels.

Data model:
Create a SQLite database with a reels table.

Required fields:
- id
- filename
- filepath
- file_extension
- file_size
- duration_seconds
- thumbnail_path
- created_at
- updated_at
- discovered_at
- status
- approved
- manual_post_text
- final_post_text
- hashtags
- notes
- ai_summary
- ai_suggested_post_text
- ai_suggested_hashtags
- ai_category
- ai_platform_suggestion
- ai_last_analyzed_at
- posted_at
- archived_at

Suggested statuses:
- draft
- needs_review
- ready
- posted
- archived

Important rule:
A reel should only be considered postable when:
status = ready
approved = true
final_post_text is not empty

Frontend requirements:
Build a polished React dashboard with these main views:

1. Sidebar / Navigation
- All Reels
- Drafts
- Needs Review
- Ready Queue
- Posted
- Archived
- Settings

2. Reel Grid/List View
Each reel card should show:
- thumbnail
- filename
- status badge
- approved indicator
- short caption preview
- hashtag preview
- duration
- updated date
- quick buttons:
  - Edit
  - Analyze with Gemini
  - Mark Ready
  - Archive

3. Search and Filters
Add:
- search by filename
- search by caption
- search by hashtags
- status filter
- approved filter
- has AI summary filter
- has final post filter

4. Reel Detail/Edit Panel
When opening a reel, show:
- video player
- filename/path metadata
- status selector
- approved checkbox
- manual post textarea
- AI suggested post textarea or display field
- final post textarea
- hashtags input
- AI suggested hashtags
- notes textarea
- AI summary field
- buttons:
  - Save
  - Analyze Reel with Gemini
  - Use AI Caption as Final
  - Use AI Hashtags
  - Copy Final Post
  - Mark Ready
  - Mark Posted
  - Archive

5. Ready Queue View
Show only reels where:
status = ready
approved = true
final_post_text exists

This view is important because future agents will use this queue.

6. Settings View
Show:
- reels folder path
- database path
- thumbnails folder
- Gemini enabled/disabled status
- current Gemini model from env
- rescan folder button

Visual/UI style:
Use a dark synthwave theme:
- background: near-black plum
- cards: dark purple/black translucent panels
- borders: subtle neon cyan/pink glow
- buttons: neon gradient but still readable
- fonts: modern sans-serif
- optional pixel-font style only for small labels/headings, not body text
- avoid eye-burning clutter
- make it feel like a retro arcade command center, but clean and functional

Do not use fake analytics charts unless they are actually useful. Acceptable small stats:
- total reels
- draft count
- ready count
- posted count
- needs review count

Backend requirements:
FastAPI backend must provide API endpoints:

GET /api/health
Returns app status and whether Gemini is configured.

POST /api/scan
Scans REELS_FOLDER for video files and adds missing reels to SQLite.

GET /api/reels
Supports optional query params:
- status
- approved
- search
- has_final_post
- has_ai_summary

GET /api/reels/{id}
Returns one reel.

PATCH /api/reels/{id}
Updates editable reel fields.

POST /api/reels/{id}/analyze
Uses Gemini to analyze the local video file and save:
- ai_summary
- ai_suggested_post_text
- ai_suggested_hashtags
- ai_category
- ai_platform_suggestion
- ai_last_analyzed_at

POST /api/reels/{id}/use-ai-caption
Copies ai_suggested_post_text into final_post_text.

POST /api/reels/{id}/use-ai-hashtags
Copies ai_suggested_hashtags into hashtags.

POST /api/reels/{id}/mark-ready
Sets approved true and status ready, but only if final_post_text exists. If not, return a clear validation error.

POST /api/reels/{id}/mark-posted
Sets status posted and posted_at timestamp.

POST /api/reels/{id}/archive
Sets status archived and archived_at timestamp.

GET /api/queue/ready
Returns only reels that are approved, ready, and have final_post_text.

Video scanning requirements:
Scan common reel/video extensions:
- .mp4
- .mov
- .m4v
- .avi
- .webm
- .mkv

Use file path as the unique identifier to avoid duplicates.
If the file already exists in the database, update metadata but do not erase saved captions/posts/AI data.

Thumbnail generation:
If ffmpeg is available, generate one thumbnail per reel into THUMBNAILS_FOLDER.
If ffmpeg is missing, do not crash. Show placeholder thumbnails instead.

Gemini analysis behavior:
Add a backend service that sends the selected reel/video to Gemini for analysis.

The Gemini prompt should ask it to:
- summarize what happens in the reel
- identify the likely business/marketing angle
- write a social media caption in a confident, modern, slightly witty, professional tone
- avoid cringe corporate language
- keep the caption practical and post-ready
- generate hashtags separately
- suggest best platform: Instagram, Facebook, TikTok, YouTube Shorts, LinkedIn
- identify if the reel seems unsuitable, unclear, low quality, or needs human review

The AI output should be structured JSON if possible:
{
  "summary": "...",
  "suggested_post": "...",
  "hashtags": ["...", "..."],
  "category": "...",
  "platform_suggestion": "...",
  "quality_notes": "..."
}

The app must handle malformed AI responses gracefully.

Tone for generated social posts:
- professional but not stiff
- energetic
- concise
- modern
- slightly witty when appropriate
- no cheesy influencer garbage
- suitable for a roofing/construction/home-services company unless the user later changes the brand context

CLI requirements:
Create a CLI command named reelctl.

CLI commands:
reelctl scan
- scans the reel folder

reelctl list
- lists reels with id, filename, status, approved, has final post

reelctl show <id>
- shows all info for one reel

reelctl set-post <id> "caption text"
- updates manual_post_text or final_post_text; choose final_post_text by default

reelctl set-hashtags <id> "#roofing #gutters"
- updates hashtags

reelctl approve <id>
- approved = true

reelctl status <id> ready
- updates status

reelctl analyze <id>
- runs Gemini analysis

reelctl next-ready
- returns the next approved, ready, postable reel

reelctl export-ready --format json
- exports ready queue as JSON

reelctl export-ready --format csv
- exports ready queue as CSV

Important CLI behavior:
The CLI and web dashboard must use the same SQLite database.
CLI output should be clean and useful for AI agents.
Use clear exit codes and readable error messages.
Never silently fail.

Suggested folder structure:
reelvault/
  backend/
    app/
      main.py
      database.py
      models.py
      schemas.py
      settings.py
      scanner.py
      thumbnails.py
      gemini_service.py
      routes/
        reels.py
        queue.py
        health.py
    requirements.txt
  frontend/
    src/
      App.tsx
      main.tsx
      api.ts
      components/
      pages/
      styles/
    package.json
    tailwind.config.js
  cli/
    reelctl.py
  data/
    thumbnails/
  .env.example
  README.md
  docker-compose.yml optional
  start.sh optional

README requirements:
Write clear setup instructions:
1. install backend dependencies
2. install frontend dependencies
3. copy .env.example to .env
4. set REELS_FOLDER
5. add GEMINI_API_KEY if desired
6. run backend
7. run frontend
8. scan reels
9. use CLI examples

Testing requirements:
Add basic backend tests for:
- database creation
- scanning folder
- updating reel fields
- ready queue validation
- Gemini-disabled behavior

UX requirements:
- Autosave or obvious Save button
- Clear success/error toasts
- Loading states
- Empty states
- No data loss
- Confirm before destructive/archive actions
- Fast enough to handle at least 500 reels

Critical implementation rules:
- Do not overwrite manual user-written captions with AI text.
- Do not mark a reel ready unless it has final_post_text.
- Do not require Gemini for the app to function.
- Do not duplicate video files.
- Do not make the UI look like a fake crypto analytics dashboard.
- Do not add random charts/gauges just because the color reference image has them.
- Build the app so future agents can safely interact through CLI/API.
- Prefer simple, maintainable code over over-engineered nonsense.
- Make everything run locally.
- Include useful comments where helpful.
- Make the first version fully runnable.

Final deliverable:
Generate the complete project with all files needed for a working MVP. Include backend, frontend, CLI, database setup, Gemini integration stub/implementation, README, and example environment file.
```

I’d use that as the main build prompt. It’s strict enough to stop the AI from building some neon Las Vegas airplane cockpit, but detailed enough to get the real tool scaffolded.



---
Powered by [ChatGPT Exporter](https://www.chatgptexporter.com)