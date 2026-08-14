# 🔮 ReelVault — Retro-Synthwave Local Social Media Command Center

ReelVault is a premium, local-first video reel archiving, AI caption-writing assistant, and approved social media queue manager. It is designed to catalog a local folder of backed-up video reels without duplicating files, generate automated captioning drafts using the official Gemini API, and maintain a strict approval gate for publishing queues.

The app features a custom **dark retro-synthwave/arcade console UI** (deep plum `#08040d` theme, glowing neon borders, scanlines, and bento status grids) and interfaces with a SQLite database shared concurrently with a powerful **Python Typer CLI (`reelctl`)**.

---

## 🚀 Key Features

*   **Zero-Copy Local Scanning**: Indexes local directories (`.mp4`, `.mov`, `.m4v`, `.avi`, `.webm`, `.mkv`) instantly and generates hover-preview thumbnails via `ffmpeg` without moving or duplicating your video files.
*   **Dual-Interface Design**: Share states, captions, approvals, and data models instantly between a beautiful, glowing Vite-React dashboard and a CLI interface (`reelctl`) designed for developer and AI-agent automation.
*   **Official Google GenAI Integration**: Uses the new official `google-genai` package to upload files to the Gemini Files API, safely analyze video visual context, write contextual captions, suggest hashtags, and auto-delete files immediately after inference.
*   **Manual Copy Safeguard**: Gemini output **never** overwrites your hand-written manual captions. The dashboard presents AI suggestions side-by-side with clear "Use AI Caption" copy utilities.
*   **Strict Queue Gates**: A reel only qualifies for the "Ready Queue" and auto-publishing when `status = 'ready'`, `approved = true`, and a non-empty `final_post_text` exists.
*   **Elegant Offline Fallback**: Does not crash if `GEMINI_API_KEY` is blank. The UI turns off AI generators gracefully while keeping manual editing and queues fully active.

---

## 📂 Project Structure

```text
cody_social_media_dash/
├── backend/                  # FastAPI Application
│   ├── app/
│   │   ├── routes/           # Endpoint routers (health, reels, queue)
│   │   ├── database.py       # SQLite connection and tables init
│   │   ├── settings.py       # Pydantic environment configurations
│   │   ├── models.py         # SQLite CRUD query transactions
│   │   ├── scanner.py        # Video filesystem crawler & ffprobe metrics
│   │   ├── thumbnails.py     # ffmpeg subprocess frame-extractor
│   │   └── gemini_service.py # Google GenAI Files API uploading & analysis
│   ├── tests/                # Pytest unit tests suite
│   └── requirements.txt      # Python dependencies (fastapi, google-genai, typer...)
├── frontend/                 # Vite + React + TypeScript + Tailwind CSS v4 Dashboard
│   ├── src/
│   │   ├── main.tsx          # React application mount
│   │   ├── App.tsx           # Full responsive arcade dashboard and player
│   │   ├── index.css         # Retro synthwave colors, animations & scanlines
│   │   └── api.ts            # Client HTTP API handlers
│   ├── package.json          # Node configurations and Tailwind plugins
│   └── vite.config.ts        # Vite proxy bindings for local serving
├── cli/
│   └── reelctl.py            # Executable Typer command-line manager
├── reels/                    # Mount directory containing your raw video files
├── data/
│   ├── thumbnails/           # Auto-generated image previews for video list
│   └── reelvault.db          # Database file populated by scanning
├── start.sh                  # Root bash runner (boots backend & frontend concurrently)
├── DETAIL.md                 # Original specifications
└── README.md                 # Project user guide
```

---

## ⚙️ Installation & Setup

### 1. System Requirements
- **Python**: version 3.10 to 3.13
- **Node.js**: version 18+ (with npm)
- **FFmpeg & FFprobe**: (Optional, but highly recommended for video thumbnail generation and duration checks). On macOS, install via Homebrew:
  ```bash
  brew install ffmpeg
  ```

