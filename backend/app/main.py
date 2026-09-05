from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import logging
from pathlib import Path

from .settings import settings
from .database import init_db
from .routes import health, reels, queue, archive
from .archive import ArchiveWorker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("reelvault.main")

# Initialize database
logger.info("Initializing SQLite database tables...")
init_db()

# Ensure directories exist
Path(settings.THUMBNAILS_FOLDER).mkdir(parents=True, exist_ok=True)

@asynccontextmanager
async def lifespan(app):
    worker = ArchiveWorker()
    worker.start()
    try:
        yield
    finally:
        worker.stop()

app = FastAPI(
    lifespan=lifespan,
    title="ReelVault API",
    description="Local-first video archive, caption assistant, and approved social queue manager.",
    version="1.1.0"
)

# CORS Configuration
# Standard local development config allowing Vite access
app.add_middleware(
    CORSMiddleware,
    allow_origins=[f"http://127.0.0.1:{settings.FRONTEND_PORT}", f"http://localhost:{settings.FRONTEND_PORT}"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount thumbnail serving static route
try:
    app.mount(
        "/thumbnails",
        StaticFiles(directory=str(Path(settings.THUMBNAILS_FOLDER).resolve())),
        name="thumbnails"
    )
    logger.info(f"Mounted Thumbnails static serving at /thumbnails from: {settings.THUMBNAILS_FOLDER}")
except Exception as e:
    logger.error(f"Failed to mount static Thumbnails folder: {e}")

# Include API routers
app.include_router(health.router, prefix="/api")
app.include_router(reels.router, prefix="/api")
app.include_router(queue.router, prefix="/api")
app.include_router(archive.router, prefix="/api")

@app.get("/")
def index():
    return {
        "message": "Welcome to ReelVault Local API command center. Renders synthwave dashboards locally.",
        "docs_url": "/docs",
        "health_check": "/api/health"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=True
    )
