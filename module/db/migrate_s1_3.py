
"""Backward compatible benefit_rule effective dating migration.

Run against a BACKUP or copy first. Does not change or duplicate existing rules.
Existing rows are valid indefinitely until edited with documented dates.
"""
from __future__ import annotations
import argparse
import sqlite3
from contextlib import closing
from pathlib import Path


def migrate(path: str | Path) -> None:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    with closing(sqlite3.connect(path)) as db:
        db.execute('PRAGMA foreign_keys=ON')
        columns = {r[1] for r in db.execute('PRAGMA table_info(benefit_rule)')}
        if 'rule_id' not in columns or 'product_id' not in columns:
            raise ValueError('unexpected benefit_rule schema')
        with db:
            if 'effective_from' not in columns:
                db.execute('ALTER TABLE benefit_rule ADD COLUMN effective_from TEXT NOT NULL DEFAULT \'0001-01-01\'')
            if 'effective_to' not in columns:
                db.execute('ALTER TABLE benefit_rule ADD COLUMN effective_to TEXT')
            db.execute('CREATE INDEX IF NOT EXISTS idx_benefit_rule_period ON benefit_rule(product_id, effective_from, effective_to)')


def find_rules_at(db: sqlite3.Connection, product_id: str, date: str):
    """Current period selection, effective_to exclusive (ISO YYYY-MM-DD)."""
    return db.execute('''
        SELECT * FROM benefit_rule
        WHERE product_id = ? AND effective_from <= ?
          AND (effective_to IS NULL OR ? < effective_to)
        ORDER BY rule_id
    ''', (product_id, date, date)).fetchall()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', required=True, type=Path)
    args = parser.parse_args()
    migrate(args.db)
    print(f'S1-3 columns prepared: {args.db}')


if __name__ == '__main__':
    main()
