import mysql.connector
from config import settings
from database import students_col

def sync_students():
    conn = mysql.connector.connect(
        host=settings.MYSQL_HOST,
        port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD,
        database=settings.MYSQL_DB
    )
    cursor = conn.cursor(dictionary=True)

    count_inserted = 0
    count_updated = 0

    for s in students_col.find():
        usn = s.get("usn")
        name = s.get("name", "Unknown")
        current_sem = s.get("current_sem", 0)
        status = s.get("status", "ACTIVE")

        if not usn:
            import time
            usn = f"TEMP-{str(name).upper().replace(' ', '')}-{int(time.time() * 1000)}"

        cursor.execute("SELECT student_id FROM students WHERE usn = %s", (usn,))
        if cursor.fetchone():
            cursor.execute(
                "UPDATE students SET name=%s, current_sem=%s, status=%s WHERE usn=%s",
                (name, current_sem, status, usn)
            )
            count_updated += 1
        else:
            cursor.execute(
                "INSERT INTO students (usn, name, current_sem, status) VALUES (%s, %s, %s, %s)",
                (usn, name, current_sem, status)
            )
            count_inserted += 1
    
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Sync complete. Inserted {count_inserted}, Updated {count_updated}.")

if __name__ == "__main__":
    sync_students()
