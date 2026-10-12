"""Project paths and database settings (read from the environment or .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = PROJECT_ROOT / "sql"
DATA_DIR = PROJECT_ROOT / "data"

DEFAULT_DSN = "localhost:1521/FREEPDB1"


@dataclass(frozen=True)
class Settings:
    user: str
    password: str
    dsn: str = DEFAULT_DSN
    client_lib_dir: str | None = None

    @classmethod
    def from_env(cls) -> Settings:
        """Build settings from environment variables, falling back to .env.

        Variables already set in the environment (e.g. in CI) take precedence
        over values in .env.
        """
        load_dotenv(PROJECT_ROOT / ".env")
        missing = [name for name in ("DB_USER", "DB_PASSWORD") if not os.getenv(name)]
        if missing:
            raise RuntimeError(
                f"Missing {', '.join(missing)}. Copy .env.example to .env and fill it in."
            )
        return cls(
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            dsn=os.getenv("DB_DSN") or DEFAULT_DSN,
            client_lib_dir=os.getenv("ORACLE_CLIENT_LIB_DIR") or None,
        )
