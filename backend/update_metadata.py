from database import db_conn

queries = [
    ("INSERT IGNORE INTO schema_metadata (table_name, column_name, data_type, is_primary_key, is_foreign_key) VALUES (%s, %s, %s, %s, %s)",
     [
         ('students', 'father_name', 'VARCHAR(150)', 0, 0),
         ('students', 'mother_name', 'VARCHAR(150)', 0, 0),
         ('students', 'blood_group', 'VARCHAR(5)', 0, 0),
         ('students', 'address', 'TEXT', 0, 0),
         ('students', 'phone', 'VARCHAR(20)', 0, 0),
         ('students', 'email', 'VARCHAR(255)', 0, 0)
     ])
]

try:
    with db_conn() as conn:
        cur = conn.cursor()
        for q, params in queries:
            cur.executemany(q, params)
        conn.commit()
        print("Schema metadata successfully updated with personal details!")
except Exception as e:
    print(f"Failed to update metadata: {e}")
