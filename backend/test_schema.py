import os
from database import get_db_connection
from auto_schema_manager import map_file_columns, sync_database_schema

try:
    print("Testing map_file_columns")
    cols = ["Father Name", "CGPA %", "Extra column", "USN", "Name"]
    res = map_file_columns(cols)
    print("Mapped:", res)
    
    print("Testing sync_database_schema")
    sync_database_schema(res)
    print("Sync successful.")
except Exception as e:
    import traceback
    traceback.print_exc()
