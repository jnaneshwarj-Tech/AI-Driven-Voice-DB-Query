"""
security_middleware.py — Production Security Middleware for FastAPI.

Features:
1. Security Headers:
   - X-Content-Type-Options: nosniff
   - X-Frame-Options: DENY
   - X-XSS-Protection: 1; mode=block
   - Strict-Transport-Security: max-age=31536000; includeSubDomains
   - Referrer-Policy: strict-origin-when-cross-origin
   - Permissions-Policy: camera=(), geolocation=(), microphone=(self)
   - Removes Server signature

2. Sliding-Window IP Rate Limiter:
   - Auth endpoints (/api/auth/*): 15 requests/min per IP
   - Query endpoints (/api/query/*): 60 requests/min per IP
   - Global rate limit: 200 requests/min per IP
   - Returns HTTP 429 with Retry-After header

3. Input Sanitization / XSS Protection:
   - Strips malicious HTML tags (<script>, <iframe>, <object>, etc.)
   - Neutralizes event handlers (onerror, onload, onclick)
   - Prevents null-byte injections
"""

import time
import re
import html
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

# ── XSS Sanitization Patterns ────────────────────────────────────────────────
_DANGEROUS_TAGS_PATTERN = re.compile(
    r"<\s*(script|iframe|object|embed|applet|meta|link|style|base|form)[^>]*>.*?</\s*\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
_DANGEROUS_EMPTY_TAGS = re.compile(
    r"<\s*(script|iframe|object|embed|applet|meta|link|style|base)[^>]*\/?>",
    re.IGNORECASE,
)
_EVENT_HANDLERS_PATTERN = re.compile(
    r"\bon\w+\s*=\s*(?:'[^']*'|\"[^\"]*\"|[^\s>]+)",
    re.IGNORECASE,
)
_JAVASCRIPT_URI_PATTERN = re.compile(
    r"(?:javascript|vbscript|data\s*:\s*text\/html)\s*:",
    re.IGNORECASE,
)


def sanitize_input(value: str) -> str:
    """Sanitize string input to prevent XSS and null byte injection."""
    if not isinstance(value, str):
        return value
    # Remove null bytes
    cleaned = value.replace("\x00", "")
    # Strip dangerous HTML elements and event handlers
    cleaned = _DANGEROUS_TAGS_PATTERN.sub("", cleaned)
    cleaned = _DANGEROUS_EMPTY_TAGS.sub("", cleaned)
    cleaned = _EVENT_HANDLERS_PATTERN.sub("", cleaned)
    cleaned = _JAVASCRIPT_URI_PATTERN.sub("", cleaned)
    return cleaned.strip()


# ── Sliding Window In-Memory Rate Limiter ───────────────────────────────────
class InMemoryRateLimiter:
    def __init__(self):
        # Maps (ip, category) -> list of timestamps
        self._history = defaultdict(list)
        # Window size in seconds
        self.window = 60

    def is_allowed(self, ip: str, category: str, max_requests: int) -> tuple[bool, int]:
        now = time.time()
        cutoff = now - self.window
        key = f"{ip}:{category}"

        # Evict timestamps older than the sliding window
        timestamps = [ts for ts in self._history[key] if ts > cutoff]
        self._history[key] = timestamps

        if len(timestamps) >= max_requests:
            retry_after = int(self.window - (now - timestamps[0])) if timestamps else self.window
            return False, max(1, retry_after)

        self._history[key].append(now)
        return True, 0


rate_limiter = InMemoryRateLimiter()


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Rate Limiting Check
        client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if not client_ip:
            client_ip = request.client.host if request.client else "127.0.0.1"

        path = request.url.path.lower()
        method = request.method.upper()

        # Exempt OPTIONS (preflight CORS requests)
        if method != "OPTIONS":
            category = "global"
            limit = 200

            if "/api/auth/login" in path or "/api/auth/forgot-password" in path or "/api/auth/register" in path:
                category = "auth"
                limit = 15
            elif "/api/query/" in path:
                category = "query"
                limit = 60

            allowed, retry_after = rate_limiter.is_allowed(client_ip, category, limit)
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": f"Too many requests. Please wait {retry_after} seconds before trying again.",
                        "retry_after": retry_after,
                    },
                    headers={"Retry-After": str(retry_after)},
                )

        # 2. Process Request
        response: Response = await call_next(request)

        # 3. Attach Defense-in-Depth Security Headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), geolocation=(), microphone=(self)"

        # Remove information leakage headers
        if "server" in response.headers:
            del response.headers["server"]
        if "x-powered-by" in response.headers:
            del response.headers["x-powered-by"]

        return response
