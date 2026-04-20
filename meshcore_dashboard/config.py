"""Application settings loaded from environment variables."""

from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Dashboard configuration with fail-closed auth."""

    serial_port: str = "/dev/ttyACM0"
    serial_baud: int = 115200
    poll_interval_default: int = 60
    poll_interval_live: int = 10
    live_mode_ttl: int = 30
    db_path: str = "data/meshcore.db"
    read_only: bool = False
    auth_disabled: bool = False
    basic_auth_user: str = ""
    basic_auth_pass: str = ""

    model_config = {"env_prefix": "", "case_sensitive": False}

    @model_validator(mode="after")
    def check_auth(self) -> Settings:
        if not self.auth_disabled and (
            not self.basic_auth_user or not self.basic_auth_pass
        ):
            raise ValueError(
                "BASIC_AUTH_USER/PASS must be set, or set AUTH_DISABLED=1 "
                "to explicitly run without authentication."
            )
        return self
