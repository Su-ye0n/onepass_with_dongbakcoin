
# check_neondb.py

"""Check NeonDB P0 schema without writing data."""

from onepass.repository_postgres import (
    P0_TABLES,
    PostgresP0Repository,
)


def main():
    repository = PostgresP0Repository(
    schema_name="public")

    audit = repository.audit_schema()

    print("\n=== OnePass NeonDB Schema Audit ===")
    print(f"Schema: {audit.schema_name}")

    print(
        f"Tables: {len(audit.present_tables)}"
        f"/{len(P0_TABLES)}"
    )

    counts = {
        table.logical_name: table.row_count
        for table in audit.tables
    }

    print("\n[Table rows]")

    for table_name in P0_TABLES:
        if table_name not in counts:
            print(f"MISSING  {table_name}")
        else:
            print(
                f"OK       {table_name:<28}"
                f"{counts[table_name]:>8} rows"
            )

    if audit.missing_columns:
        print("\n[Missing core columns]")

        for table_name, missing in (
            audit.missing_columns.items()
        ):
            print(
                f"{table_name}: {', '.join(missing)}"
            )

    print("\n[Result]")

    if audit.core_ok:
        print("P0 CORE SCHEMA: OK")
    else:
        print("P0 CORE SCHEMA: CHECK REQUIRED")

    if (
        audit.core_ok
        and all(count == 0 for count in counts.values())
    ):
        print(
            "All P0 tables are currently empty. "
            "This is expected before data loading."
        )


if __name__ == "__main__":
    main()
