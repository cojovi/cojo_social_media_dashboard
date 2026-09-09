"""Synthetic media fixture for a SEPARATE, disposable QA data directory only."""
import os
import subprocess
from pathlib import Path

if os.getenv('REELVAULT_QA') != 'true':
    raise RuntimeError('Refusing to seed outside an explicit QA container')
from app.settings import settings
from app.database import init_db
from app.scanner import scan_reels_folder
from app import models

settings.REELS_FOLDER.mkdir(parents=True, exist_ok=True)
video = settings.REELS_FOLDER / 'ReelVault_test_pattern.mp4'
if not video.exists():
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=360x640:rate=24',
                    '-t', '5', '-c:v', 'libx264', '-threads', '1', '-pix_fmt', 'yuv420p',
                    '-movflags', '+faststart', str(video)], check=True)
init_db()
scan_reels_folder()
for reel in models.get_all_reels():
    models.update_reel(reel['id'], {'notes': 'Synthetic QA fixture, not part of the real archive.'})
print('Seeded synthetic QA fixture.')
