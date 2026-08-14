#!/bin/bash

# Define colors for beautiful retro arcade output
CYAN='\033[0;36m'
PINK='\033[0;35m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${PINK}"
echo "    ██████╗ ███████╗███████╗██╗     ██╗   ██╗ █████╗ ██╗   ██╗████████╗"
echo "    ██╔══██╗██╔════╝██╔════╝██║     ██║   ██║██╔══██╗██║   ██║╚══██╔══╝"
echo "    ██████╔╝█████╗  █████╗  ██║     ██║   ██║███████║██║   ██║   ██║   "
echo "    ██╔══██╗██╔══╝  ██╔══╝  ██║     ╚██╗ ██╔╝██╔══██║██║   ██║   ██║   "
echo "    ██║  ██║███████╗███████╗███████╗ ╚████╔╝ ██║  ██║╚██████╔╝   ██║   "
echo "    ╚═╝  ╚═╝╚══════╝╚══════╝╚══════╝  ╚═══╝  ╚═╝  ╚═╝ ╚═════╝    ╚═╝   "
echo -e "${NC}"
echo -e "${CYAN}--- Retro-Synthwave Social Media Command Center Booting Up ---${NC}\n"

# Locate script directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$DIR"

# Source environment variables if file exists (space-safe line parsing)
if [ -f .env ]; then
    echo -e "${GREEN}[INFO]${NC} Loading configurations from .env..."
    while IFS= read -r line || [ -n "$line" ]; do
        # Strip leading/trailing whitespaces
        line=$(echo "$line" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
        # Skip comments and empty lines
        if [[ ! "$line" =~ ^# ]] && [[ ! -z "$line" ]]; then
            export "$line"
        fi
    done < .env
else
    echo -e "${YELLOW}[WARNING]${NC} No .env file found in root. Using default configs."
fi

# Set default ports if not set in .env
BACKEND_PORT=${APP_PORT:-8000}
FRONTEND_PORT=${FRONTEND_PORT:-5173}
BACKEND_HOST=${APP_HOST:-127.0.0.1}

# Make sure SQLite parent folders exist
mkdir -p data/thumbnails
mkdir -p reels

# Function to clean up background processes on exit
cleanup() {
    echo -e "\n${PINK}[SHUTDOWN]${NC} Shutting down server processes gracefully..."
    # Terminate the entire process group
    kill $(jobs -p) 2>/dev/null
    exit 0
}

# Trap Ctrl+C (SIGINT) and SIGTERM
trap cleanup SIGINT SIGTERM

# Dynamically detect Python with required uvicorn & typer modules
PYTHON_EXEC=""
for p in "$CONDA_PREFIX/bin/python3" "$CONDA_PREFIX/bin/python" "python3" "python"; do
    if [ -n "$p" ] && [ -x "$(which "$p" 2>/dev/null)" ] && "$p" -c "import uvicorn, typer" &>/dev/null; then
        PYTHON_EXEC="$p"
        break
    fi
done

if [ -z "$PYTHON_EXEC" ]; then
    echo -e "${YELLOW}[WARNING]${NC} Could not verify python environment with uvicorn and typer. Falling back to default 'python3'."
    PYTHON_EXEC="python3"
else
    echo -e "${GREEN}[INFO]${NC} Using Python interpreter: $PYTHON_EXEC"
fi

# 1. Boot up FastAPI Backend
echo -e "${CYAN}[BACKEND]${NC} Starting FastAPI backend on http://${BACKEND_HOST}:${BACKEND_PORT}..."
PYTHONPATH=backend "$PYTHON_EXEC" -m uvicorn app.main:app --host "${BACKEND_HOST}" --port "${BACKEND_PORT}" --reload &
BACKEND_PID=$!

# 2. Boot up Vite Frontend
echo -e "${CYAN}[FRONTEND]${NC} Starting Vite dev server on http://127.0.0.1:${FRONTEND_PORT}..."
npm run dev --prefix frontend &
FRONTEND_PID=$!

# 3. Wait a moment then auto-open browser on macOS
sleep 2.5
if [ "$(uname)" == "Darwin" ]; then
    echo -e "${GREEN}[LAUNCH]${NC} Launching browser at http://127.0.0.1:${FRONTEND_PORT}..."
    open "http://127.0.0.1:${FRONTEND_PORT}"
fi

# Keep script running to monitor logs and intercept Ctrl+C
wait
