import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()
try:
    cursor.execute("DROP TABLE IF EXISTS uploaded_data")
    conn.commit()
    print("Successfully dropped uploaded_data table.")
except Exception as e:
    print(f"Error: {e}")
finally:
    cursor.close()
    conn.close()
