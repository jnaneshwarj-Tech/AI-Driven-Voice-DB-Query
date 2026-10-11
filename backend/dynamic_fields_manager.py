import json

def register_dynamic_fields(cur, all_keys: list[str]) -> list[str]:
    """
    Checks if there are any new dynamic fields and registers them in the database.
    Returns a list of newly discovered canonical field names.
    """
    from routes_files import STUDENT_COLS
    
    new_fields = []
    
    # Identify fields that are NOT in static STUDENT_COLS and not standard structural fields
    for canonical in all_keys:
        if canonical in STUDENT_COLS or canonical in ('usn', 'sgpa', 'cgpa', 'semester'):
            continue
        if "sgpa" in canonical or "cgpa" in canonical or "semester" in canonical:
            continue
            
        cur.execute("SELECT id FROM field_registry WHERE canonical_name=%s", (canonical,))
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO field_registry (original_name, canonical_name, data_type) VALUES (%s, %s, %s)",
                (canonical.replace('_', ' ').title(), canonical, 'text')
            )
            new_fields.append(canonical)
            
    return new_fields

def get_all_dynamic_fields(cur) -> list[dict]:
    cur.execute("SELECT canonical_name, original_name, data_type FROM field_registry WHERE is_dynamic=1")
    return cur.fetchall()

def extract_dynamic_data(row: dict) -> dict:
    """Extracts non-standard keys from a parsed row into a dynamic data dictionary."""
    from routes_files import STUDENT_COLS
    
    dynamic_data = {}
    for k, v in row.items():
        if k in STUDENT_COLS or k in ('usn', 'sgpa', 'cgpa', 'semester'):
            continue
        if "sgpa" in k or "cgpa" in k or "semester" in k:
            continue
        
        if v is not None and str(v).strip() != '':
            dynamic_data[k] = str(v).strip()
            
    return dynamic_data
