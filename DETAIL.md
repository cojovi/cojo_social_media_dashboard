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
GEMINI_MODEL=gemini-2.5-flash
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