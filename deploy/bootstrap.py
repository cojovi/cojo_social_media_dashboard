"""Generate private test-instance credentials once. Run on the VM in its install directory."""
import os
import secrets
from pathlib import Path

root = Path.cwd()
env = root / "vmtest.env"
data = root / "data"
data.mkdir(mode=0o700, exist_ok=True)
if not env.exists():
    admin, agent = secrets.token_urlsafe(40), secrets.token_urlsafe(40)
    config = {
        "STORAGE_PROVIDER": "dropbox", "AUTH_REQUIRED": "true", "ADMIN_TOKEN": admin, "AGENT_TOKEN": agent,
        # HTTP only on an SSH-forwarded loopback port. Set true before adding public HTTPS.
        "COOKIE_SECURE": "false", "PUBLIC_ORIGIN": "http://127.0.0.1:18765",
        "AUTO_SCAN": "true", "SCAN_INTERVAL_SECONDS": "900", "AUTO_QUICK_SUMMARY": "false",
        "GEMINI_API_KEY": "", "MAX_CONCURRENT_DOWNLOADS": "5", "CACHE_MAX_BYTES": "5000000000",
        "CACHE_TTL_SECONDS": "43200", "MIN_FREE_DISK_BYTES": "5000000000",
        "QUICK_SUMMARY_DAILY_BUDGET_USD": "1",
    }
    fd = os.open(env, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write("".join(f"{k}={v}\n" for k, v in config.items()))
    fd = os.open(root / "access.txt", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write("ReelVault vmtest credentials. Keep private; never commit.\n\n")
        stream.write(f"Dashboard: http://127.0.0.1:18765\nOwner access token: {admin}\nAgent bearer token: {agent}\n")
    print("Created private configuration and access.txt; token values are not printed.")
else:
    print("Existing configuration preserved.")
