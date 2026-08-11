from database import db_conn, _add_col_if_missing

NEW_COLS = [
    ("caste",             "VARCHAR(100)"),
    ("sub_caste",         "VARCHAR(100)"),
    ("permanent_address", "TEXT"),
    ("current_address",   "TEXT"),
    ("aadhar_no",         "VARCHAR(20)"),
    ("source_file",       "VARCHAR(255)"),
]

METADATA_ROWS = [
    ('students', 'caste',             'VARCHAR(100)', 0, 0),
    ('students', 'sub_caste',         'VARCHAR(100)', 0, 0),
    ('students', 'permanent_address', 'TEXT',         0, 0),
    ('students', 'current_address',   'TEXT',         0, 0),
    ('students', 'aadhar_no',         'VARCHAR(20)',  0, 0),
]

try:
    with db_conn() as conn:
        cur = conn.cursor()
        for col, dtype in NEW_COLS:
            _add_col_if_missing(cur, "students", col, dtype)
        cur.executemany(
            "INSERT IGNORE INTO schema_metadata "
            "(table_name,column_name,data_type,is_primary_key,is_foreign_key) VALUES (%s,%s,%s,%s,%s)",
            METADATA_ROWS
        )
        conn.commit()
        cur.close()
    print("Done! New columns added to students table and schema_metadata.")
except Exception as e:
    print(f"Error: {e}")
