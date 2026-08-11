"""
ai_column_mapper.py — Compatibility shim.

All real logic lives in canonical_fields.py (the single authoritative
canonical field + synonym registry). This module re-exports the public API
so existing imports continue to work.
"""
from canonical_fields import (
    normalize_header as normalize_col,
    map_column,
    map_columns,
    map_columns_detailed,
    apply_mapping,
    extract_wide_semester_rows,
    extract_marks_from_row,
    validate_mapped_rows,
    validate_sgpa_value,
    SYNONYM_REGISTRY as COLUMN_MAP,
    detect_file_format,
    parse_wide_sem_col,
)

__all__ = [
    "normalize_col",
    "map_column",
    "map_columns",
    "map_columns_detailed",
    "apply_mapping",
    "extract_wide_semester_rows",
    "extract_marks_from_row",
    "validate_mapped_rows",
    "validate_sgpa_value",
    "COLUMN_MAP",
    "detect_file_format",
    "parse_wide_sem_col",
]
