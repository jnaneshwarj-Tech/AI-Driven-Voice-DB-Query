import mysql.connector
from config import settings
from database import students_col

import re
from datetime import datetime

def _parse_usn(usn: str) -> dict:
    match = re.match(r'^(\d)([A-Za-z]{2})(\d{2})([A-Za-z]{2})(\d{2,3})$', str(usn).strip())
    if not match:
        return {}
    
    course_duration = int(match.group(1))
    adm_yr_short = int(match.group(3))
    admission_year = 2000 + adm_yr_short
    roll_no = int(match.group(5))
    
    is_lateral = roll_no >= 400
    student_type = "Lateral Entry" if is_lateral else "Regular"
    
    now = datetime.now()
    curr_yr = now.year
    curr_mo = now.month
    
    years_diff = curr_yr - admission_year
    
    if curr_mo >= 7:  # July to Dec = ODD Sem
        calc_sem = years_diff * 2 + 1
    else:             # Jan to Jun = EVEN Sem
        calc_sem = years_diff * 2
        
    if is_lateral:
        calc_sem += 2
        
    calc_sem = max(1, calc_sem)
    
    if calc_sem > (course_duration * 2):
        status = "GRADUATED"
    else:
        status = "ACTIVE"
        
    current_year = (calc_sem + 1) // 2
    if current_year > course_duration:
        current_year = course_duration
        
    return {
        "admission_year": admission_year,
        "current_year": current_year,
        "student_type": student_type,
        "estimated_semester": calc_sem,
        "status": status,
        "current_sem": calc_sem
    }

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

        usn_data = _parse_usn(usn)
        ad_year = usn_data.get("admission_year")
        curr_year = usn_data.get("current_year")
        st_type = usn_data.get("student_type")
        est_sem = usn_data.get("estimated_semester")
        calc_status = usn_data.get("status", status)

        # Let's check schema. We might need to handle NULLs or format properly.
        # However, this script is a one-off mongo-to-mysql sync. We will just update it.
        try:
            cursor.execute("SELECT student_id FROM students WHERE usn = %s", (usn,))
            if cursor.fetchone():
                cursor.execute(
                    """UPDATE students SET name=%s, current_sem=%s, status=%s, 
                       admission_year=%s, current_year=%s, student_type=%s, estimated_semester=%s 
                       WHERE usn=%s""",
                    (name, current_sem, calc_status, ad_year, curr_year, st_type, est_sem, usn)
                )
                count_updated += 1
            else:
                cursor.execute(
                    """INSERT INTO students (usn, name, current_sem, status, 
                       admission_year, current_year, student_type, estimated_semester) 
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (usn, name, current_sem, calc_status, ad_year, curr_year, st_type, est_sem)
                )
                count_inserted += 1
        except Exception as e:
            print(f"Error syncing {usn}: {e}")
    
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Sync complete. Inserted {count_inserted}, Updated {count_updated}.")

if __name__ == "__main__":
    sync_students()
