"""
address_parser.py — Village extraction and Rural/Urban classification.

Rules (strictly followed):
  - "(V)" or "(v)" pattern explicitly in the address → RURAL, extract village name
  - The pattern must be "(V)" as a parenthesized standalone indicator
  - "Vijayanagar", "Vivek Nagar" etc. do NOT match — bare 'v' in a word is ignored
  - Region extracted from text after the comma following "(V)"
  - Original address is NEVER modified
"""

import re


# Matches: "SomeName (V)" or "SomeName (v)" with word boundary
# Group 1: village name before "(V)"
# Group 2: optional region text after comma
_VILLAGE_PATTERN = re.compile(
    r'\b([A-Za-z][A-Za-z\s\-\'\.]{0,49}?)\s*\(\s*[Vv]\s*\)\s*(?:,\s*(.+))?',
    re.IGNORECASE,
)

# Explicit rural/urban keywords (standalone word match)
_RURAL_WORDS = re.compile(r'\b(rural)\b', re.IGNORECASE)
_URBAN_WORDS = re.compile(r'\b(urban)\b', re.IGNORECASE)


def parse_address_for_location(address: str) -> dict:
    """
    Parse an address string and extract structured location attributes.

    Returns a dict with keys (all may be None if not found):
        village   — name of the village before "(V)"
        area_type — "RURAL" if "(V)" detected or 'rural' keyword found,
                    "URBAN" if 'urban' keyword found, else None
        region    — district/area text after "(V), " separator

    CRITICAL: Does NOT modify the original address.
    Does NOT classify as rural merely because the letter "v" appears in a word.
    Patterns like "Vijayanagar", "Vivek Nagar" are NOT treated as villages.

    Examples:
        "Ajjampura (V), Chikkamagaluru"
          → {"village": "Ajjampura", "area_type": "RURAL", "region": "Chikkamagaluru"}

        "Ajjampura (v), Tarikere, Chikkamagaluru"
          → {"village": "Ajjampura", "area_type": "RURAL", "region": "Tarikere, Chikkamagaluru"}

        "Vijayanagar, Bangalore"
          → {"village": None, "area_type": None, "region": None}

        "Vivek Nagar"
          → {"village": None, "area_type": None, "region": None}

        "Rural area, Mysore"
          → {"village": None, "area_type": "RURAL", "region": None}

        "Urban locality, Bangalore"
          → {"village": None, "area_type": "URBAN", "region": None}
    """
    result = {"village": None, "area_type": None, "region": None}

    if not address or not isinstance(address, str):
        return result

    address_stripped = address.strip()

    # Try to find "(V)" pattern
    m = _VILLAGE_PATTERN.search(address_stripped)
    if m:
        raw_village = m.group(1).strip()
        raw_region = m.group(2)

        # Clean village name — remove trailing punctuation
        village = re.sub(r'[\s,;\.]+$', '', raw_village).strip()
        if village:
            result["village"] = village
        result["area_type"] = "RURAL"
        if raw_region:
            result["region"] = raw_region.strip()
        return result

    # No "(V)" pattern — check for explicit rural/urban keywords
    if _RURAL_WORDS.search(address_stripped):
        result["area_type"] = "RURAL"
    elif _URBAN_WORDS.search(address_stripped):
        result["area_type"] = "URBAN"

    return result


def normalize_area_type(value: str) -> str | None:
    """
    Normalize an explicit area_type column value.
    Accepts many common variants → 'RURAL' or 'URBAN'.
    Returns None for unrecognized values.
    """
    if not value:
        return None
    v = str(value).strip().lower()
    # Rural variants
    if v in ('rural', 'r', 'rur', 'village', 'gram', 'grameen', 'gramin',
             'rural area', 'rural areas', '1', 'yes-rural'):
        return 'RURAL'
    # Urban variants
    if v in ('urban', 'u', 'urb', 'city', 'town', 'municipal', 'corporation',
             'urban area', 'urban areas', '2', 'yes-urban'):
        return 'URBAN'
    return None


def enrich_row_from_address(row: dict) -> dict:
    """
    Given a mapped student row, try to enrich village/area_type/region
    fields from address columns if those enrichment fields are not already set.

    Checks: address, permanent_address, current_address (in order).
    Returns the row with new keys added (does not overwrite non-empty values).
    """
    from canonical_fields import _is_empty

    enriched = dict(row)

    # Skip if area_type is already provided
    has_area_type = not _is_empty(enriched.get('area_type'))
    has_village = not _is_empty(enriched.get('village'))

    if has_area_type and has_village:
        return enriched  # Already have what we need

    # Also normalize explicit area_type column if present
    if not has_area_type and not _is_empty(enriched.get('area_type')):
        normalized = normalize_area_type(str(enriched['area_type']))
        if normalized:
            enriched['area_type'] = normalized
            has_area_type = True

    # Try to extract from address fields
    for addr_field in ('address', 'permanent_address', 'current_address'):
        addr_val = enriched.get(addr_field)
        if _is_empty(addr_val):
            continue
        parsed = parse_address_for_location(str(addr_val))
        if parsed.get('village') and not has_village:
            enriched['village'] = parsed['village']
            has_village = True
        if parsed.get('area_type') and not has_area_type:
            enriched['area_type'] = parsed['area_type']
            has_area_type = True
        if parsed.get('region') and _is_empty(enriched.get('region')):
            enriched['region'] = parsed['region']
        if has_area_type and has_village:
            break

    # Normalize any explicit area_type that was just populated
    if not _is_empty(enriched.get('area_type')):
        enriched['area_type'] = normalize_area_type(str(enriched['area_type'])) or enriched['area_type']

    return enriched
