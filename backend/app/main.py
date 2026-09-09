from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import logging
from pathlib import Path

from .settings import settings
from .database import init_db
from .routes import health, reels, queue, archive, v1
from .archive import ArchiveWorker
from .auth import AuthMiddleware, router as auth_router
from .jobs import JobWorker
from .previews import previews
from .dropbox_storage import StorageError
from fastapi.responses import JSONResponse, FileResponse

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
    jobs = JobWorker()
    if settings.VM_JOBS_ENABLED:
        jobs.start()
        previews.start()
    worker = ArchiveWorker()
    worker.start()
    try:
        yield
    finally:
        worker.stop()
        previews.stop()
        jobs.stop()

app = FastAPI(
    lifespan=lifespan,
    title="ReelVault API",
    description="Local-first video archive, caption assistant, and approved social queue manager.",
    version="2.0.0"
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
app.include_router(v1.router, prefix="/api")
app.include_router(auth_router)
app.add_middleware(AuthMiddleware)


@app.exception_handler(StorageError)
async def storage_error(request, exc):
    return JSONResponse(status_code=exc.status, content={"detail": str(exc), "code": "storage_unavailable"})


@app.get('/healthz', include_in_schema=False)
def liveness():
    return {"status": "ok"}

@app.get("/")
def index():
    if (settings.FRONTEND_DIST / 'index.html').is_file():
        return FileResponse(settings.FRONTEND_DIST / 'index.html')
    return {
        "message": "Welcome to ReelVault Local API command center. Renders synthwave dashboards locally.",
        "docs_url": "/docs",
        "health_check": "/api/health"
    }


@app.get('/favicon.svg', include_in_schema=False)
def favicon():
    from fastapi import HTTPException
    path = settings.FRONTEND_DIST / 'favicon.svg'
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type='image/svg+xml')


if (settings.FRONTEND_DIST / 'assets').is_dir():
    app.mount('/assets', StaticFiles(directory=settings.FRONTEND_DIST / 'assets'), name='frontend-assets')

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=True
    )
