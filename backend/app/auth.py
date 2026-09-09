"""Single-owner browser sessions and a separate, deliberately limited agent token."""
import hashlib
import hmac
import re
import secrets
import time
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from .settings import settings

router = APIRouter(prefix="/api/auth", tags=["authentication"])
COOKIE = "reelvault_session"
sessions: dict[str, float] = {}
login_attempts: dict[str, list[float]] = {}


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def role_for(request):
    if not settings.AUTH_REQUIRED:
        return "admin"
    token = request.headers.get("authorization", "").removeprefix("Bearer ")
    if token and hmac.compare_digest(token, settings.ADMIN_TOKEN):
        return "admin"
    if token and hmac.compare_digest(token, settings.AGENT_TOKEN):
        return "agent"
    session = request.cookies.get(COOKIE, "")
    if sessions.get(digest(session), 0) > time.time():
        return "admin"
    return None


def agent_allowed(method, path):
    # Legacy mutations intentionally excluded: the agent cannot approve its own content.
    if method in {"GET", "HEAD"}:
        return bool(re.fullmatch(r"/api/v1/(guide|queue/ready|reels(?:/\d+(?:/download|/video|/preview(?:/video)?)?)?|jobs(?:/[a-f0-9]+)?|storage|publications(?:/[a-f0-9]+)?)", path)) or path == "/openapi.json"
    if method == "POST":
        return path == "/api/v1/publications" or bool(re.fullmatch(
            r"/api/v1/(reels/\d+/materialize|publications/[a-f0-9]+/(renew|start|complete|release))", path))
    return False


class AuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request = Request(scope)
        path = request.url.path
        protected = path.startswith(("/api/", "/thumbnails")) or path in {"/docs", "/redoc", "/openapi.json"}
        public = path in {"/api/auth/login", "/api/auth/session", "/healthz"}
        role = role_for(request)
        error = None
        if protected and not public and not role:
            error = (401, "Authentication required")
        elif protected and role == "agent" and not agent_allowed(request.method, path):
            error = (403, "This operation requires the dashboard owner")
        # Browsers never need cross-origin writes. Prevent login CSRF as well as session CSRF.
        if settings.AUTH_REQUIRED and request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and origin not in settings.allowed_browser_origins:
                error = (403, "Origin is not allowed")
        if error:
            return await JSONResponse({"detail": error[1]}, status_code=error[0])(scope, receive, send)
        async def secure_send(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend([(b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"no-referrer"),
                                (b"x-frame-options", b"DENY")])
                if protected:
                    headers.append((b"cache-control", b"private, no-store"))
                message["headers"] = headers
            await send(message)
        await self.app(scope, receive, secure_send)


class Login(BaseModel):
    token: str = Field(max_length=256)


@router.get("/session")
def session(request: Request):
    return {"authenticated": role_for(request) == "admin", "auth_required": settings.AUTH_REQUIRED}


@router.post("/login")
def login(body: Login, request: Request, response: Response):
    now = time.time()
    host = request.client.host if request.client else "unknown"
    recent = [t for t in login_attempts.get(host, []) if t > now - 300]
    if len(recent) >= 10:
        raise HTTPException(429, "Too many attempts; try again in five minutes")
    if not settings.ADMIN_TOKEN or not hmac.compare_digest(body.token, settings.ADMIN_TOKEN):
        login_attempts[host] = recent + [now]
        raise HTTPException(401, "Invalid access token")
    for key, expiry in list(sessions.items()):
        if expiry < now:
            sessions.pop(key, None)
    token = secrets.token_urlsafe(32)
    sessions[digest(token)] = now + 86400
    response.set_cookie(COOKIE, token, httponly=True, secure=settings.COOKIE_SECURE,
                        samesite="strict", max_age=86400, path="/")
    return {"authenticated": True}


@router.post("/logout")
def logout(request: Request, response: Response):
    sessions.pop(digest(request.cookies.get(COOKIE, "")), None)
    response.delete_cookie(COOKIE)
    return {"authenticated": False}
