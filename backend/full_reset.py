import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()
try:
    cursor.execute("DROP TABLE IF EXISTS uploaded_data")
    cursor.execute("DROP TABLE IF EXISTS uploaded_files")
    conn.commit()
    print("Successfully dropped uploaded_data and uploaded_files tables for a 100% clean reset.")
except Exception as e:
    print(f"Error: {e}")
finally:
    cursor.close()
    conn.close()
