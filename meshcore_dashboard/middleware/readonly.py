"""Read-only mode middleware. Blocks all mutation methods."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class ReadOnlyMiddleware(BaseHTTPMiddleware):
    """Return 403 for all mutation requests."""

    async def dispatch(
        self, request: Request, call_next: object
    ) -> Response:
        if request.method in MUTATION_METHODS:
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "Server is in read-only mode"
                },
            )
        return await call_next(request)  # type: ignore[misc]
