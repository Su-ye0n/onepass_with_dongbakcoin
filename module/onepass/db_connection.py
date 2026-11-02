
# onepass/db_connection.py

"""Read-only PostgreSQL connection for OnePass P0."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


class DatabaseConfigurationError(ValueError):
    pass


def get_database_url(
    env_path: str | Path | None = None,
) -> str:
    if env_path is None:
        load_dotenv()
    else:
        load_dotenv(dotenv_path=env_path, override=True)

    url = os.getenv("DATABASE_URL", "").strip()

    if not url:
        raise DatabaseConfigurationError(
            "DATABASE_URL_NOT_CONFIGURED"
        )

    if not url.startswith(
        ("postgresql://", "postgres://")
    ):
        raise DatabaseConfigurationError(
            "DATABASE_URL_MUST_BE_POSTGRESQL"
        )

    return url


def connect_readonly(
    database_url: str | None = None,
):
    """Open a read-only connection to NeonDB."""

    import psycopg
    from psycopg.rows import dict_row

    url = (
        database_url
        if database_url is not None
        else get_database_url()
    )

    if not url.startswith(
        ("postgresql://", "postgres://")
    ):
        raise DatabaseConfigurationError(
            "DATABASE_URL_MUST_BE_POSTGRESQL"
        )

    connection = psycopg.connect(
        url,
        row_factory=dict_row,
        autocommit=False,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
    )

    return connection
