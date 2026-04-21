"""HTTP Basic Auth middleware with fail-closed default."""

from __future__ import annotations

import base64
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

EXEMPT_PATHS = {"/api/health"}


class BasicAuthMiddleware(BaseHTTPMiddleware):
    """Require Basic Auth on all routes except health."""

    def __init__(self, app: object, username: str, password: str) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._username = username
        self._password = password

    async def dispatch(self, request: Request, call_next: object) -> Response:
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)  # type: ignore[misc]

        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Basic "):
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="meshcore"'},
            )

        try:
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
            username, password = decoded.split(":", 1)
        except (ValueError, UnicodeDecodeError):
            return Response(status_code=401)

        if not (
            secrets.compare_digest(username, self._username)
            and secrets.compare_digest(password, self._password)
        ):
            return Response(status_code=401)

        return await call_next(request)  # type: ignore[misc]
