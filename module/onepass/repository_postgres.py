
# onepass/repository_postgres.py

"""PostgreSQL read-only repository and P0 schema audit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from psycopg import sql

from .db_connection import connect_readonly


P0_TABLES = (
    "CARD_PRODUCT",
    "BENEFIT_RULE",
    "BENEFIT_INDUSTRY",
    "CARD_PERF_EXCLUDE",
    "BENEFIT_CAP_TIER",
    "DB_POLICY",
    "DB_POLICY_RATE",
    "DB_POLICY_BONUS",
    "MERCHANT",
    "BENEFIT_CATEGORY_MAP",
    "USER",
    "ONECARD",
    "USER_CATEGORY",
    "ACCOUNT",
    "DB_WALLET",
    "USER_CARD",
    "USER_CATEGORY_PRIORITY",
    "LEDGER",
    "CARD_MONTH_CLOSE",
    "CARD_PERF_MONTH_CLOSE",
)

# Minimum columns needed to identify core P0 relationships.
# This is not a full column-by-column ERD validation.
REQUIRED_CORE_COLUMNS = {
    "CARD_PRODUCT": {"product_id", "card_type"},
    "BENEFIT_RULE": {"rule_id", "product_id"},
    "BENEFIT_INDUSTRY": {"rule_id"},
    "DB_POLICY": {"policy_id"},
    "DB_POLICY_RATE": {"policy_id", "sales_band"},
    "MERCHANT": {"merchant_id"},
    "USER": {"user_id"},
    "USER_CARD": {
        "user_card_id", "user_id", "product_id"
    },
    "ACCOUNT": {"account_id", "user_id"},
    "DB_WALLET": {"wallet_id", "user_id"},
}


class PostgresRepositoryError(RuntimeError):
    pass


@dataclass(frozen=True)
class TableInfo:
    logical_name: str
    actual_name: str
    row_count: int
    columns: tuple[str, ...]


@dataclass(frozen=True)
class SchemaAudit:
    schema_name: str
    present_tables: tuple[str, ...]
    missing_tables: tuple[str, ...]
    missing_columns: dict[str, tuple[str, ...]]
    tables: tuple[TableInfo, ...]

    @property
    def core_ok(self) -> bool:
        return (
            not self.missing_tables
            and not self.missing_columns
        )


def inspect_schema_metadata(
    discovered: dict[str, set[str]],
) -> tuple[
    tuple[str, ...],
    dict[str, tuple[str, ...]],
]:
    """Pure validation helper, usable without any DB."""

    present = {
        name.upper(): {
            column.lower() for column in columns
        }
        for name, columns in discovered.items()
    }

    missing_tables = tuple(
        name
        for name in P0_TABLES
        if name not in present
    )

    missing_columns = {}

    for table_name, required in (
        REQUIRED_CORE_COLUMNS.items()
    ):
        if table_name not in present:
            continue

        missing = required - present[table_name]

        if missing:
            missing_columns[table_name] = tuple(
                sorted(missing)
            )

    return missing_tables, missing_columns


class PostgresP0Repository:
    """Read-only access to the P0 PostgreSQL schema."""

    def __init__(
        self,
        database_url: str | None = None,
        schema_name: str = "public",
    ):
        if not schema_name or "\x00" in schema_name:
            raise ValueError("INVALID_SCHEMA_NAME")

        self.database_url = database_url
        self.schema_name = schema_name

    def connect(self):
        return connect_readonly(self.database_url)

    def _discover(self, connection):
        """Discover real PostgreSQL table/column names."""

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    table_name,
                    column_name
                FROM information_schema.columns
                WHERE table_schema = %s
                ORDER BY table_name, ordinal_position
                """,
                (self.schema_name,),
            )
            rows = cursor.fetchall()

        discovered = {}

        for row in rows:
            name = row["table_name"]
            discovered.setdefault(name, set()).add(
                row["column_name"]
            )

        return discovered

    def _table_map(self, connection):
        discovered = self._discover(connection)

        mapped = {}

        for actual_name in discovered:
            logical_name = actual_name.upper()

            if logical_name in P0_TABLES:
                if logical_name in mapped:
                    raise PostgresRepositoryError(
                        "AMBIGUOUS_TABLE_NAME: "
                        + logical_name
                    )

                mapped[logical_name] = actual_name

        return mapped, discovered

    def _count_rows(
        self,
        connection,
        actual_name: str,
    ) -> int:
        query = sql.SQL(
            "SELECT COUNT(*) AS n FROM {}.{}"
        ).format(
            sql.Identifier(self.schema_name),
            sql.Identifier(actual_name),
        )

        with connection.cursor() as cursor:
            cursor.execute(query)
            result = cursor.fetchone()

        return int(result["n"])

    def audit_schema(self) -> SchemaAudit:
        """Inspect P0 tables. No INSERT/UPDATE/DDL."""

        with self.connect() as connection:
            mapped, discovered = self._table_map(
                connection
            )

            logical_columns = {
                logical_name: discovered[actual_name]
                for logical_name, actual_name
                in mapped.items()
            }

            missing_tables, missing_columns = (
                inspect_schema_metadata(
                    logical_columns
                )
            )

            tables = []

            for logical_name in P0_TABLES:
                actual_name = mapped.get(logical_name)

                if actual_name is None:
                    continue

                columns = tuple(
                    sorted(discovered[actual_name])
                )

                tables.append(
                    TableInfo(
                        logical_name=logical_name,
                        actual_name=actual_name,
                        row_count=self._count_rows(
                            connection,
                            actual_name,
                        ),
                        columns=columns,
                    )
                )

            return SchemaAudit(
                schema_name=self.schema_name,
                present_tables=tuple(
                    t.logical_name for t in tables
                ),
                missing_tables=missing_tables,
                missing_columns=missing_columns,
                tables=tuple(tables),
            )

    def fetch_table(
        self,
        table_name: str,
        *,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Read one approved P0 table."""

        logical = table_name.upper()

        if logical not in P0_TABLES:
            raise ValueError(
                f"UNKNOWN_P0_TABLE: {table_name}"
            )

        if not isinstance(limit, int) or (
            isinstance(limit, bool)
        ) or not 1 <= limit <= 100000:
            raise ValueError("INVALID_LIMIT")

        with self.connect() as connection:
            mapped, _ = self._table_map(connection)

            actual = mapped.get(logical)

            if actual is None:
                raise PostgresRepositoryError(
                    f"MISSING_TABLE: {logical}"
                )

            query = sql.SQL(
                "SELECT * FROM {}.{} LIMIT %s"
            ).format(
                sql.Identifier(self.schema_name),
                sql.Identifier(actual),
            )

            with connection.cursor() as cursor:
                cursor.execute(query, (limit,))
                return cursor.fetchall()

    def require_data(
        self,
        table_names: tuple[str, ...] = (
            "CARD_PRODUCT",
            "DB_POLICY",
            "MERCHANT",
        ),
    ) -> None:
        """Fail explicitly when core input tables are empty."""

        audit = self.audit_schema()

        if not audit.core_ok:
            raise PostgresRepositoryError(
                "P0_SCHEMA_NOT_READY"
            )

        counts = {
            item.logical_name: item.row_count
            for item in audit.tables
        }

        for name in table_names:
            logical = name.upper()

            if logical not in P0_TABLES:
                raise ValueError(
                    f"UNKNOWN_P0_TABLE: {name}"
                )

            if counts.get(logical, 0) == 0:
                raise PostgresRepositoryError(
                    f"REQUIRED_TABLE_EMPTY: {logical}"
                )
