import os
from pathlib import Path
from urllib.parse import urlsplit
from dotenv import load_dotenv

# Load env variables from root folder
env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=env_path)

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
LEGACY_GEMINI_MODELS = {"gemini-1.5-pro"}

def clean_path_string(path_str: str) -> str:
    if not path_str:
        return path_str
    
    # Remove enclosing quotes
    path_str = path_str.strip('\'"')
    
    # Unescape backslash-escapes commonly pasted from terminal on Unix/macOS
    escaped_chars = [' ', '~', '(', ')', '&', "'", '"', '$', '`', '!', '*', '?', '[', ']', '{', '}', ';', '<', '>', '|']
    for char in escaped_chars:
        path_str = path_str.replace(f"\\{char}", char)
        
    # Handle literal backslashes that were doubled
    path_str = path_str.replace("\\\\", "\\")
    return path_str

def normalize_gemini_model(model_name: str) -> str:
    cleaned_model = (model_name or "").strip()
    if not cleaned_model:
        return DEFAULT_GEMINI_MODEL
    if cleaned_model in LEGACY_GEMINI_MODELS:
        return DEFAULT_GEMINI_MODEL
    return cleaned_model

class Settings:
    PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
    
    def __init__(self):
        icloud_root = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/SnapIGTik Download"
        reels_val = clean_path_string(os.getenv("REELS_FOLDER", str(icloud_root) if icloud_root.is_dir() else "./reels"))
        db_val = clean_path_string(os.getenv("DATABASE_PATH", "./data/reelvault.db"))
        thumbs_val = clean_path_string(os.getenv("THUMBNAILS_FOLDER", "./data/thumbnails"))
        
        # If paths are relative, anchor them to PROJECT_ROOT
        self.REELS_FOLDER = Path(reels_val) if Path(reels_val).is_absolute() else (self.PROJECT_ROOT / reels_val).resolve()
        self.DATABASE_PATH = Path(db_val) if Path(db_val).is_absolute() else (self.PROJECT_ROOT / db_val).resolve()
        self.THUMBNAILS_FOLDER = Path(thumbs_val) if Path(thumbs_val).is_absolute() else (self.PROJECT_ROOT / thumbs_val).resolve()
        
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
        self.GEMINI_MODEL = normalize_gemini_model(os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL))
        self.QUICK_SUMMARY_MODEL = os.getenv("QUICK_SUMMARY_MODEL", "gemini-2.5-flash-lite").strip()
        self.AUTO_SCAN = os.getenv("AUTO_SCAN", "true").lower() == "true"
        self.SCAN_INTERVAL_SECONDS = max(30, int(os.getenv("SCAN_INTERVAL_SECONDS", "900")))
        self.AUTO_QUICK_SUMMARY = os.getenv("AUTO_QUICK_SUMMARY", "true").lower() == "true"
        self.FILE_SETTLE_SECONDS = max(0, int(os.getenv("FILE_SETTLE_SECONDS", "60")))
        self.QUICK_SUMMARY_DELAY_SECONDS = max(1, float(os.getenv("QUICK_SUMMARY_DELAY_SECONDS", "4")))
        self.QUICK_SUMMARY_DAILY_BUDGET_USD = max(0, float(os.getenv("QUICK_SUMMARY_DAILY_BUDGET_USD", "1")))
        
        self.APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
        self.APP_PORT = int(os.getenv("APP_PORT", "8000"))
        self.FRONTEND_PORT = int(os.getenv("FRONTEND_PORT", "5173"))
        self.STORAGE_PROVIDER = os.getenv("STORAGE_PROVIDER", "local")
        if self.STORAGE_PROVIDER not in {"local", "dropbox"}:
            raise ValueError("STORAGE_PROVIDER must be local or dropbox")
        self.CACHE_FOLDER = Path(os.getenv("CACHE_FOLDER", str(self.DATABASE_PATH.parent / "cache"))).resolve()
        self.CACHE_MAX_BYTES = int(os.getenv("CACHE_MAX_BYTES", "5000000000"))
        self.CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "43200"))
        self.PREVIEWS_FOLDER = self.DATABASE_PATH.parent / "previews"
        self.PREVIEW_MAX_BYTES = max(5_000_000, int(os.getenv("PREVIEW_MAX_BYTES", "1000000000")))
        self.AUTO_PREVIEWS = os.getenv("AUTO_PREVIEWS", "true").lower() == "true"
        self.PREVIEW_DELAY_SECONDS = max(1, float(os.getenv("PREVIEW_DELAY_SECONDS", "10")))
        self.MIN_FREE_DISK_BYTES = int(os.getenv("MIN_FREE_DISK_BYTES", "5000000000"))
        self.MAX_CONCURRENT_DOWNLOADS = max(1, min(5, int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "5"))))
        self.AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "false").lower() == "true"
        self.ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
        self.AGENT_TOKEN = os.getenv("AGENT_TOKEN", "")
        self.COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"
        self.PUBLIC_ORIGIN = os.getenv("PUBLIC_ORIGIN", "http://127.0.0.1:18765").rstrip("/")
        self.FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST", str(self.PROJECT_ROOT / "frontend/dist")))
        self.DROPBOX_CREDENTIALS_PATH = self.DATABASE_PATH.parent / "secrets/dropbox.json"
        self.VM_JOBS_ENABLED = os.getenv("VM_JOBS_ENABLED", "true").lower() == "true"
        if self.AUTH_REQUIRED and (len(self.ADMIN_TOKEN) < 32 or len(self.AGENT_TOKEN) < 32
                                   or self.ADMIN_TOKEN == self.AGENT_TOKEN):
            raise ValueError("Authenticated hosting needs distinct ADMIN_TOKEN and AGENT_TOKEN (32+ characters)")

    @property
    def allowed_browser_origins(self) -> set[str]:
        """Permit equivalent loopback names, never arbitrary request/forwarded hosts."""
        origins = {self.PUBLIC_ORIGIN}
        parsed = urlsplit(self.PUBLIC_ORIGIN)
        if (parsed.scheme in {"http", "https"}
                and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
                and parsed.username is None and parsed.password is None
                and not parsed.path and not parsed.query and not parsed.fragment):
            default_port = 443 if parsed.scheme == "https" else 80
            port = f":{parsed.port}" if parsed.port and parsed.port != default_port else ""
            origins.update(f"{parsed.scheme}://{host}{port}"
                           for host in ("localhost", "127.0.0.1", "[::1]"))
        return origins

    @property
    def is_gemini_enabled(self) -> bool:
        return bool(self.GEMINI_API_KEY.strip())

settings = Settings()
