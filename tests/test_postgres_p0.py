
# tests/test_postgres_p0.py

import pytest

from onepass.db_connection import (
    DatabaseConfigurationError,
    get_database_url,
)

from onepass.repository_postgres import (
    P0_TABLES,
    PostgresP0Repository,
    inspect_schema_metadata,
)


def make_minimal_metadata():
    from onepass.repository_postgres import (
        REQUIRED_CORE_COLUMNS,
    )

    return {
        name: set(REQUIRED_CORE_COLUMNS.get(name, set()))
        for name in P0_TABLES
    }


def test_p0_table_count():
    assert len(P0_TABLES) == 20
    assert len(set(P0_TABLES)) == 20


def test_complete_core_metadata():
    discovered = make_minimal_metadata()

    missing_tables, missing_columns = (
        inspect_schema_metadata(discovered)
    )

    assert missing_tables == ()
    assert missing_columns == {}


def test_missing_table_detected():
    discovered = make_minimal_metadata()
    del discovered["USER_CARD"]

    missing_tables, _ = inspect_schema_metadata(
        discovered
    )

    assert "USER_CARD" in missing_tables


def test_missing_core_column_detected():
    discovered = make_minimal_metadata()
    discovered["USER_CARD"].remove("product_id")

    _, missing_columns = inspect_schema_metadata(
        discovered
    )

    assert "USER_CARD" in missing_columns
    assert "product_id" in missing_columns["USER_CARD"]


def test_lowercase_postgres_names():
    discovered = {
        name.lower(): {
            col.lower() for col in columns
        }
        for name, columns in (
            make_minimal_metadata().items()
        )
    }

    missing_tables, missing_columns = (
        inspect_schema_metadata(discovered)
    )

    assert missing_tables == ()
    assert missing_columns == {}


def test_missing_database_url(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")

    with pytest.raises(
        DatabaseConfigurationError,
        match="DATABASE_URL_NOT_CONFIGURED",
    ):
        get_database_url(env_file)


def test_non_postgres_url_rejected(
    tmp_path,
    monkeypatch,
):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=sqlite:///example.db",
        encoding="utf-8",
    )

    with pytest.raises(
        DatabaseConfigurationError,
        match="DATABASE_URL_MUST_BE_POSTGRESQL",
    ):
        get_database_url(env_file)


def test_postgres_url_accepted(
    tmp_path,
    monkeypatch,
):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql://u:p@localhost/db",
        encoding="utf-8",
    )

    assert get_database_url(env_file) == (
        "postgresql://u:p@localhost/db"
    )


def test_invalid_schema_name():
    with pytest.raises(
        ValueError,
        match="INVALID_SCHEMA_NAME",
    ):
        PostgresP0Repository(
            schema_name=""
        )


def test_invalid_table_rejected_without_db():
    repo = PostgresP0Repository()

    with pytest.raises(
        ValueError,
        match="UNKNOWN_P0_TABLE",
    ):
        repo.fetch_table("untrusted_table")


def test_invalid_limit_rejected_without_db():
    repo = PostgresP0Repository()

    with pytest.raises(
        ValueError,
        match="INVALID_LIMIT",
    ):
        repo.fetch_table("USER_CARD", limit=0)


def test_boolean_limit_rejected_without_db():
    repo = PostgresP0Repository()

    with pytest.raises(
        ValueError,
        match="INVALID_LIMIT",
    ):
        repo.fetch_table("USER_CARD", limit=True)
