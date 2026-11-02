
"""Validate A/B final statistical inputs without inventing missing observations.

This module only validates the handoff contract; it does not generate users yet.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from math import isclose
from pathlib import Path

AGES = frozenset(('20s', '30s', '40s', '50s', '60plus'))
REQUIRED = {
    'age_district_weights.csv': ('age_band', 'district_code', 'weight'),
    'age_category_weights.csv': ('age_band', 'source_category_code', 'weight'),
    'category_crosswalk.csv': ('source_category_code', 'engine_category', 'mapping_status'),
    'category_ticket_means.csv': ('source_category_code', 'mean_ticket_won'),
    'spend_band_weights.csv': ('metric', 'band_code', 'weight', 'respondent_scope'),
    'dongbaek_usage_weights.csv': ('metric', 'band_code', 'weight', 'respondent_scope'),
    'card_ownership_weights.csv': ('combination_code', 'weight'),
}
OPTIONAL = ('day_weights.csv', 'time_weights.csv', 'card_behavior_weights.csv', 'ticket_calibration.csv')


@dataclass(frozen=True)
class Handoff:
    tables: dict[str, list[dict[str, str]]]
    warnings: tuple[str, ...]


def _read_csv(path: Path, required_columns: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        missing = set(required_columns) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f'{path.name}: missing columns {sorted(missing)}')
        return list(reader)


def _weights(rows, keys, table_name, *, require_sum=True):
    totals = {}
    for i, row in enumerate(rows, 2):
        if row.get('weight', '').strip() == '':
            raise ValueError(f'{table_name}:{i}: missing weight')
        try:
            value = float(row['weight'])
        except ValueError as e:
            raise ValueError(f'{table_name}:{i}: invalid weight') from e
        if not 0 <= value <= 1:
            raise ValueError(f'{table_name}:{i}: weight outside [0,1]')
        key = tuple(row.get(k, '') for k in keys)
        totals[key] = totals.get(key, 0.0) + value
    if require_sum:
        for group, total in totals.items():
            if not isclose(total, 1.0, abs_tol=0.005):
                raise ValueError(f'{table_name}: weights for {group} sum to {total:.6f}, expected 1')


def load_handoff(final_dir: str | Path) -> Handoff:
    """Load and validate A/B's final CSVs. Fail on missing required inputs.

    Period mixing and provenance are documented as warnings, not silently corrected.
    """
    final_dir = Path(final_dir)
    tables = {}
    for filename, columns in REQUIRED.items():
        path = final_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f'M1 handoff missing: {path}')
        tables[filename] = _read_csv(path, columns)
        if not tables[filename]:
            raise ValueError(f'{filename}: empty file')
    for filename in OPTIONAL:
        if (final_dir / filename).is_file():
            tables[filename] = _read_csv(final_dir / filename, ())

    age_district = tables['age_district_weights.csv']
    age_category = tables['age_category_weights.csv']
    for name, rows in [('age_district_weights.csv', age_district), ('age_category_weights.csv', age_category)]:
        unexpected = {r['age_band'] for r in rows} - AGES
        if unexpected:
            raise ValueError(f'{name}: invalid age_band: {sorted(unexpected)}')

    _weights(age_district, (), 'age_district_weights.csv')
    _weights(age_category, ('age_band',), 'age_category_weights.csv')
    _weights(tables['card_ownership_weights.csv'], (), 'card_ownership_weights.csv')
    _weights(tables['spend_band_weights.csv'], ('metric', 'respondent_scope'), 'spend_band_weights.csv')
    _weights(tables['dongbaek_usage_weights.csv'], ('metric', 'respondent_scope'), 'dongbaek_usage_weights.csv')

    crosswalk = {r['source_category_code']: r for r in tables['category_crosswalk.csv']}
    warnings = []
    for row in age_category:
        category = row['source_category_code']
        mapped = crosswalk.get(category)
        if mapped is None:
            raise ValueError(f'no crosswalk for source category: {category}')
        if not mapped['engine_category'].strip():
            raise ValueError(f'empty engine_category for: {category}')
        if mapped['mapping_status'].upper() not in ('CONFIRMED', 'VERIFIED', 'EXACT'):
            warnings.append(f'{category}: mapping requires review ({mapped["mapping_status"]})')

    ticket_categories = {r['source_category_code'] for r in tables['category_ticket_means.csv']}
    missing_tickets = {r['source_category_code'] for r in age_category} - ticket_categories
    if missing_tickets:
        raise ValueError(f'no ticket mean for categories: {sorted(missing_tickets)}')
    for row in tables['category_ticket_means.csv']:
        if float(row['mean_ticket_won']) <= 0:
            raise ValueError(f'invalid mean_ticket_won for {row["source_category_code"]}')

    periods = {r.get('reference_period') for rows in tables.values() for r in rows if r.get('reference_period')}
    if len(periods) > 1:
        warnings.append(f'multiple observation periods: {sorted(periods)}; retain as source metadata')
    return Handoff(tables=tables, warnings=tuple(dict.fromkeys(warnings)))
