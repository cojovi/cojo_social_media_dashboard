import os
from pathlib import Path
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
        reels_val = clean_path_string(os.getenv("REELS_FOLDER", "./reels"))
        db_val = clean_path_string(os.getenv("DATABASE_PATH", "./data/reelvault.db"))
        thumbs_val = clean_path_string(os.getenv("THUMBNAILS_FOLDER", "./data/thumbnails"))
        
        # If paths are relative, anchor them to PROJECT_ROOT
        self.REELS_FOLDER = Path(reels_val) if Path(reels_val).is_absolute() else (self.PROJECT_ROOT / reels_val).resolve()
        self.DATABASE_PATH = Path(db_val) if Path(db_val).is_absolute() else (self.PROJECT_ROOT / db_val).resolve()
        self.THUMBNAILS_FOLDER = Path(thumbs_val) if Path(thumbs_val).is_absolute() else (self.PROJECT_ROOT / thumbs_val).resolve()
        
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
        self.GEMINI_MODEL = normalize_gemini_model(os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL))
        
        self.APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
        self.APP_PORT = int(os.getenv("APP_PORT", "8000"))
        self.FRONTEND_PORT = int(os.getenv("FRONTEND_PORT", "5173"))

    @property
    def is_gemini_enabled(self) -> bool:
        return bool(self.GEMINI_API_KEY.strip())

settings = Settings()