### 2. Install Backend Dependencies
Run pip installer from the backend folder:
```bash
pip install -r backend/requirements.txt
```

### 3. Install Frontend Dependencies
Run npm installer from the frontend folder:
```bash
cd frontend && npm install && cd ..
```

### 4. Setup Environment Variables
Copy `.env.example` to `.env` in the project root:
```bash
cp .env.example .env
```
Ensure the configurations are correct:
- `REELS_FOLDER`: Absolute path to your local folder of videos. By default, it will create and look in `./reels` in the project root.
- `GEMINI_API_KEY`: Provide your Google AI Studio API Key to enable video visual parsing. If empty, the app boots in **Offline mode** with AI buttons gracefully informing you key is missing.

---

## 🎮 How to Run

Simply boot the orchestrator script from the root workspace:
```bash
./start.sh
```

**What happens next?**
1. FastAPI boots up in the background on `http://127.0.0.1:8000`.
2. Vite dev (Frontend) server boots concurrently on `http://127.0.0.1:5173`.
3. The script automatically opens your default web browser to the dashboard.
4. Hit the **"Rescan Folder"** button in the Settings tab to sync and parse your video folder!

---

## 🛠️ Command Line Interface (`reelctl`)

ReelVault features a CLI utility designed for automation scripts and AI agents. It uses the exact same sqlite database configuration.

To execute CLI commands, run `python3 cli/reelctl.py <command>`.

### Available Commands

| Command | Usage | Description |
|---|---|---|
| **scan** | `python3 cli/reelctl.py scan` | Scans `REELS_FOLDER` and adds newly discovered video reels into the database. |
| **list** | `python3 cli/reelctl.py list` | Displays indexed reels with ID, filename, status, approved flag, and final caption presence. |
| **show** | `python3 cli/reelctl.py show <id>` | Prints the full details of a single reel. |
| **set-post** | `python3 cli/reelctl.py set-post <id> "caption"` | Updates the `final_post_text` (default) or `manual_post_text` for a reel. |
| **set-hashtags** | `python3 cli/reelctl.py set-hashtags <id> "#tag1 #tag2"` | Updates the hashtags for a reel. |
| **approve** | `python3 cli/reelctl.py approve <id>` | Sets `approved = 1` for the specified reel. |
| **status** | `python3 cli/reelctl.py status <id> ready` | Updates the status of the reel (e.g. `ready`, `posted`, `archived`). |
| **analyze** | `python3 cli/reelctl.py analyze <id>` | Triggers Gemini API file uploading, waits for processing, and writes structured summary/captions. |
| **next-ready** | `python3 cli/reelctl.py next-ready` | Returns the next postable approved, ready reel in the publishing queue. |
| **export-ready** | `python3 cli/reelctl.py export-ready --format json` | Exports the publishing queue as JSON or CSV formatted documents. |

*Tip: Use `--help` on any command to view parameter info! (e.g., `python3 cli/reelctl.py set-post --help`)*

---

## 🧪 Running Automated Tests

Run the backend pytest tests from the root of your project:
```bash
PYTHONPATH=backend python3 -m pytest backend/tests
```
This isolates tests in temporary virtual folders and verifies database structures, scanning mechanisms, manual-caption overrides, status change locks, and offline fallback responses.

---

## 🎨 Visual Design Aesthetic

ReelVault features a premium **Retro Synthwave Arcade Command Center** styling:
- **Background**: Deep plum-black (`#08040d`) with subtle glassmorphism transparency card layouts.
- **Accents**: Glowing neon cyan, sunset gradients (`#f472b6` to `#fb923c`), and neon pink pulses.
- **Atmosphere**: Subtle terminal scanline grid patterns overlaying the workspace.
- **Metrics Bento**: Micro-counters display total catalogs, drafts, needs-review items, and ready queues for quick operations.

Enjoy organizing and writing captions in ReelVault! 🔮
