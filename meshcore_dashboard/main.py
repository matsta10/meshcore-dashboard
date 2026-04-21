"""FastAPI application with lifespan, middleware, and static serving."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from meshcore_dashboard.config import Settings
from meshcore_dashboard.database import create_engine_and_tables
from meshcore_dashboard.middleware.auth import BasicAuthMiddleware
from meshcore_dashboard.middleware.readonly import ReadOnlyMiddleware
from meshcore_dashboard.routers import (
    commands as commands_router,
)
from meshcore_dashboard.routers import (
    config as config_router,
)
from meshcore_dashboard.routers import (
    logs as logs_router,
)
from meshcore_dashboard.routers import (
    neighbors as neighbors_router,
)
from meshcore_dashboard.routers import (
    stats as stats_router,
)
from meshcore_dashboard.routers import (
    status as status_router,
)
from meshcore_dashboard.routers import (
    websocket as ws_router,
)
from meshcore_dashboard.serial.connection import RepeaterConnection
from meshcore_dashboard.services.poller import Poller
from meshcore_dashboard.services.retention import RetentionService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    """Application startup and shutdown."""
    settings = Settings()

    # Database
    db_url = f"sqlite+aiosqlite:///{settings.db_path}"
    engine, session_factory = await create_engine_and_tables(db_url)

    # Serial connection
    connection = RepeaterConnection(
        port=settings.serial_port, baud=settings.serial_baud
    )
    try:
        await connection.connect()
        logger.info("Connected to repeater at %s", settings.serial_port)
    except ConnectionError as e:
        logger.warning("Could not connect to repeater: %s", e)

    # Wire dependencies
    poller = Poller(connection, session_factory)
    status_router.set_dependencies(connection, session_factory, poller=poller)
    config_router.set_dependencies(connection, session_factory)
    neighbors_router.set_dependencies(connection, session_factory)
    logs_router.set_dependencies(connection, session_factory)
    commands_router.set_dependencies(connection)

    # Start background services
    stats_router.set_dependencies(session_factory, poller=poller)
    if connection.state.value == "connected":
        await poller.sync_device_state(detect_drift=False)
    poller.start()

    retention = RetentionService(session_factory, settings.db_path)
    retention.start()

    yield

    # Shutdown
    await poller.stop()
    await retention.stop()
    await connection.disconnect()
    await engine.dispose()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = Settings()

    app = FastAPI(
        title="MeshCore Dashboard",
        lifespan=lifespan,
    )

    # Middleware (order matters: first added = outermost)
    if settings.read_only:
        app.add_middleware(ReadOnlyMiddleware)

    if not settings.auth_disabled:
        app.add_middleware(
            BasicAuthMiddleware,
            username=settings.basic_auth_user,
            password=settings.basic_auth_pass,
        )

    # Routers
    app.include_router(status_router.router)
    app.include_router(stats_router.router)
    app.include_router(config_router.router)
    app.include_router(neighbors_router.router)
    app.include_router(logs_router.router)
    app.include_router(commands_router.router)
    app.include_router(ws_router.router)

    # Static files (frontend build output)
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount(
            "/",
            StaticFiles(directory=static_dir, html=True),
            name="static",
        )

    return app


app = create_app()
