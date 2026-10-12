"""
rag_sql_generator.py
Natural language → MySQL SQL using NVIDIA LLM.
Rules: cumulative CGPA, default USN sort, NLP synonyms, schema memory.
Sprint 2: Kannada language support + complete student profile queries.
"""
from llm_service import llm_service
from database import db_conn
import re
from kannada_processor import normalize_query, build_language_context, is_complete_profile_intent


def _load_schema_context() -> str:
    try:
        from dynamic_fields_manager import get_all_dynamic_fields
        with db_conn() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT table_name, column_name, data_type "
                "FROM schema_metadata ORDER BY table_name, id"
            )
            rows = cur.fetchall()
            dynamic_fields = get_all_dynamic_fields(cur)
            cur.close()
            
        if not rows and not dynamic_fields:
            return _STATIC_SCHEMA
            
        tables: dict[str, list] = {}
        for r in rows:
            tables.setdefault(r["table_name"], []).append(
                f"   - {r['column_name']} ({r['data_type']})"
            )
        lines = ["Tables in student_db:\n"]
        for tbl, cols in tables.items():
            lines.append(f"{tbl}:")
            lines.extend(cols)
            lines.append("")
            
        if dynamic_fields:
            lines.append("\nDYNAMIC FIELDS (Stored in s.dynamic_data JSON column):")
            lines.append("CRITICAL RULE: To query these fields, you MUST use JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.canonical_name')) or s.dynamic_data->>'$.canonical_name'")
            for df in dynamic_fields:
                lines.append(f"   - {df['canonical_name']} (Original: '{df['original_name']}', Type: {df['data_type']})")
            lines.append("")
            
        lines.append("RULE: CGPA = cumulative AVG(sgpa) per semester using window function.")
        lines.append("RULE: Default sort = ORDER BY s.usn ASC unless user specifies otherwise.")
        return "\n".join(lines)
    except Exception as e:
        print(f"Error loading schema context: {e}")
        return _STATIC_SCHEMA


_STATIC_SCHEMA = """
Tables in student_db:

students:
   - usn (VARCHAR(100)) PRIMARY KEY
   - name (VARCHAR(150))
   - dob (DATE)
   - year_of_joining (INT)
   - current_sem (INT)
   - status (VARCHAR(20))
   - admission_year (INT) - Actual admission batch (corrected for lateral entry)
   - current_year (INT) - Current academic year (1-4)
   - student_type (VARCHAR(50)) - "Regular" or "Lateral Entry"
   - estimated_semester (INT) - Current semester calculated from USN
   - father_name (VARCHAR(150))
   - mother_name (VARCHAR(150))
   - father_occupation (VARCHAR(100)) - Father's job/profession
   - mother_occupation (VARCHAR(100)) - Mother's job/profession
   - blood_group (VARCHAR(10))
   - gender (VARCHAR(10))
   - religion (VARCHAR(50))
   - caste (VARCHAR(100))
   - sub_caste (VARCHAR(100))
   - category (VARCHAR(20))
   - address (TEXT) - full residential address
   - permanent_address (TEXT)
   - current_address (TEXT)
   - village (VARCHAR(100)) - village name extracted from address e.g. "Ajjampura"
   - area (VARCHAR(100)) - locality/area name
   - area_type (VARCHAR(20)) - RURAL or URBAN classification (values: 'RURAL', 'URBAN')
   - region (VARCHAR(100)) - geographic district/region text e.g. "Chikkamagaluru"
   - taluk (VARCHAR(100))
   - district (VARCHAR(100))
   - state (VARCHAR(100))
   - pin_code (VARCHAR(10)) - Postal PIN code
   - post_office (VARCHAR(100)) - Nearest post office name
   - phone (VARCHAR(20))
   - parents_phone (VARCHAR(20)) - Parent/guardian contact number
   - emergency_contact_number (VARCHAR(20))
   - email (VARCHAR(255))
   - aadhar_no (VARCHAR(20))
   - year_and_branch (VARCHAR(100))
   - branch (VARCHAR(50))
   - division (VARCHAR(50))
   - domain (VARCHAR(100))
   - hk_status (VARCHAR(20)) - Hyderabad-Karnataka region status: 'HK' or 'Non-HK'
   - quota (VARCHAR(100)) - Admission quota/reservation details e.g. 'Sports', 'Management'
   - distance_from_college (VARCHAR(50)) - Distance from home to college in km
   - kannada_medium (VARCHAR(10)) - Whether student studied in Kannada medium: 'Yes' or 'Not'
   - physically_handicapped (VARCHAR(10)) - Physical disability status: 'Yes' or 'No'
   - backlogs (TEXT) - Backlog/arrear subject details
   - snq_quota (VARCHAR(10)) - SNQ quota status

marks:
   - id (INT) PRIMARY KEY
   - usn (VARCHAR(100)) FK → students.usn
   - semester (INT)
   - sgpa (DECIMAL(4,2))
   - year (INT)

student_fees:
   - id (INT) PRIMARY KEY
   - usn (VARCHAR(100)) FK → students.usn
   - fee_type (VARCHAR(50)) - 'VTU', 'PD', 'IDP', 'TUITION_PAID', 'TUITION_REMAINING'
   - year (INT) - Academic year 1, 2, or 3
   - status (VARCHAR(30)) - 'Paid', 'Not Paid', 'Partially Paid'
   - amount_paid (VARCHAR(100))
   - remaining_amount (VARCHAR(100))

student_backlogs:
   - id (INT) PRIMARY KEY
   - usn (VARCHAR(100)) FK → students.usn
   - subject (VARCHAR(200)) - Subject with backlog
   - semester (INT) - Semester the backlog is in
   - year (VARCHAR(20)) - Academic year
   - cleared (TINYINT) - 0=pending, 1=cleared

RULE: CGPA = cumulative AVG(sgpa) per semester using window function.
RULE: Default sort = ORDER BY s.usn ASC unless user specifies otherwise.
RULE: Graduation Year = admission_year + 4
RULE: Graduation Status = 'GRADUATED' if YEAR(CURDATE()) >= (admission_year + 4), else 'ACTIVE'
RULE: Never permanently store graduation_status - always calculate dynamically.
RULE: area_type stores RURAL or URBAN. Use s.area_type = 'RURAL' for rural students.
RULE: village stores the village name extracted from address (e.g. "Ajjampura").
RULE: hk_status stores 'HK' or 'Non-HK'. Use s.hk_status = 'HK' for HK region students.
RULE: Fees are stored in student_fees table. JOIN students s LEFT JOIN student_fees sf ON sf.usn = s.usn for fee queries.
RULE: Backlogs are stored in student_backlogs table. JOIN students s LEFT JOIN student_backlogs sb ON sb.usn = s.usn for backlog queries.
"""

_SYSTEM_PROMPT = """You are an expert MySQL query generator for a college student database.

{schema}

Role: {role}

═══════════════════════════════════════════════════════
NLP SYNONYM RULES (apply regardless of case):
  "show/give/display/list/get"  → SELECT
  "top/highest/best/first/rank" → ORDER BY ... DESC
  "lowest/last/worst/bottom"    → ORDER BY ... ASC
  "cgpa wise"                   → ORDER BY cgpa DESC
  "sgpa wise"                   → ORDER BY sgpa DESC
  "name order/alphabetical"     → ORDER BY s.name ASC
  "usn order"                   → ORDER BY s.usn ASC
  "year wise"                   → ORDER BY year_of_joining

FIELD SYNONYM RULES:
  "phone/mobile/contact/mobile number/contact number" → s.phone
  "parents phone/parent mobile/family phone/guardian contact" → s.parents_phone
  "emergency contact/emergency number/emergency phone" → s.emergency_contact_number
  "address/residential address"  → s.address
  "permanent address/home address" → s.permanent_address
  "current address/local address" → s.current_address
  "village/native village"       → s.village
  "area/locality"                → s.area
  "area type/rural urban/residence type" → s.area_type
  "region/district region"       → s.region
  "taluk/tehsil/mandal"          → s.taluk
  "district"                     → s.district
  "state/province"               → s.state
  "pin code/pincode/postal code/zip" → s.pin_code
  "post office/postal office/po" → s.post_office
  "father name/dad name"         → s.father_name
  "mother name/mom name"         → s.mother_name
  "father occupation/father job/father profession/dad job" → s.father_occupation
  "mother occupation/mother job/mother profession/mom job" → s.mother_occupation
  "dob/date of birth/birth date" → s.dob
  "blood group/blood type"       → s.blood_group
  "branch/department/stream"     → s.branch
  "section/division"             → s.division
  "current semester/sem"         → s.current_sem
  "cgpa/cumulative gpa"          → calculated from marks
  "aadhar/uid"                   → s.aadhar_no
  "email/mail"                   → s.email
  "hk/non-hk/hyd karnataka/hyderabad karnataka" → s.hk_status
  "quota/reservation/admission quota" → s.quota
  "distance/distance from home/distance from college" → s.distance_from_college
  "kannada medium/medium of instruction" → s.kannada_medium
  "physically handicapped/disabled/handicapped" → s.physically_handicapped
  "backlogs/arrears/pending subjects/failed subjects" → s.backlogs (also student_backlogs table)
  "fees/fee status/vtu fees/pd fees/idp fees/tuition fees" → student_fees table

HK RULES:
  "hk students/hyd karnataka students"  → WHERE s.hk_status = 'HK'
  "non-hk students"                      → WHERE s.hk_status = 'Non-HK'
  "how many hk students"                 → SELECT COUNT(*) AS total_hk_students FROM students s WHERE s.hk_status = 'HK'

BACKLOG RULES:
  "students with backlogs"        → JOIN student_backlogs sb ON sb.usn = s.usn WHERE sb.cleared = 0
  "students without backlogs"     → WHERE s.usn NOT IN (SELECT usn FROM student_backlogs WHERE cleared = 0)
  "how many backlogs"             → COUNT from student_backlogs
  "backlog in 3rd semester"       → WHERE sb.semester = 3

FEE RULES:
  "vtu fees/vtu fee status"       → JOIN student_fees sf ON sf.usn = s.usn WHERE sf.fee_type = 'VTU'
  "fees not paid/unpaid fees"     → WHERE sf.status LIKE '%Not Paid%'
  "fees paid"                     → WHERE sf.status LIKE '%Paid%'
  "how many paid fees"            → COUNT students with all fees paid

RURAL/URBAN RULES (MANDATORY):
  "rural students/rural"         → WHERE s.area_type = 'RURAL'
  "urban students/urban"         → WHERE s.area_type = 'URBAN'
  "how many rural students"      → SELECT COUNT(*) AS total_rural_students FROM students s WHERE s.area_type = 'RURAL'
  "how many urban students"      → SELECT COUNT(*) AS total_urban_students FROM students s WHERE s.area_type = 'URBAN'
  NEVER use address REGEXP for rural/urban — always use s.area_type column.
  NEVER use s.region for rural/urban — region stores geographic text like district names.

VILLAGE RULES:
  "village of <name>"  → SELECT s.village FROM students s WHERE s.name LIKE '%<name>%'
  "students from village X" → WHERE LOWER(s.village) LIKE '%x%'
  Village name is stored in s.village column (extracted from address during upload).

GRADUATION QUERY SYNONYMS:
  "graduated/graduates/alumni/passed out/completed degree/graduation list/who graduated"
    → WHERE YEAR(CURDATE()) >= (s.admission_year + 4)
  "active students/current students/enrolled/studying"
    → WHERE YEAR(CURDATE()) < (s.admission_year + 4)

DEFAULT SORT RULE (MANDATORY):
  If user does NOT specify sorting → always add: ORDER BY s.usn ASC

CGPA CALCULATION RULE (MANDATORY):
  CGPA = cumulative average of SGPA up to each semester.
  Use window function:
    ROUND(AVG(m.sgpa) OVER (PARTITION BY m.usn ORDER BY m.semester
          ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2) AS cgpa
  NEVER use a stored cgpa column.

QUERY STRUCTURE RULES:
  1. Output ONLY raw SQL — no markdown, no explanation, no code fences.
  2. Aliases: students AS s, marks AS m.
  3. JOIN CONDITIONAL: Only JOIN marks m ON m.usn = s.usn IF academic details
     (sgpa, cgpa, semester, marks) are requested. Personal-only queries use students table only.
  4. SPECIFIC FIELD RULE (CRITICAL): If user asks for ONE specific field, SELECT ONLY that
     field (plus usn and name for identification). Do NOT add unrelated fields.
     Examples:
       "show Manoj's phone"   → SELECT s.usn, s.name, s.phone FROM students s WHERE ...
       "show Manoj's address" → SELECT s.usn, s.name, s.address FROM students s WHERE ...
       "show Manoj's village" → SELECT s.usn, s.name, s.village FROM students s WHERE ...
       "show Manoj's CGPA"    → SELECT s.usn, s.name, ROUND(AVG(m.sgpa),2) AS cgpa FROM ...
       "what is Manoj's DOB"  → SELECT s.usn, s.name, s.dob FROM students s WHERE ...
  5. MULTI-FIELD RULE: If user asks for multiple specific fields, return exactly those fields.
     "show Manoj's name, USN and CGPA" → SELECT s.usn, s.name, ROUND(AVG(m.sgpa),2) AS cgpa ...
  6. COMPLETE PROFILE OR PERSONAL DETAILS: "full details", "complete information", "personal details", "all details"
     → SELECT s.* (which automatically includes s.dynamic_data) and academic fields. When personal details are asked, you MUST SELECT s.* to ensure all dynamic non-academic fields are returned.
  7. For graduation queries, include: s.student_type, s.admission_year, (s.admission_year + 4) AS graduation_year
  8. Admin: SELECT, INSERT, UPDATE, or one selected-student DELETE after explicit confirmation.
      Staff: SELECT, INSERT, UPDATE. Staff DELETE and all-table destructive operations are forbidden.
  9. Search by name: WHERE s.name LIKE '%<name>%'
  10. Search by USN:  WHERE s.usn = '<usn>'
  11. Query order: WHERE → GROUP BY → HAVING → ORDER BY → LIMIT
  12. Never mix semesters in top-N (always filter by semester first).
    13. DELETE must target one student with an exact USN filter; UPDATE must target one student.
    14. Never use DELETE for all students or use TRUNCATE, DROP, ALTER, CREATE, GRANT, REVOKE.
  15. LIST QUERIES (rural/urban/top N): Return only identification + requested fields.
      "show rural students" → SELECT s.usn, s.name, s.area_type, s.village, s.region FROM students s WHERE s.area_type = 'RURAL' ORDER BY s.usn ASC
      "show rural students with current semester" → SELECT s.usn, s.name, s.current_sem, s.area_type, s.village FROM students s WHERE s.area_type = 'RURAL' ORDER BY s.usn ASC
═══════════════════════════════════════════════════════

DYNAMIC FIELD RULES (CRITICAL — READ CAREFULLY):

Some student attributes are stored as JSON in s.dynamic_data column.
These include: hk_non_hk, distance_from_home_to_college, kannada_medium,
  physically_handicapped, parents_phone_number, post_office, pin_code,
  quota_reservation_details, expected_year_of_graduation, backlogs_if_any,
  father_occupation, mother_occupation, and any future columns added from new uploaded files.

To FILTER on these fields, use JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.field_name')):
  "HK students" / "HK zone students"  → WHERE JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.hk_non_hk')) = 'HK'
  "Non-HK students" / "non hk"        → WHERE JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.hk_non_hk')) != 'HK' AND JSON_EXTRACT(s.dynamic_data, '$.hk_non_hk') IS NOT NULL
  "not HK"                            → WHERE UPPER(JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.hk_non_hk'))) != 'HK'
  "distance > 50"                     → WHERE CAST(JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.distance_from_home_to_college')) AS UNSIGNED) > 50
  "students far from college"         → ORDER BY CAST(JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.distance_from_home_to_college')) AS UNSIGNED) DESC
  "kannada medium students"           → WHERE LOWER(JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.kannada_medium'))) = 'yes'
  "physically handicapped"            → WHERE LOWER(JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.physically_handicapped'))) = 'yes'
  "father occupation is farmer"       → WHERE LOWER(JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.father_occupation'))) LIKE '%farmer%'
  "mother occupation"                 → JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.mother_occupation'))
  "students with backlogs"            → WHERE JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.backlogs_if_any')) NOT IN ('No', 'None', '', 'no')
  "parents phone number"              → JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.parents_phone_number'))

NEVER mistake HK/Non-HK for a name — it is ALWAYS a zone classification stored in dynamic_data.
NEVER use s.name LIKE '%HK%' for HK queries.
For ANY query mentioning "hk", "non-hk", "hk zone", "non hk", always use JSON_EXTRACT on dynamic_data.

When listing dynamic field values:
  SELECT s.usn, s.name, JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.hk_non_hk')) AS hk_non_hk FROM students s ORDER BY s.usn ASC

═══════════════════════════════════════════════════════


Q: students with blood group B+
SQL: SELECT s.usn, s.name, s.blood_group FROM students s WHERE UPPER(TRIM(s.blood_group)) = 'B+' ORDER BY s.usn ASC;

Q: show blood group A+ students
SQL: SELECT s.usn, s.name, s.blood_group FROM students s WHERE UPPER(TRIM(s.blood_group)) = 'A+' ORDER BY s.usn ASC;

Q: how many students have O+ blood group
SQL: SELECT COUNT(*) AS total_students FROM students s WHERE UPPER(TRIM(s.blood_group)) = 'O+';

Q: students from cs branch 2023 batch
SQL: SELECT s.usn, s.name, s.branch, s.admission_year, s.current_sem FROM students s WHERE (UPPER(s.branch) = 'CS' OR s.usn LIKE '%CS%') AND (s.admission_year = 2023 OR s.year_of_joining = 2023) ORDER BY s.usn ASC;

Q: show CSE students 2022 batch
SQL: SELECT s.usn, s.name, s.branch, s.admission_year, s.current_sem FROM students s WHERE (UPPER(s.branch) = 'CSE' OR s.usn LIKE '%CS%') AND (s.admission_year = 2022 OR s.year_of_joining = 2022) ORDER BY s.usn ASC;

Q: show all students
SQL: SELECT s.usn, s.name, s.student_type, s.admission_year, s.current_year, CASE WHEN YEAR(CURDATE()) >= (s.admission_year + 4) THEN 'GRADUATED' ELSE 'ACTIVE' END AS graduation_status FROM students s ORDER BY s.usn ASC;

Q: show rural students
SQL: SELECT s.usn, s.name, s.area_type, s.village, s.region FROM students s WHERE s.area_type = 'RURAL' ORDER BY s.usn ASC;

Q: show urban students
SQL: SELECT s.usn, s.name, s.area_type, s.area, s.region FROM students s WHERE s.area_type = 'URBAN' ORDER BY s.usn ASC;

Q: show HK students
SQL: SELECT s.usn, s.name, JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.hk_non_hk')) AS hk_non_hk FROM students s WHERE JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.hk_non_hk')) = 'HK' ORDER BY s.usn ASC;

Q: show Non-HK students
SQL: SELECT s.usn, s.name, JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.hk_non_hk')) AS hk_non_hk FROM students s WHERE UPPER(JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.hk_non_hk'))) != 'HK' AND JSON_EXTRACT(s.dynamic_data, '$.hk_non_hk') IS NOT NULL ORDER BY s.usn ASC;

Q: how many HK students are there
SQL: SELECT COUNT(*) AS total_hk_students FROM students s WHERE JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.hk_non_hk')) = 'HK';

Q: show all Non HK students
SQL: SELECT s.usn, s.name, JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.hk_non_hk')) AS hk_non_hk FROM students s WHERE UPPER(JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.hk_non_hk'))) != 'HK' AND JSON_EXTRACT(s.dynamic_data, '$.hk_non_hk') IS NOT NULL ORDER BY s.usn ASC;

Q: show students with distance from home more than 100
SQL: SELECT s.usn, s.name, JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.distance_from_home_to_college')) AS distance FROM students s WHERE CAST(JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.distance_from_home_to_college')) AS UNSIGNED) > 100 ORDER BY s.usn ASC;

Q: what is the distance from native for 4HG25CS402
SQL: SELECT s.usn, s.name, JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.distance_from_home_to_college')) AS distance_from_home FROM students s WHERE UPPER(s.usn) = '4HG25CS402';

Q: show father occupation of all students
SQL: SELECT s.usn, s.name, JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.father_occupation')) AS father_occupation FROM students s WHERE JSON_EXTRACT(s.dynamic_data, '$.father_occupation') IS NOT NULL ORDER BY s.usn ASC;

Q: show mother occupation of Divya
SQL: SELECT s.usn, s.name, JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.mother_occupation')) AS mother_occupation FROM students s WHERE s.name LIKE '%Divya%';

Q: show students whose father is a farmer
SQL: SELECT s.usn, s.name, JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.father_occupation')) AS father_occupation FROM students s WHERE LOWER(JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.father_occupation'))) LIKE '%farmer%' ORDER BY s.usn ASC;

Q: show kannada medium students
SQL: SELECT s.usn, s.name, JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.kannada_medium')) AS kannada_medium FROM students s WHERE LOWER(JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.kannada_medium'))) = 'yes' ORDER BY s.usn ASC;

Q: show students with backlogs
SQL: SELECT s.usn, s.name, JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.backlogs_if_any')) AS backlogs FROM students s WHERE JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.backlogs_if_any')) NOT IN ('No', 'None', 'no', '') ORDER BY s.usn ASC;

Q: show parents phone number of Devidas
SQL: SELECT s.usn, s.name, JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.parents_phone_number')) AS parents_phone FROM students s WHERE s.name LIKE '%Devidas%';

Q: show physically handicapped students
SQL: SELECT s.usn, s.name, JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.physically_handicapped')) AS physically_handicapped FROM students s WHERE LOWER(JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.physically_handicapped'))) = 'yes' ORDER BY s.usn ASC;

Q: personal details of 4HG25CS402
SQL: SELECT s.* FROM students s WHERE UPPER(s.usn) = '4HG25CS402' ORDER BY s.usn ASC;

Q: show complete profile of Divya
SQL: SELECT s.*, m.semester, m.sgpa FROM students s LEFT JOIN marks m ON m.usn = s.usn WHERE s.name LIKE '%Divya%' ORDER BY m.semester ASC;


Q: how many rural students are there
SQL: SELECT COUNT(*) AS total_rural_students FROM students s WHERE s.area_type = 'RURAL';

Q: how many urban students are there
SQL: SELECT COUNT(*) AS total_urban_students FROM students s WHERE s.area_type = 'URBAN';

Q: show rural students with their current semester
SQL: SELECT s.usn, s.name, s.current_sem, s.area_type, s.village, s.region FROM students s WHERE s.area_type = 'RURAL' ORDER BY s.usn ASC;

Q: show rural CS students
SQL: SELECT s.usn, s.name, s.current_sem, s.area_type, s.village FROM students s WHERE s.area_type = 'RURAL' AND s.usn LIKE '%CS%' ORDER BY s.usn ASC;

Q: show rural students with CGPA above 8
SQL: SELECT s.usn, s.name, s.area_type, s.village, ROUND(AVG(m.sgpa),2) AS cgpa FROM students s JOIN marks m ON m.usn = s.usn WHERE s.area_type = 'RURAL' GROUP BY s.usn, s.name, s.area_type, s.village HAVING AVG(m.sgpa) >= 8.0 ORDER BY s.usn ASC;

Q: show top 10 rural students based on CGPA
SQL: SELECT s.usn, s.name, s.village, s.region, ROUND(AVG(m.sgpa),2) AS cgpa FROM students s JOIN marks m ON m.usn = s.usn WHERE s.area_type = 'RURAL' GROUP BY s.usn, s.name, s.village, s.region ORDER BY cgpa DESC LIMIT 10;

Q: show names villages and USNs of rural students
SQL: SELECT s.usn, s.name, s.village FROM students s WHERE s.area_type = 'RURAL' ORDER BY s.usn ASC;

Q: show Manoj's phone number
SQL: SELECT s.usn, s.name, s.phone FROM students s WHERE s.name LIKE '%Manoj%';

Q: show Manoj's address
SQL: SELECT s.usn, s.name, s.address FROM students s WHERE s.name LIKE '%Manoj%';

Q: show Manoj's village
SQL: SELECT s.usn, s.name, s.village FROM students s WHERE s.name LIKE '%Manoj%';

Q: show Manoj's current semester
SQL: SELECT s.usn, s.name, s.current_sem FROM students s WHERE s.name LIKE '%Manoj%';

Q: what is Manoj's CGPA
SQL: SELECT s.usn, s.name, ROUND(AVG(m.sgpa),2) AS cgpa FROM students s JOIN marks m ON m.usn = s.usn WHERE s.name LIKE '%Manoj%' GROUP BY s.usn, s.name;

Q: show Manoj's emergency contact
SQL: SELECT s.usn, s.name, s.emergency_contact_number FROM students s WHERE s.name LIKE '%Manoj%';

Q: show Manoj's name USN and CGPA
SQL: SELECT s.usn, s.name, ROUND(AVG(m.sgpa),2) AS cgpa FROM students s JOIN marks m ON m.usn = s.usn WHERE s.name LIKE '%Manoj%' GROUP BY s.usn, s.name;

Q: show complete information about Manoj
SQL: SELECT s.*, m.semester, m.sgpa, ROUND(AVG(m.sgpa) OVER (PARTITION BY m.usn ORDER BY m.semester ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),2) AS cgpa FROM students s LEFT JOIN marks m ON m.usn = s.usn WHERE s.name LIKE '%Manoj%' ORDER BY m.semester ASC;

Q: show everything about Manoj
SQL: SELECT s.*, m.semester, m.sgpa, ROUND(AVG(m.sgpa) OVER (PARTITION BY m.usn ORDER BY m.semester ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),2) AS cgpa FROM students s LEFT JOIN marks m ON m.usn = s.usn WHERE s.name LIKE '%Manoj%' ORDER BY m.semester ASC;

Q: show graduated students
SQL: SELECT s.usn, s.name, s.student_type, s.admission_year, (s.admission_year + 4) AS graduation_year FROM students s WHERE YEAR(CURDATE()) >= (s.admission_year + 4) ORDER BY s.usn ASC;

Q: show marks / gpa of all students
SQL: SELECT s.usn, s.name, m.semester, m.sgpa, ROUND(AVG(m.sgpa) OVER (PARTITION BY m.usn ORDER BY m.semester ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),2) AS cgpa FROM students s JOIN marks m ON m.usn = s.usn ORDER BY s.usn ASC, m.semester ASC;

Q: show details of Manoj
SQL: SELECT s.usn, s.name, s.father_name, s.mother_name, s.dob, s.blood_group, s.address, s.village, s.district, s.state FROM students s WHERE s.name LIKE '%Manoj%';

Q: top 10 students of 3rd semester
SQL: SELECT s.usn, s.name, m.semester, m.sgpa FROM students s JOIN marks m ON m.usn = s.usn WHERE m.semester = 3 ORDER BY m.sgpa DESC LIMIT 10;

Q: How many students have 8+ CGPA?
SQL: SELECT COUNT(*) AS total_students FROM (SELECT s.usn FROM students s JOIN marks m ON m.usn = s.usn GROUP BY s.usn HAVING AVG(m.sgpa) >= 8.0) AS sub;

Q: show personal details of all students
SQL: SELECT s.usn, s.name, s.father_name, s.mother_name, s.dob, s.gender, s.blood_group, s.religion, s.caste, s.sub_caste, s.category, s.address, s.permanent_address, s.current_address, s.phone, s.email, s.aadhar_no FROM students s ORDER BY s.name ASC;

Q: add student USN 4HG23CS099 name Ravi Kumar
SQL: INSERT INTO students (usn, name) VALUES ('4HG23CS099', 'Ravi Kumar');

Q: delete student USN 4HG23CS099
SQL: DELETE FROM students WHERE usn = '4HG23CS099';

Q: Give only girls names
SQL: SELECT s.name FROM students s WHERE UPPER(s.gender) = 'FEMALE' ORDER BY s.name ASC;

Q: show Manoj's father occupation
SQL: SELECT s.usn, s.name, s.father_occupation FROM students s WHERE s.name LIKE '%Manoj%';

Q: show Manoj's mother occupation
SQL: SELECT s.usn, s.name, s.mother_occupation FROM students s WHERE s.name LIKE '%Manoj%';

Q: show father and mother occupation of Manoj
SQL: SELECT s.usn, s.name, s.father_occupation, s.mother_occupation FROM students s WHERE s.name LIKE '%Manoj%';

Q: students whose father is a farmer
SQL: SELECT s.usn, s.name, s.father_occupation FROM students s WHERE LOWER(s.father_occupation) LIKE '%farmer%' ORDER BY s.usn ASC;

Q: how many students have farmer father
SQL: SELECT COUNT(*) AS total_students FROM students s WHERE LOWER(s.father_occupation) LIKE '%farmer%';

Q: show HK students
SQL: SELECT s.usn, s.name, s.hk_status, s.district FROM students s WHERE s.hk_status = 'HK' ORDER BY s.usn ASC;

Q: how many HK students are there
SQL: SELECT COUNT(*) AS total_hk_students FROM students s WHERE s.hk_status = 'HK';

Q: show non-HK students
SQL: SELECT s.usn, s.name, s.hk_status, s.district FROM students s WHERE s.hk_status = 'Non-HK' ORDER BY s.usn ASC;

Q: show students with backlogs
SQL: SELECT DISTINCT s.usn, s.name, s.branch, sb.subject, sb.semester FROM students s JOIN student_backlogs sb ON sb.usn = s.usn WHERE sb.cleared = 0 ORDER BY s.usn ASC;

Q: how many students have backlogs
SQL: SELECT COUNT(DISTINCT s.usn) AS students_with_backlogs FROM students s JOIN student_backlogs sb ON sb.usn = s.usn WHERE sb.cleared = 0;

Q: show students with backlogs in 3rd semester
SQL: SELECT DISTINCT s.usn, s.name, sb.subject FROM students s JOIN student_backlogs sb ON sb.usn = s.usn WHERE sb.semester = 3 AND sb.cleared = 0 ORDER BY s.usn ASC;

Q: show students without backlogs
SQL: SELECT s.usn, s.name FROM students s WHERE s.usn NOT IN (SELECT usn FROM student_backlogs WHERE cleared = 0) ORDER BY s.usn ASC;

Q: show Manoj backlogs
SQL: SELECT s.usn, s.name, sb.subject, sb.semester, sb.year FROM students s LEFT JOIN student_backlogs sb ON sb.usn = s.usn WHERE s.name LIKE '%Manoj%' ORDER BY sb.semester ASC;

Q: show fee status of Divya
SQL: SELECT s.usn, s.name, sf.fee_type, sf.year, sf.status, sf.amount_paid FROM students s LEFT JOIN student_fees sf ON sf.usn = s.usn WHERE s.name LIKE '%Divya%' ORDER BY sf.fee_type, sf.year;

Q: show students with unpaid VTU fees
SQL: SELECT s.usn, s.name, sf.fee_type, sf.year, sf.status FROM students s JOIN student_fees sf ON sf.usn = s.usn WHERE sf.fee_type = 'VTU' AND sf.status LIKE '%Not Paid%' ORDER BY s.usn ASC;

Q: show Manoj's distance from college
SQL: SELECT s.usn, s.name, s.distance_from_college FROM students s WHERE s.name LIKE '%Manoj%';

Q: show kannada medium students
SQL: SELECT s.usn, s.name, s.kannada_medium, s.branch FROM students s WHERE UPPER(TRIM(s.kannada_medium)) IN ('YES', 'Y') ORDER BY s.usn ASC;

Q: how many physically handicapped students
SQL: SELECT COUNT(*) AS total_ph_students FROM students s WHERE UPPER(TRIM(s.physically_handicapped)) IN ('YES', 'Y');

Q: show students from sports quota
SQL: SELECT s.usn, s.name, s.quota FROM students s WHERE LOWER(s.quota) LIKE '%sports%' ORDER BY s.usn ASC;

Q: show Divya's pin code
SQL: SELECT s.usn, s.name, s.pin_code, s.post_office FROM students s WHERE s.name LIKE '%Divya%';

USER QUERY: {query}


SQL:"""


def _strip_markdown(raw: str) -> str:
    for fence in ("```sql", "```"):
        if fence in raw:
            parts = raw.split(fence)
            if len(parts) > 1:
                return parts[1].split("```")[0].strip()
    return raw.strip()


ALLOWED_OPS = {"SELECT", "INSERT", "UPDATE", "DELETE"}


def _is_safe_dml(sql: str) -> bool:
    m = re.match(r'^\s*(\w+)', sql)
    return bool(m) and m.group(1).upper() in ALLOWED_OPS


def _fix_window_order(sql: str) -> str:
    """
    If SQL uses a window function alias (cgpa/sgpa) in ORDER BY,
    MySQL requires wrapping in a subquery.
    Detects pattern and wraps automatically.
    """
    sql_upper = sql.upper()
    # Check if it has a window function (OVER) AND orders by the alias
    has_window = 'OVER' in sql_upper and ('PARTITION BY' in sql_upper or 'ORDER BY' in sql_upper)
    if not has_window:
        return sql

    # Check if ORDER BY references a window alias (cgpa or sgpa at end)
    # Pattern: ORDER BY cgpa DESC or ORDER BY sgpa DESC at the outermost level
    order_match = re.search(
        r'\bORDER\s+BY\s+(cgpa|sgpa)\s*(DESC|ASC)?\s*(?:LIMIT\s+\d+\s*)?$',
        sql, re.IGNORECASE
    )
    if not order_match:
        return sql

    # Wrap in subquery so ORDER BY can reference the window alias
    order_col   = order_match.group(1)
    order_dir   = order_match.group(2) or 'DESC'
    # Extract LIMIT if present
    limit_match = re.search(r'\bLIMIT\s+(\d+)\s*$', sql, re.IGNORECASE)
    limit_clause = f" LIMIT {limit_match.group(1)}" if limit_match else ""

    # Strip the ORDER BY (and LIMIT) from the inner query
    inner = re.sub(
        r'\s+ORDER\s+BY\s+(cgpa|sgpa)\s*(DESC|ASC)?\s*(?:LIMIT\s+\d+\s*)?$',
        '', sql, flags=re.IGNORECASE
    ).strip().rstrip(';')

    wrapped = (
        f"SELECT * FROM ({inner}) AS sub "
        f"ORDER BY {order_col} {order_dir}{limit_clause};"
    )
    return wrapped


def classify_query_intent(query: str) -> dict:
    """Lightweight intent classifier for graduation and academic queries."""
    text = (query or "").strip()
    if not text:
        return {"intent": "unknown"}
    low = text.lower()

    year_match = re.search(r'\b(\d{4})\b', low)
    if year_match and re.search(r'\b(graduates?|graduation list|graduated)\b', low):
        return {"intent": "graduation_year", "year": int(year_match.group(1))}

    admission_match = re.search(r'\b(?:admitted\s+in|admission\s+batch|admission\s+year)\s+(\d{4})\b', low)
    if not admission_match:
        admission_match = re.search(r'\b(\d{4})\s+(?:admission\s+batch|admission\s+year|admitted\s+in)\b', low)
    if admission_match:
        return {"intent": "admission_batch", "batch": int(admission_match.group(1))}

    if re.search(r'\b(active|current|enrolled|studying)\b', low) and re.search(r'\bstudents?\b', low):
        return {"intent": "graduation_status", "status": "active"}

    if re.search(r'\b(graduated|graduates?|alumni|passed out|completed degree|graduation list|who graduated)\b', low):
        status = "graduated"
        if re.search(r'\b(active|current|enrolled|studying)\b', low):
            status = "active"
        result = {"intent": "graduation_status", "status": status}
        if re.search(r'\b(cs|computer science)\b', low):
            result["branch"] = "CS"
        return result

    if re.search(r'\blateral\s+entry\b', low):
        return {"intent": "student_type", "student_type": "Lateral Entry"}

    if re.search(r'\bcomputer\s+science\b|\bcs\b', low):
        return {"intent": "graduation_status", "branch": "CS"}

    return {"intent": "general"}


_RURAL_ADDRESS_PATTERN = r"(^|[^a-z0-9])(village|gram|panchayat|taluk|taluka|tehsil|mandal|rural)([^a-z0-9]|$)"
_URBAN_ADDRESS_PATTERN = r"(^|[^a-z0-9])(urban|city|town|municipal|municipality|corporation|ward|layout|nagar|colony)([^a-z0-9]|$)"


def _address_query(effective_query: str):
    """
    Generate SQL for rural/urban/location-based queries.
    CRITICAL: rural/urban queries MUST use s.area_type column, NOT address REGEXP.
    area_type stores 'RURAL' or 'URBAN' as set during the import pipeline.
    """
    eq = effective_query.strip().lower()

    is_rural = bool(re.search(r'\brural\b', eq))
    is_urban = bool(re.search(r'\burban\b', eq))
    count_query = bool(re.search(r'\b(?:how\s+many|count|number\s+of|estimated|estimate)\b', eq))
    with_semester = bool(re.search(r'\b(?:semester|sem|current\s+sem)\b', eq))
    with_cgpa = bool(re.search(r'\b(?:cgpa|gpa)\b', eq))
    location_match = re.search(
        r"\b(?:from|in|at|near)\s+([a-z][a-z .'-]*?)"
        r"(?=\s+(?:with|who|and|or|aged?|age|branch|semester|sem|cgpa|blood|father|"
        r"mother|students?|student|phone|gender)\b|[?.!,;]|$)",
        eq,
    )
    location = location_match.group(1).strip() if location_match else None
    if location:
        location = re.sub(r"\s+(?:district|taluk|taluka|village|city|town)$", "", location).strip()
        if location in {"rural area", "rural areas", "urban area", "urban areas",
                        "rural", "urban", "the", "a", "an"}:
            location = None

    if not is_rural and not is_urban and not location:
        return None

    conditions = []
    params: list = []

    if is_rural:
        conditions.append("s.area_type = 'RURAL'")
    elif is_urban:
        conditions.append("s.area_type = 'URBAN'")

    if location:
        conditions.append(
            "LOWER(CONCAT_WS(' ', COALESCE(s.address,''), COALESCE(s.village,''), "
            "COALESCE(s.district,''))) LIKE %s"
        )
        loc_val = f"%{location}%"
        params.append(loc_val)

    where = " AND ".join(conditions) if conditions else "1=1"

    if count_query:
        label = "total_rural_students" if is_rural else ("total_urban_students" if is_urban else "total_students")
        sql = f"SELECT COUNT(*) AS {label} FROM students s WHERE {where}"
        return sql, params

    if with_cgpa:
        cols = "s.usn, s.name, s.area_type, s.village, ROUND(AVG(m.sgpa),2) AS cgpa"
        sql = (
            f"SELECT {cols} FROM students s "
            f"JOIN marks m ON m.usn = s.usn "
            f"WHERE {where} "
            f"GROUP BY s.usn, s.name, s.area_type, s.village "
            f"ORDER BY s.usn ASC"
        )
        return sql, params

    if with_semester:
        cols = "s.usn, s.name, s.current_sem, s.area_type, s.village"
    else:
        cols = "s.usn, s.name, s.area_type, s.village"

    sql = f"SELECT {cols} FROM students s WHERE {where} ORDER BY s.usn ASC"
    return sql, params


def _student_lookup_query(effective_query: str):
    eq = effective_query.strip()
    lower_query = eq.lower()
    field_patterns = (
        ("father_name", r"(?:father(?:'s)?|dad(?:'s)?)\s+name"),
        ("mother_name", r"(?:mother(?:'s)?|mom(?:'s)?)\s+name"),
        ("phone", r"(?:phone(?:\s+number)?|mobile(?:\s+number)?)"),
        ("email", r"email(?:\s+address)?"),
        ("address", r"address"),
        ("blood_group", r"blood\s+group"),
        ("dob", r"(?:date\s+of\s+birth|dob|birth\s+date)"),
        ("age", r"age"),
    )
    field_match = None
    selected_field = None
    for column, pattern in field_patterns:
        match = re.search(r"(?:['’]s\s+|\s+)" + pattern + r"\b", lower_query)
        if match:
            field_match = match
            selected_field = column
            break

    usn_match = re.search(r"\b(?=[a-z0-9]*\d)[a-z0-9]{6,}\b", lower_query)
    target = eq[:field_match.start()] if field_match else eq
    if not field_match and not usn_match and not re.search(
        r"\b(?:find|search|show|get|display|look\s+up|details|information|profile)\b", lower_query
    ):
        return None

    target = re.sub(
        r"^\s*(?:(?:what\s+is|find|search(?:\s+for)?|show|get|display|look\s+up|give(?:\s+me)?)\s+)+",
        "",
        target,
        flags=re.I,
    )
    target = re.sub(
        r"^\s*(?:(?:all|complete|full|personal|academic|acadamic|acdemic|student)\s+)*(?:details|information|info|profile)\s+(?:of|for|about)\s+",
        "",
        target,
        flags=re.I,
    )
    target = re.sub(r"\s+(?:(?:personal|complete|full|academic|acadamic|acdemic)\s+)?(?:details|information|info|profile)\s*$", "", target, flags=re.I)
    target = re.sub(r"(?:['’]s|s')\s*$", "", target).strip(" \t\r\n?.!,;:")

    if usn_match:
        identity_sql = "UPPER(s.usn) = %s"
        identity_value = usn_match.group(0).upper()
    elif target:
        # A phrase that still talks about students in general, or asks for a
        # substring, is a filter over the batch rather than the name of one
        # person. Comparing s.name to the whole clause answered "show students
        # whose name contains Ra" with zero rows. A single "student" in the
        # phrase ("details of student Manoj Kumar") is still a person lookup.
        if re.search(r"\bstudents\b|\b(?:who|whose|that)\b", target, re.I) or re.search(
                r"\b(?:contains?|containing|includes?|including)\b", lower_query):
            return None
        identity_sql = "LOWER(TRIM(s.name)) = LOWER(%s)"
        identity_value = target
    else:
        return None

    # Academic details query -> join marks
    # Handle both "academic details" and "academicdetails" (no space) and typos like "acadamic"
    if re.search(r'\b(?:academic|acadamic|acdemic|marks?|gpa|cgpa|sgpa|score)\b|academicdetails?|acadamicdetails?', lower_query):
        return (
            f"SELECT s.usn, s.name, m.semester, m.sgpa, ROUND(AVG(m.sgpa) OVER (PARTITION BY m.usn ORDER BY m.semester ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2) AS cgpa "
            f"FROM students s JOIN marks m ON m.usn = s.usn "
            f"WHERE {identity_sql} ORDER BY m.semester ASC",
            [identity_value],
        )

    # Complete profile / full details -> left join marks
    if re.search(r'\b(?:complete|full\s+details|everything|entire\s+profile)\b', lower_query):
        return (
            f"SELECT s.*, m.semester, m.sgpa, ROUND(AVG(m.sgpa) OVER (PARTITION BY m.usn ORDER BY m.semester ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2) AS cgpa "
            f"FROM students s LEFT JOIN marks m ON m.usn = s.usn "
            f"WHERE {identity_sql} ORDER BY m.semester ASC",
            [identity_value],
        )

    if selected_field == "age":
        field_sql = "TIMESTAMPDIFF(YEAR, s.dob, CURDATE()) AS age"
    elif selected_field:
        field_sql = f"s.`{selected_field}`"
    else:
        field_sql = "s.*"
    columns = f"s.usn, s.name, {field_sql}" if selected_field else field_sql
    return (
        f"SELECT {columns} FROM students s WHERE {identity_sql} ORDER BY s.usn ASC",
        [identity_value],
    )


def _father_name_filter_query(effective_query: str):
    match = re.search(
        r"\b(?:father(?:['’]s)?|dad(?:['’]s)?)\s+name\b\s*(?:is|=|of)?\s*"
        r"([A-Za-z][A-Za-z .'-]*?)"
        r"(?=\s+(?:students?|from|in|with|and|or|list|show|who|aged?|age|branch|"
        r"semester|current)\b|[?.!,;]|$)",
        effective_query,
        re.I,
    )
    if not match:
        return None

    father_name = match.group(1).strip(" .'-")
    if not father_name:
        return None

    where = "LOWER(TRIM(s.father_name)) = LOWER(TRIM(%s))"
    father_name_pattern = father_name
    if re.search(r"\b(?:contains?|includes?|partial(?:ly)?)\b", effective_query, re.I):
        where = "LOWER(TRIM(s.father_name)) LIKE LOWER(%s)"
        father_name_pattern = f"%{father_name}%"

    if re.search(r"\b(?:how\s+many|count|number\s+of)\b", effective_query, re.I):
        return f"SELECT COUNT(*) AS total_students FROM students s WHERE {where}", [father_name_pattern]
    return (
        f"SELECT s.usn, s.name, s.father_name FROM students s WHERE {where} ORDER BY s.usn ASC",
        [father_name_pattern],
    )


_ORDINAL_WORD_MAP: dict[str, int] = {
    "first": 1, "1st": 1, "1": 1, "one": 1,
    "second": 2, "2nd": 2, "2": 2, "two": 2,
    "third": 3, "3rd": 3, "3": 3, "three": 3,
    "fourth": 4, "4th": 4, "4": 4, "four": 4,
    "fifth": 5, "5th": 5, "5": 5, "five": 5,
    "sixth": 6, "6th": 6, "6": 6, "six": 6,
    "seventh": 7, "7th": 7, "7": 7, "seven": 7,
    "eighth": 8, "8th": 8, "8": 8, "eight": 8,
    # Kannada mappings
    "ಒಂದನೇ": 1, "ಮೊದಲ": 1, "ಮೊದಲನೇ": 1, "ondane": 1, "modalane": 1, "modala": 1,
    "ಎರಡನೇ": 2, "eradane": 2,
    "ಮೂರನೇ": 3, "moorane": 3, "moorané": 3, "murane": 3,
    "ನಾಲ್ಕನೇ": 4, "nalkane": 4,
    "ಐದನೇ": 5, "aidane": 5,
    "ಆರನೇ": 6, "aarane": 6,
    "ಏಳನೇ": 7, "elane": 7, "yelane": 7,
    "ಎಂಟನೇ": 8, "entane": 8,
}

_SEM_WORDS_PAT = r'(?:semester|semesters|sem|sem\.|ಸೆಮಿಸ್ಟರ್|ಸೆಮ್)'


def _detect_target_semester(eq: str) -> int | None:
    """Extract the target semester number from a query string.

    Deterministic ordinal mapping (NEVER lets the LLM guess):
      first / 1st / 1  → 1
      second / 2nd / 2 → 2
      ...
      eighth / 8th / 8 → 8

    Supported patterns:
      "first semester", "second sem", "3rd semester", "sem 3", "semester 5",
      "sem-3", "semester-4", "current semester is 4", "students in 8th sem",
      "3rd sem CSE students", "how many 3rd sem students"
    """
    text = eq if isinstance(eq, str) else ""
    low = text.lower()

    # ── Pattern 1: "<ordinal_word> semester/sem" ──
    for word, num in _ORDINAL_WORD_MAP.items():
        if re.search(rf"(?:\b|(?<=[\s_-]))({re.escape(word)})[-\s]+{_SEM_WORDS_PAT}", low, re.UNICODE):
            return num

    # ── Pattern 2: "N(st|nd|rd|th|ನೇ) semester/sem" (with or without hyphen/space) ──
    m = re.search(
        rf"\b([1-8])(?:st|nd|rd|th|ನೇ)?[-\s]*{_SEM_WORDS_PAT}",
        low,
        re.UNICODE,
    )
    if m:
        return int(m.group(1))

    # ── Pattern 3: "semester/sem N" (with or without 'is' / 'number' / '-' / ':') ──
    m = re.search(
        rf"\b(?:current\s+)?{_SEM_WORDS_PAT}\s*[-_:=#\s]*(?:(?:is|number|no|#)\s*[-_:=#\s]*)?([1-8])\b",
        low,
        re.UNICODE,
    )
    if m:
        return int(m.group(1))

    # ── Pattern 4: "N semester/sem" (bare number before sem word) ──
    m = re.search(
        rf"\b([1-8])\s*[-_\s]\s*{_SEM_WORDS_PAT}",
        low,
        re.UNICODE,
    )
    if m:
        return int(m.group(1))

    # ── Pattern 5: N(st|nd|rd|th) in context of students/academic/branch
    # NOTE: avoid treating “3rd year” as semester — the presence of a year
    # keyword means this should stay in the academic-year path, not sem.
    if re.search(r"\b(?:year|yr|academic\s+year)\b", low) and not re.search(rf"{_SEM_WORDS_PAT}", low):
        return None
    m = re.search(r"\b([1-8])(?:st|nd|rd|th)\b", low)
    if m and re.search(r"\b(?:students?|student|branch|cse?|ece?|ise?|mech?|civil|eee?|gpa|cgpa|sgpa)\b", low):
        return int(m.group(1))

    # ── Pattern 6: "semester/sem <number-word>" (spelled number AFTER the word) ──
    # "students in semester three", "sem sixth" — staff spell the number out and
    # place it after the sem word, which Patterns 1-5 do not cover.
    _word_alt = "|".join(sorted((re.escape(w) for w in _ORDINAL_WORD_MAP), key=len, reverse=True))
    m = re.search(rf"\b{_SEM_WORDS_PAT}\s+(?:is|of|number|no|#|:|-)?\s*({_word_alt})\b", low, re.UNICODE)
    if m:
        return _ORDINAL_WORD_MAP.get(m.group(1))

    return None


_BRANCH_NORMALIZATION: dict[str, tuple[str, ...]] = {
    "CS":    ("CS", "CSE", "COMPUTER SCIENCE", "COMPUTER SCIENCE AND ENGINEERING"),
    "CSE":   ("CS", "CSE", "COMPUTER SCIENCE", "COMPUTER SCIENCE AND ENGINEERING"),
    "ISE":   ("IS", "ISE", "INFORMATION SCIENCE", "INFORMATION SCIENCE AND ENGINEERING"),
    "IS":    ("IS", "ISE", "INFORMATION SCIENCE", "INFORMATION SCIENCE AND ENGINEERING"),
    "IT":    ("IT", "INFORMATION TECHNOLOGY"),
    "ECE":   ("EC", "ECE", "ELECTRONICS", "ELECTRONICS AND COMMUNICATION ENGINEERING"),
    "EC":    ("EC", "ECE", "ELECTRONICS", "ELECTRONICS AND COMMUNICATION ENGINEERING"),
    "EEE":   ("EE", "EEE", "ELECTRICAL", "ELECTRICAL AND ELECTRONICS ENGINEERING"),
    "EE":    ("EE", "EEE", "ELECTRICAL", "ELECTRICAL AND ELECTRONICS ENGINEERING"),
    "ME":    ("ME", "MECH", "MECHANICAL", "MECHANICAL ENGINEERING"),
    "MECH":  ("ME", "MECH", "MECHANICAL", "MECHANICAL ENGINEERING"),
    "CIVIL": ("CV", "CIV", "CIVIL", "CIVIL ENGINEERING"),
    "CIV":   ("CV", "CIV", "CIVIL", "CIVIL ENGINEERING"),
    "CE":    ("CV", "CIV", "CIVIL", "CIVIL ENGINEERING"),
    "CV":    ("CV", "CIV", "CIVIL", "CIVIL ENGINEERING"),
    "AIML":  ("AIML", "AI ML", "ARTIFICIAL INTELLIGENCE AND MACHINE LEARNING"),
    "AI":    ("AI", "AIML", "ARTIFICIAL INTELLIGENCE"),
    "AIDS":  ("AIDS", "AI DS", "ARTIFICIAL INTELLIGENCE AND DATA SCIENCE"),
    "CSD":   ("CSD", "COMPUTER SCIENCE AND DESIGN"),
    "CSBS":  ("CSBS", "COMPUTER SCIENCE AND BUSINESS SYSTEMS"),
    "IOT":   ("IOT", "INTERNET OF THINGS"),
    "ROBOTICS": ("ROBOTICS",),
    "MBA":   ("MBA",),
    "MCA":   ("MCA",),
    "CHEMICAL": ("CH", "CHEMICAL", "CHEMICAL ENGINEERING"),
    "CH":    ("CH", "CHEMICAL", "CHEMICAL ENGINEERING"),
    "ARCH":  ("ARCH", "ARCHITECTURE"),
}


def _normalize_branch(raw: str) -> tuple[str, ...]:
    """Map a branch name/acronym to all equivalent forms.

    Returns tuple of canonical aliases (upper-case) for exact IN matching.
    Empty tuple means unknown.
    """
    key = (raw or "").strip().upper()
    if not key:
        return ()
    # Direct lookup
    if key in _BRANCH_NORMALIZATION:
        return _BRANCH_NORMALIZATION[key]
    # Alias-based reverse lookup
    for canon, aliases in _BRANCH_NORMALIZATION.items():
        if key in aliases or key == canon:
            return aliases
    return ()


def _extract_branches(eq: str) -> list[str]:
    """Extract all explicitly requested branches from a query.

    Deterministic — the LLM does NOT get to decide branch interpretation.
    Multi-word branch names are matched first to avoid ambiguity.
    """
    text = (eq or "").strip()
    low = text.lower()
    upper = text.upper()
    found: list[str] = []

    def _add(canon: str):
        if canon and canon not in found:
            found.append(canon)

    # ── Multi-word branch names (case-insensitive text match) ──
    if re.search(r"\bcomputer\s+science\s+and\s+engineering\b", low):
        _add("CS")
    elif re.search(r"\bcomputer\s+science\b", low):
        _add("CS")
    if re.search(r"\binformation\s+science\s+and\s+engineering\b", low):
        _add("IS")
    elif re.search(r"\binformation\s+science\b", low):
        _add("IS")
    if re.search(r"\binformation\s+technology\b", low):
        _add("IT")
    if re.search(r"\belectronics\s+(?:and\s+|&\s+)?communication\s+(?:engineering)?\b", low):
        _add("EC")
    elif re.search(r"\belectronics\b", low) and not re.search(r"\belectrical\b", low):
        _add("EC")
    if re.search(r"\belectrical\s+and\s+electronics\s+(?:engineering)?\b", low):
        _add("EEE")
    elif re.search(r"\belectrical(?:\s+engineering)?\b", low):
        _add("EEE")
    if re.search(r"\bmechanical(?:\s+engineering)?\b", low):
        _add("ME")
    if re.search(r"\bcivil(?:\s+engineering)?\b", low):
        _add("CV")
    if re.search(r"\bartificial\s+intelligence\s+and\s+machine\s+learning\b", low):
        _add("AIML")
    elif re.search(r"\bartificial\s+intelligence\b", low) and "AIML" not in found:
        _add("AI")
    if re.search(r"\bartificial\s+intelligence\s+and\s+data\s+science\b", low):
        _add("AIDS")
    if re.search(r"\bcomputer\s+science\s+and\s+design\b", low):
        _add("CSD")
    if re.search(r"\bcomputer\s+science\s+(?:and\s+)?business\s+systems\b", low):
        _add("CSBS")
    if re.search(r"\binternet\s+of\s+things\b", low):
        _add("IOT")
    if re.search(r"\brobotics\b", low):
        _add("ROBOTICS")
    if re.search(r"\bchemical(?:\s+engineering)?\b", low):
        _add("CH")
    if re.search(r"\barchitecture\b", low):
        _add("ARCH")
    if re.search(r"\bmba\b", low):
        _add("MBA")
    if re.search(r"\bmca\b", low):
        _add("MCA")

    # ── Explicit acronyms / short-forms (case-insensitive) ──
    acronym_pats = [
        (r"\bcse\b", "CS"),
        (r"\bise\b", "IS"),
        (r"\beit\b", "IT"),
        (r"\bece\b", "EC"),
        (r"\beee\b", "EEE"),
        (r"\bmech\b", "ME"),
        (r"\bciv\b", "CV"),
        (r"\baiml\b", "AIML"),
        (r"\baids\b", "AIDS"),
        (r"\bcsd\b", "CSD"),
        (r"\bcsbs\b", "CSBS"),
        (r"\biot\b", "IOT"),
    ]
    for pat, canon in acronym_pats:
        if re.search(pat, low) and canon not in found:
            _add(canon)

    # ── 2-letter codes — careful not to match English words like "is", "me", "in" ──
    # CS (unambiguous because "cs" is not a common English word in this context)
    if re.search(r"\bcs\b", low) and "CS" not in found:
        _add("CS")
    # EC
    if re.search(r"\bec\b", low) and "EC" not in found:
        _add("EC")
    # CV
    if re.search(r"\bcv\b", low) and "CV" not in found:
        _add("CV")
    # EE
    if re.search(r"\bee\b", low) and "EEE" not in found:
        _add("EEE")
    # "is" → IS branch: only when paired with explicit branch context
    if re.search(
        r"\bis\s+(?:branch|dept|department|stream)\b|"
        r"\b(?:branch|dept|department|stream)\s+is\b|"
        r"\bis\s+(?:students?|student|sem|semester)\b|"
        r"\b(?:sem|semester)\s+\d+\s+is\b",
        low,
    ) or re.search(r"\bIS\b", text):
        if "IS" not in found:
            _add("IS")
    # "me" → ME branch: only when paired with explicit branch context
    if re.search(
        r"\bme\s+(?:branch|dept|department|stream)\b|"
        r"\b(?:branch|dept|department|stream)\s+me\b|"
        r"\bme\s+(?:students?|student|sem|semester)\b|"
        r"\b(?:sem|semester)\s+\d+\s+me\b",
        low,
    ) or re.search(r"\bME\b", text):
        if "ME" not in found:
            _add("ME")

    return found


def _extract_blood_group(eq: str) -> str | None:
    """Extract explicit blood group A/B/AB/O with +/-, or None."""
    text = (eq or "").strip()
    low = text.lower()
    has_blood_ctx = bool(re.search(r"\bblood\b|ರಕ್ತ", low))
    if not has_blood_ctx and not re.search(r"\b(?:students?|with|and|in)\b", low):
        return None
    m = re.search(
        r"(?<![A-Z0-9])(AB|A|B|O)\s*(\+|-|plus|positive|pos|negative|neg|-)?(?![A-Z])",
        text,
        re.I,
    )
    if not m:
        return None
    group, sign = m.groups()
    sign = "+" if (sign or "").lower() in {"+", "plus", "positive", "pos"} else "-"
    return group.upper() + sign


def _extract_gpa_filter(eq: str, target_semester: int | None):
    """Return (metric, operator, value) or None.

    metric = 'sgpa_per_sem' if semester-scoped SGPA, else 'cgpa'.
    """
    text = (eq or "").strip().lower()
    has_sgpa = bool(re.search(r"\bsgpa\b", text))
    has_cgpa = bool(re.search(r"\bcgpa\b", text))
    has_gpa  = bool(re.search(r"\bgpa\b", text))
    if not (has_sgpa or has_cgpa or has_gpa):
        return None

    metric = "cgpa"
    if has_sgpa and target_semester is not None:
        metric = "sgpa_per_sem"
    elif has_sgpa:
        metric = "sgpa_aggregate"

    between = re.search(
        r"\b(?:cgpa|sgpa|gpa)\s+between\s+(\d+(?:\.\d+)?)\s+(?:and|to)\s+(\d+(?:\.\d+)?)",
        text,
    )
    if between:
        lo, hi = sorted((float(between.group(1)), float(between.group(2))))
        return (metric, "BETWEEN", (lo, hi))

    m = re.search(
        r"\b(?:cgpa|sgpa|gpa)\s*(?:is\s+)?(?:(not\s+)?(above|over|greater\s+than|below|under|less\s+than|"
        r"at\s+least|at\s+most|not\s+below|not\s+above|>=|<=|>|<|=))?\s*(\d+(?:\.\d+)?)",
        text,
    )
    if not m:
        return None
    neg, op_word, val = m.groups()
    op_word = (op_word or "=").lower()
    op = {
        "above": ">", "over": ">", "greater than": ">", ">": ">",
        "below": "<", "under": "<", "less than": "<", "<": "<",
        "at least": ">=", ">=": ">=", "at most": "<=", "<=": "<=",
        "not below": ">=", "not above": "<=", "=": "=",
    }.get(op_word, "=")
    if neg:
        op = ">=" if op == "<" else ("<=" if op == ">" else op)
    return (metric, op, float(val))


def _extract_top_limit(eq: str) -> int | None:
    """Extract TOP N limit from a query like 'top 10 ...' or 'first 5 ...'."""
    text = (eq or "").strip().lower()
    m = re.search(
        r"\b(?:top|first|highest|best|toppers?)\s+(\d{1,4})\b",
        text,
    )
    if m:
        n = int(m.group(1))
        return n if 1 <= n <= 10000 else None
    return None


def _build_comprehensive_student_query(eq: str, target_semester: int | None,
                                        branches: list[str]) -> tuple | None:
    """Build parameterised SQL for semester / branch / blood-group / GPA combinations.

    This is the authoritative rule-based handler for queries like:
      "list 3rd sem CSE students with O+ blood group"
      "top 10 3rd semester students by CGPA"
      "how many 4th sem ECE students with CGPA above 8"

    Every extracted condition is AND-ed together — nothing is dropped.
    COUNT queries use identical WHERE clauses to the list queries.
    """
    low = (eq or "").strip().lower()
    text = eq or ""

    is_count = bool(re.search(r"\b(?:how\s+many|count|number\s+of)\b", low))
    top_n = _extract_top_limit(eq)
    blood = _extract_blood_group(eq)
    gpa = _extract_gpa_filter(eq, target_semester)

    # Nothing to do if no filter was extracted at all
    if (target_semester is None and not branches and blood is None
            and gpa is None and top_n is None):
        return None
    # But if we have semester or branch — we want to handle this even without others

    if target_semester is None and not branches:
        # If we only have blood / GPA without sem/branch, let other handlers deal.
        return None

    where_parts: list[str] = []
    params: list = []
    selected: list[str] = ["s.usn", "s.name"]
    needs_marks_join = False

    def _is_negated(field_words):
        pattern = r"\b(?:not|don't|doesn't|aren't|without)\b.{0,30}\b(?:" + "|".join(field_words) + r")\b"
        return bool(re.search(pattern, low))

    # ── Semester (EXACT equality — authoritative on students.current_sem for
    #    "current students" intent, unless query explicitly asks for marks-table
    #    membership such as "students who have semester N marks"). ──
    if target_semester is not None:
        marks_historical = bool(re.search(
            r"\b(?:students?\s+)?who\s+(?:have|got|scored|taken|appeared\s+in)\b.*\bmarks?\b|"
            r"\bmarks?\s+(?:for|of|in)\b.*\bsem(?:ester)?\b",
            low,
        ))
        sem_neg = _is_negated([str(target_semester), "sem", "semester", "semesters"])
        if marks_historical:
            if sem_neg:
                where_parts.append(
                    "NOT EXISTS (SELECT 1 FROM marks m WHERE m.usn = s.usn AND m.semester = %s)"
                )
            else:
                where_parts.append(
                    "EXISTS (SELECT 1 FROM marks m WHERE m.usn = s.usn AND m.semester = %s)"
                )
            params.append(target_semester)
        else:
            if sem_neg:
                where_parts.append("(s.current_sem != %s OR s.current_sem IS NULL)")
            else:
                where_parts.append("s.current_sem = %s")
            params.append(target_semester)
        if "s.current_sem" not in selected and not marks_historical and not is_count:
            selected.append("s.current_sem")

    # ── Branch (EXACT — never return all branches when user requested one) ──
    if branches:
        or_parts = []
        for branch_key in branches:
            aliases = _normalize_branch(branch_key)
            if not aliases:
                aliases = (branch_key.upper(),)
            placeholders = ", ".join(["%s"] * len(aliases))
            exact = f"UPPER(COALESCE(s.branch, '')) IN ({placeholders})"
            params.extend(aliases)
            like_parts = []
            for alias in aliases:
                like_parts.append("UPPER(COALESCE(s.year_and_branch, '')) LIKE %s")
                params.append(f"%{alias}%")
            composite = "(" + " OR ".join(like_parts) + ")"
            or_parts.append(f"({exact} OR {composite})")
        branch_neg = _is_negated([re.escape(b.lower()) for b in branches] + ["branch", "dept", "department"])
        combined_branches = "(" + " OR ".join(or_parts) + ")"
        if branch_neg:
            where_parts.append(f"(NOT {combined_branches} OR s.branch IS NULL OR TRIM(s.branch) = '')")
        else:
            where_parts.append(combined_branches)
        if "s.branch" not in selected and not is_count:
            selected.append("s.branch")

    # ── Blood group ──
    if blood is not None:
        blood_neg = _is_negated([re.escape(blood.lower()), "blood", "group", "o\+", "o-", "a\+", "a-", "b\+", "b-", "ab\+", "ab-"])
        blood_expr = "REPLACE(REPLACE(REPLACE(UPPER(COALESCE(s.blood_group, '')), 'POSITIVE', '+'), 'NEGATIVE', '-'), ' ', '')"
        if blood_neg:
            where_parts.append(f"({blood_expr} <> %s OR NULLIF(TRIM(COALESCE(s.blood_group, '')), '') IS NULL)")
        else:
            where_parts.append(f"{blood_expr} = %s")
        params.append(blood)
        if "s.blood_group" not in selected and not is_count:
            selected.append("s.blood_group")

    # ── GPA filter ──
    order_by = _order_by_clause(text, target_semester)
    limit_clause = ""

    if gpa is not None:
        metric, op, val = gpa
        gpa_neg = _is_negated(["gpa", "cgpa", "sgpa", str(val)])
        # If user says "whose cgpa is not 8", op is '=' but gpa_neg is True, so we flip to '!=', plus IS NULL.
        # If op is '<', we don't flip unless they said "not less than 8", which is handled by gpa extractor (>=).
        if metric == "sgpa_per_sem" and target_semester is not None:
            sub = (
                "(SELECT m.sgpa FROM marks m WHERE m.usn=s.usn "
                "AND m.semester=%s AND m.sgpa IS NOT NULL LIMIT 1)"
            )
            params_for_expr = [target_semester]
            if gpa_neg and op == '=':
                where_parts.append(
                    f"(NOT EXISTS (SELECT 1 FROM marks m WHERE m.usn=s.usn AND m.semester=%s AND m.sgpa IS NOT NULL) OR {sub} != %s)"
                )
                params.extend([target_semester] + params_for_expr + [val])
            else:
                where_parts.append(
                    "EXISTS (SELECT 1 FROM marks m WHERE m.usn=s.usn "
                    "AND m.semester=%s AND m.sgpa IS NOT NULL)"
                )
                params.append(target_semester)
                if op == "BETWEEN":
                    where_parts.append(f"{sub} BETWEEN %s AND %s")
                    params.extend(params_for_expr + list(val))
                else:
                    where_parts.append(f"{sub} {op} %s")
                    params.extend(params_for_expr + [val])
            needs_marks_join = True
            if "ROUND(" + sub % (target_semester,) + ", 2) AS sgpa" not in " ".join(selected):
                sub_filled = (
                    "(SELECT m.sgpa FROM marks m WHERE m.usn=s.usn "
                    f"AND m.semester={target_semester} AND m.sgpa IS NOT NULL LIMIT 1)"
                )
                selected.append(f"ROUND({sub_filled}, 2) AS sgpa")
        elif metric == "sgpa_aggregate":
            sub = "(SELECT AVG(m.sgpa) FROM marks m WHERE m.usn=s.usn AND m.sgpa IS NOT NULL)"
            needs_marks_join = True
            if gpa_neg and op == '=':
                where_parts.append(f"(COALESCE({sub}, s.cgpa) != %s OR COALESCE({sub}, s.cgpa) IS NULL)")
                params.append(val)
            else:
                if op == "BETWEEN":
                    where_parts.append(f"COALESCE({sub}, s.cgpa) BETWEEN %s AND %s")
                    params.extend(list(val))
                else:
                    where_parts.append(f"COALESCE({sub}, s.cgpa) {op} %s")
                    params.append(val)
            selected.append(f"ROUND(COALESCE({sub}, s.cgpa), 2) AS cgpa")
        else:  # cgpa
            cgpa_expr = (
                "COALESCE((SELECT AVG(m.sgpa) FROM marks m WHERE m.usn=s.usn "
                "AND m.sgpa IS NOT NULL), s.cgpa)"
            )
            needs_marks_join = True
            if gpa_neg and op == '=':
                where_parts.append(f"({cgpa_expr} != %s OR {cgpa_expr} IS NULL)")
                params.append(val)
            else:
                if op == "BETWEEN":
                    where_parts.append(f"{cgpa_expr} BETWEEN %s AND %s")
                    params.extend(list(val))
                else:
                    where_parts.append(f"{cgpa_expr} {op} %s")
                    params.append(val)
            selected.append(f"ROUND({cgpa_expr}, 2) AS cgpa")

    # ── Ensure CGPA or SGPA is selected if mentioned or ordered by ──
    cgpa_expr_default = (
        "COALESCE((SELECT AVG(m.sgpa) FROM marks m WHERE m.usn=s.usn "
        "AND m.sgpa IS NOT NULL), s.cgpa)"
    )
    if (re.search(r"\b(?:cgpa|gpa)\b", low) or "cgpa" in order_by.lower()) and not is_count:
        if not any("AS cgpa" in col for col in selected):
            selected.append(f"ROUND({cgpa_expr_default}, 2) AS cgpa")

    if re.search(r"\bsgpa\b", low) and target_semester is not None and not is_count:
        if not any("AS sgpa" in col for col in selected):
            sub_filled = (
                "(SELECT m.sgpa FROM marks m WHERE m.usn=s.usn "
                f"AND m.semester={target_semester} AND m.sgpa IS NOT NULL LIMIT 1)"
            )
            selected.append(f"ROUND({sub_filled}, 2) AS sgpa")

    # ── TOP / LIMIT ──
    if top_n is not None:
        limit_clause = f" LIMIT {int(top_n)}"

    where_joined = " AND ".join(where_parts) if where_parts else "1=1"

    # ── COUNT variant uses identical WHERE ──
    if is_count:
        sql = (
            f"SELECT COUNT(*) AS total_students FROM students s "
            f"WHERE {where_joined}"
        )
        return (sql, params)

    sql = (
        "SELECT " + ", ".join(selected)
        + " FROM students s WHERE " + where_joined
        + " " + order_by
        + limit_clause
    )
    return (sql, params)


def _validate_semester_branch_sql(sql: str, eq: str,
                                   params: list | tuple | None = None) -> tuple[bool, str]:
    """Post-validate a generated SQL against extracted semester / branch intent.

    Returns (is_valid, error_message).

    Rules:
      - If user said semester 3, the SQL must reference semester/current_sem = 3
        (NOT >= 3, NOT <= 8, NOT some other semester).
      - If user asked for CSE, SQL must include a CSE/CS branch restriction
        (never return all branches when one was explicitly requested).

    Accepts optional `params` (the bound parameter list for parameterized SQL,
    i.e. values substituted for %s placeholders) so the validator can confirm
    branch aliases even when they are bound via placeholders rather than
    embedded literally in the SQL string.
    """
    if not sql:
        return False, "Empty SQL"

    target_sem = _detect_target_semester(eq)
    branches = _extract_branches(eq)
    bound_vals: tuple[str, ...] = tuple(
        str(v).strip().upper() for v in (params or []) if v is not None
    )

    # ── Semester validation ──
    if target_sem is not None:
        sql_upper = sql.upper()
        marks_historical = bool(re.search(
            r"\b(?:students?\s+)?who\s+(?:have|got|scored|taken|appeared\s+in)\b.*\bmarks?\b|"
            r"\bmarks?\s+(?:for|of|in)\b.*\bsem(?:ester)?\b",
            eq.lower(),
        ))

        # 1. Forbid range operators (> >= < <=) on semester columns
        range_pat = re.compile(
            r"\b(?:(?:s|students|m|marks)\.)?(?:current_sem|semester)\s*(>=|<=|>|<)",
            re.IGNORECASE,
        )
        if range_pat.search(sql):
            return False, (
                f"Semester validation failed: SQL uses range operator "
                f"({range_pat.search(sql).group(1)}) for semester "
                f"{target_sem} (exact = required)."
            )

        # 2. Check for generic ">= 8" or other semester range hacks
        if re.search(r"\b(?:current_sem|semester)\s*>=\s*8\b", sql, re.I):
            return False, f"Semester validation failed: SQL contains >= 8 for semester {target_sem}."

        # 3. Forbid wrong semester numeric values appearing in = comparisons
        for other in range(1, 13):
            if other == target_sem:
                continue
            wrong_pat = re.compile(
                rf"\b(?:(?:s|students|m|marks)\.)?(?:current_sem|semester)\s*=\s*{other}\b",
                re.IGNORECASE,
            )
            if wrong_pat.search(sql):
                return False, (
                    f"Semester validation failed: SQL contains = {other} "
                    f"but user requested semester {target_sem}."
                )

        # 4. Check exact equality
        exact_sem_ok = False
        sem_equal_pat = re.compile(
            rf"\b(?:(?:s|students)\.)?current_sem\s*=\s*{target_sem}\b",
            re.IGNORECASE,
        )
        sem_param_pat = re.compile(
            r"\b(?:(?:s|students)\.)?current_sem\s*=\s*%s\b",
            re.IGNORECASE,
        )
        sem_marks_equal_pat = re.compile(
            rf"\b(?:(?:m|marks)\.)?semester\s*=\s*{target_sem}\b",
            re.IGNORECASE,
        )
        sem_marks_param_pat = re.compile(
            r"\b(?:(?:m|marks)\.)?semester\s*=\s*%s\b",
            re.IGNORECASE,
        )

        has_target_in_params = (
            target_sem in (params or [])
            or str(target_sem) in (params or [])
            or any(v == target_sem for v in (params or []))
        )

        if sem_equal_pat.search(sql):
            exact_sem_ok = True
        elif sem_param_pat.search(sql) and (not params or has_target_in_params):
            exact_sem_ok = True
        elif marks_historical and sem_marks_equal_pat.search(sql):
            exact_sem_ok = True
        elif marks_historical and sem_marks_param_pat.search(sql) and (not params or has_target_in_params):
            exact_sem_ok = True

        # If user asked for current students, but SQL filtered on marks table only
        if not marks_historical and not (sem_equal_pat.search(sql) or sem_param_pat.search(sql)):
            return False, f"Semester validation failed: query for current semester {target_sem} must filter on current_sem, not marks table."

        # Forbid OR conditions that combine current_sem with other semesters or marks table
        if not marks_historical:
            if re.search(r"current_sem\b[^;]*\bOR\b[^;]*\b(?:m\.|marks\.)?semester\b", sql, re.I) or \
               re.search(r"(?:m\.|marks\.)?semester\b[^;]*\bOR\b[^;]*\bcurrent_sem\b", sql, re.I):
                return False, "Semester validation failed: OR between current_sem and marks is forbidden for current student queries."
            if re.search(r"current_sem\s*=\s*(?:" + str(target_sem) + r"|%s)\s+OR\b|\bOR\s+(?:(?:s|students)\.)?current_sem\s*=", sql, re.I):
                return False, "Semester validation failed: OR conditions on current_sem are forbidden."

        if not exact_sem_ok:
            return False, (
                f"Semester validation failed: user requested semester "
                f"{target_sem}, but SQL does not contain exact = {target_sem}."
            )

    # ── Branch validation ──
    if branches:
        # Normalize each requested branch to its alias set (union)
        all_aliases: set[str] = set()
        for b in branches:
            aliases = _normalize_branch(b)
            if aliases:
                all_aliases.update(aliases)
            else:
                all_aliases.add(b.upper())

        sql_has_branch_restriction = False

        # Structural check: does the SQL predicate on any of the canonical
        # branch columns (branch / year_and_branch / usn) via IN, =, or LIKE?
        # The column reference may be wrapped in UPPER/COALESCE/TRIM/REPLACE etc.
        # so allow balanced function-call parentheses before the operator.
        branch_pred_pat = re.compile(
            r"(?:\b(?:s|students)\.)?(?:branch|year_and_branch|usn)"
            r"[^)]{0,120}"
            r"(?:\)\s*)*(?:IN\s*\(|=|LIKE)",
            re.IGNORECASE,
        )

        if not branch_pred_pat.search(sql):
            # No branch-column predicate at all — definitely invalid
            sql_has_branch_restriction = False
        else:
            # Predicate exists. Now confirm the actual branch value(s) match.
            #   a) Check literals embedded directly in the SQL text.
            #   b) Check bound parameter values (for parameterized queries like
            #      `IN (%s, %s)` or `LIKE %s`).
            for alias in all_aliases:
                alias_escaped = re.escape(alias)
                # literal IN(...), =, or LIKE against the column
                if re.search(
                    rf"(?:branch|year_and_branch|usn)[^)]*\b{alias_escaped}\b",
                    sql, re.IGNORECASE,
                ):
                    sql_has_branch_restriction = True
                    break
                if re.search(
                    rf"BRANCH\s*(?:IN|=)[^)]*\b{alias_escaped}\b",
                    sql, re.IGNORECASE,
                ):
                    sql_has_branch_restriction = True
                    break

            # If not found via SQL literals, try the bound parameter list.
            if not sql_has_branch_restriction and bound_vals:
                # A LIKE-param value is wrapped in "%ALIAS%"; an IN-param is
                # the bare alias. An exact-match param is exactly the alias.
                # So match: alias is in bound_vals, or "%alias%" is in bound_vals.
                for alias in all_aliases:
                    a = alias.upper()
                    for v in bound_vals:
                        v_clean = v.strip().strip("%").strip()
                        if v_clean == a:
                            sql_has_branch_restriction = True
                            break
                        # Also allow LIKE-param with surrounding %
                        if (f"%{a}%" == v) or (v == a) or (v.endswith(a) and v.startswith("%")):
                            sql_has_branch_restriction = True
                            break
                    if sql_has_branch_restriction:
                        break

            # Final safety: also require at least one %s placeholder in a
            # branch-predicate context when we matched via bound params, to
            # ensure a stray alias in an unrelated SELECT-alias didn't pass.
            if sql_has_branch_restriction and bound_vals and not any(
                re.search(
                    r"(?:\b(?:s|students)\.)?(?:branch|year_and_branch|usn)"
                    r"[^)]{0,120}(?:\)\s*)*(?:IN\s*\(\s*%s|=\s*%s|LIKE\s*%s)",
                    sql, re.I,
                )
                for _ in (0,)
            ):
                # If the branch predicate does not contain %s at all, we rely
                # on the literal check (already true above), so leave it.
                pass

        if not sql_has_branch_restriction:
            return False, (
                f"Branch validation failed: user requested branch(es) "
                f"{branches} but SQL does not contain any branch restriction."
            )

    return True, ""


def _order_by_clause(eq: str, target_semester: int | None = None) -> str:
    """Derive an ORDER BY clause from an explicit sort directive; default to USN ASC.
    Only whitelisted column expressions are used, so this stays injection-safe."""
    eq_lower = eq.lower() if isinstance(eq, str) else eq
    has_directive = bool(re.search(
        r"\b(?:sort|order|arrange)\w*\b|\balphabetical\b|\b(?:ascending|descending|asc|desc)\b|"
        r"\b(?:name|usn|cgpa|sgpa|year|age|dob|semester)\s*(?:order|wise)\b|"
        r"\b(sgpa|cgpa|gpa)\s+(wise|based|highest|lowest|toppers?|top|descending|ascending|sorted|order|sort|ranking|ranked|best|worst|maximum|minimum|max|min)\b",
        eq, re.I
    ))
    # Implicit sort: user says "sgpa wise" or "cgpa wise" or "top students by sgpa" etc.
    sgpa_mention = bool(re.search(r"\bsgpa\b", eq, re.I))
    cgpa_mention = bool(re.search(r"\bcgpa\b", eq, re.I))
    gpa_mention = sgpa_mention or cgpa_mention or bool(re.search(r"\bgpa\b", eq, re.I))
    if not has_directive:
        if gpa_mention:
            has_directive = True
    desc_word = bool(re.search(r"\b(?:desc|descending|reverse|highest|largest|greatest|top|decreasing|best|toppers?|maximum|max|greater)\b", eq, re.I))
    asc_word = bool(re.search(r"\b(?:asc|ascending|lowest|smallest|least|bottom|increasing|worst|minimum|min|lesser)\b", eq, re.I))
    direction = "DESC" if (desc_word and not asc_word) else "ASC"
    if sgpa_mention or cgpa_mention or re.search(r"\bgpa\b", eq, re.I):
        if sgpa_mention and target_semester is not None:
            # Per-semester SGPA ordering for semester-scoped queries
            expr = (f"(SELECT m.sgpa FROM marks m WHERE m.usn=s.usn "
                    f"AND m.semester={target_semester} AND m.sgpa IS NOT NULL LIMIT 1)")
        else:
            # CGPA or aggregate SGPA when no semester scope
            expr = ("COALESCE((SELECT AVG(m.sgpa) FROM marks m WHERE m.usn=s.usn "
                    "AND m.sgpa IS NOT NULL), s.cgpa)")
        # "top/highest CGPA/SGPA" defaults to DESC unless the user asked for ascending.
        direction = "ASC" if asc_word else "DESC"
        return f"ORDER BY {expr} {direction}, s.usn ASC"
    if re.search(r"\bname\b|alphabet", eq, re.I):
        return f"ORDER BY s.name {direction}, s.usn ASC"
    if re.search(r"\busn\b", eq, re.I):
        return f"ORDER BY s.usn {direction}"
    if re.search(r"\b(?:semester|sem)\b", eq, re.I):
        return f"ORDER BY s.current_sem {direction}, s.usn ASC"
    if re.search(r"\b(?:year|batch|joining)\b", eq, re.I):
        return f"ORDER BY s.year_of_joining {direction}, s.usn ASC"
    if re.search(r"\b(?:dob|age|born)\b", eq, re.I):
        return f"ORDER BY s.dob {direction}, s.usn ASC"
    return "ORDER BY s.usn ASC"


def _year_where_clause(yr: int) -> tuple[str, list]:
    """Generate a safe year filter combining admission_year, year_of_joining,
    and the 2-digit year embedded in the USN at character positions 3-4/4-5
    (e.g. 4HG23CS032 → chars 4-5 are '23' meaning 2023 batch)."""
    yr_short = str(yr)[-2:]
    where = (
        "(s.admission_year = %s OR s.year_of_joining = %s OR "
        "SUBSTRING(UPPER(REPLACE(REPLACE(REPLACE(s.usn,' ',''),'-',''),'.','')), 4, 2) = %s)"
    )
    return where, [yr, yr, yr_short]


def _rule_based_fallback_sql(effective_query: str) -> str | None:
    """Generate deterministic SQL for standard queries. Runs BEFORE LLM."""
    eq = effective_query.strip().lower()

    father_filter_query = _father_name_filter_query(effective_query)
    if father_filter_query:
        return father_filter_query

    # ── Detect semester / branch / blood / GPA context EARLY ─────────────────
    target_semester = _detect_target_semester(effective_query)
    branches = _extract_branches(effective_query)
    sgpa_mention = bool(re.search(r"\bsgpa\b", eq))
    cgpa_mention = bool(re.search(r"\bcgpa\b", eq))

    # ── COMPREHENSIVE multi-condition handler (sem / branch / blood / CGPA /
    #    TOP N) — supersedes individual cases below for pure sem/branch/gpa/blood
    #    queries. HOWEVER: if the query also mentions filters NOT supported by
    #    the comprehensive builder (rural/urban, age, father/mother, address,
    #    DOB, join year, gender, status, phone, emergency, etc.), we SKIP this
    #    handler and return None so the general combined builder in
    #    routes_query.build_deterministic_student_query can construct the full
    #    query with ALL filters AND-ed together — no condition is dropped.
    _COMPREHENSIVE_UNSUPPORTED = re.compile(
        r"\b(?:rural|urban|area_type|region|age|aged|years?\s+old|year[- ]old|"
        r"older|younger|ವರ್ಷದ|born|birth|dob|"
        r"january|february|march|april|may|june|july|august|september|october|november|december|"
        r"father|mother|parent|address|village|district|city|taluk|taluka|town|locality|"
        r"from\s+[a-z]{3,}|at\s+[a-z]{3,}|"
        r"phone|mobile|emergency\s+(?:contact|phone|number)|email|mail|"
        r"gender|male|female|"
        r"status|active|graduated|alumni|passed[\s\-]?out|inactive|currently|enrolled|studying|"
        r"joined|joining|admitted|admission|enrolled|enrolment|enrollment|batch|intake|"
        r"year\s+of\s+(?:joining|admission)|20\d{2}\s+(?:batch|year|students|student)|"
        r"without|no|missing|does\s+not\s+have|do\s+not\s+have|don't\s+have|has\s+no|"
        r"null|empty|blank|available|not\s+available|"
        r"section|division|category|class|cast(?:e)?|sub\s*caste|religion)\b",
        re.UNICODE | re.IGNORECASE,
    )
    if target_semester is not None or branches:
        if not _COMPREHENSIVE_UNSUPPORTED.search(effective_query):
            comprehensive = _build_comprehensive_student_query(
                effective_query, target_semester, branches
            )
            if comprehensive:
                return comprehensive

    # ── Semester + SGPA queries (BEFORE year-only, because "4th sem sgpa > 8"
    #    is a semester-scoped SGPA query, not just a general query) ────────────
    if target_semester is not None and sgpa_mention:
        count_q = bool(re.search(r"\b(?:how\s+many|count|number\s+of)\b", eq))
        order = _order_by_clause(effective_query, target_semester)
        sgpa_between = re.search(
            r"\bsgpa\s+between\s+(\d+(?:\.\d+)?)\s+(?:and|to)\s+(\d+(?:\.\d+)?)", eq
        )
        sgpa_val = None
        sgpa_op = None
        if not sgpa_between:
            m = re.search(
                r"\bsgpa\s*(?:is\s+)?(?:(not\s+)?(above|over|greater\s+than|below|under|less\s+than|"
                r"at\s+least|at\s+most|not\s+below|not\s+above|>=|<=|>|<|=))?\s*(\d+(?:\.\d+)?)", eq
            )
            if m:
                neg, op_word, val = m.groups()
                op_word = (op_word or "=").lower()
                op = {
                    "above": ">", "over": ">", "greater than": ">", ">": ">",
                    "below": "<", "under": "<", "less than": "<", "<": "<",
                    "at least": ">=", ">=": ">=", "at most": "<=", "<=": "<=",
                    "not below": ">=", "not above": "<=", "=": "=",
                }[op_word]
                if neg:
                    op = ">=" if op == "<" else ("<=" if op == ">" else op)
                sgpa_val = float(val)
                sgpa_op = op
        sgpa_select_expr = (
            f"(SELECT ROUND(m.sgpa, 2) FROM marks m WHERE m.usn=s.usn "
            f"AND m.semester={target_semester} AND m.sgpa IS NOT NULL LIMIT 1) AS sgpa"
        )
        where_parts = [
            "EXISTS (SELECT 1 FROM marks m WHERE m.usn=s.usn AND m.semester=%s AND m.sgpa IS NOT NULL)"
        ]
        params: list = [target_semester]
        if sgpa_between:
            low, high = sorted((float(sgpa_between.group(1)), float(sgpa_between.group(2))))
            where_parts.append(
                f"((SELECT m.sgpa FROM marks m WHERE m.usn=s.usn AND m.semester=%s AND m.sgpa IS NOT NULL LIMIT 1) BETWEEN %s AND %s)"
            )
            params.extend([target_semester, low, high])
        elif sgpa_val is not None and sgpa_op is not None:
            where_parts.append(
                f"((SELECT m.sgpa FROM marks m WHERE m.usn=s.usn AND m.semester=%s AND m.sgpa IS NOT NULL LIMIT 1) {sgpa_op} %s)"
            )
            params.extend([target_semester, sgpa_val])
        where_combined = " AND ".join(where_parts)
        if count_q:
            return (
                "SELECT COUNT(*) AS total_students FROM students s WHERE " + where_combined,
                params,
            )
        return (
            f"SELECT s.usn, s.name, s.current_sem, {sgpa_select_expr} "
            f"FROM students s WHERE {where_combined} {order}",
            params,
        )

    # ── Blood group queries ───────────────────────────────────────────────────
    blood_match = re.search(
        r'\bblood\s*(?:group|type)?\s*(?:is|=|:)?\s*([ABO]{1,2}[+-])',
        effective_query, re.I
    )
    if not blood_match:
        blood_match = re.search(r'\b([ABO]{1,2}[+-])\s*(?:blood|group|students?|blood\s*group)?\b', effective_query, re.I)
        if blood_match:
            after = effective_query[blood_match.end():].strip().lower()
            before = effective_query[:blood_match.start()].strip().lower()
            if not (re.search(r'\bblood|students?|group\b', after + ' ' + before)):
                blood_match = None
    if not blood_match:
        blood_match = re.search(r'\bblood\b.*?\b([ABO]{1,2}[+-])\b', effective_query, re.I)
    if blood_match:
        bg = blood_match.group(1).upper()
        count_query = bool(re.search(r'\b(?:how\s+many|count|number\s+of)\b', eq))
        if count_query:
            return (
                "SELECT COUNT(*) AS total_students FROM students s "
                "WHERE UPPER(TRIM(s.blood_group)) = %s",
                [bg]
            )
        return (
            "SELECT s.usn, s.name, s.blood_group FROM students s "
            "WHERE UPPER(TRIM(s.blood_group)) = %s ORDER BY s.usn ASC",
            [bg]
        )

    # ── "academicdetails" (no space) typo query ───────────────────────────────
    acad_nospace = re.search(
        r'^(.+?)\s+acadamic?details?\s*$',
        effective_query.strip(), re.I
    )
    if acad_nospace:
        name_part = acad_nospace.group(1).strip()
        name_part = re.sub(r'^\s*(?:show|give|display|get)\s+', '', name_part, flags=re.I).strip()
        if name_part and len(name_part) >= 2:
            return (
                f"SELECT s.usn, s.name, m.semester, m.sgpa, "
                f"ROUND(AVG(m.sgpa) OVER (PARTITION BY m.usn ORDER BY m.semester "
                f"ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2) AS cgpa "
                f"FROM students s JOIN marks m ON m.usn = s.usn "
                f"WHERE s.name LIKE %s ORDER BY m.semester ASC",
                [f"%{name_part}%"]
            )

    # ── HK / Non-HK queries ───────────────────────────────────────────────────
    if re.search(r'\bhk\b|\bhyd\.?\s*karnataka\b|\bhyderabad.karnataka\b', eq):
        is_nonhk = bool(re.search(r'\bnon.hk\b|\bnon\s+hk\b', eq))
        hk_val = 'Non-HK' if is_nonhk else 'HK'
        count_q = bool(re.search(r'\b(?:how\s+many|count)\b', eq))
        order = _order_by_clause(eq)
        if count_q:
            label = 'total_non_hk_students' if is_nonhk else 'total_hk_students'
            return (f"SELECT COUNT(*) AS {label} FROM students s WHERE s.hk_status = %s", [hk_val])
        return (
            f"SELECT s.usn, s.name, s.hk_status, s.district, s.current_sem "
            f"FROM students s WHERE s.hk_status = %s {order}",
            [hk_val]
        )

    # ── Backlog queries ────────────────────────────────────────────────────────
    if re.search(r'\bbacklogs?\b|\barrears?\b|\bpending\s+subjects?\b', eq):
        count_q = bool(re.search(r'\b(?:how\s+many|count)\b', eq))
        no_backlog = bool(re.search(r'\bno\s+backlog|\bwithout\s+backlog|\bzero\s+backlog', eq))
        sem_m = re.search(r'\b(\d+)(?:st|nd|rd|th)?\s*(?:sem(?:ester)?)\b', eq)
        sem_filter = f" AND sb.semester = {int(sem_m.group(1))}" if sem_m else ""

        if no_backlog:
            if count_q:
                return (
                    "SELECT COUNT(DISTINCT s.usn) AS students_without_backlogs "
                    "FROM students s WHERE s.usn NOT IN "
                    "(SELECT usn FROM student_backlogs WHERE cleared = 0)",
                    []
                )
            return (
                "SELECT s.usn, s.name, s.branch FROM students s WHERE s.usn NOT IN "
                f"(SELECT usn FROM student_backlogs WHERE cleared = 0) {_order_by_clause(eq)}",
                []
            )
        if count_q:
            return (
                f"SELECT COUNT(DISTINCT s.usn) AS students_with_backlogs "
                f"FROM students s JOIN student_backlogs sb ON sb.usn = s.usn "
                f"WHERE sb.cleared = 0{sem_filter}",
                []
            )
        return (
            f"SELECT DISTINCT s.usn, s.name, s.branch, sb.subject, sb.semester "
            f"FROM students s JOIN student_backlogs sb ON sb.usn = s.usn "
            f"WHERE sb.cleared = 0{sem_filter} ORDER BY s.usn ASC",
            []
        )

    # ── Father/Mother occupation queries ─────────────────────────────────────
    occ_match = re.search(
        r'\b(father|mother|dad|mom)\s*(?:\'?s\s+|\s+)?(?:occupation|job|profession|work)\b',
        effective_query, re.I
    )
    if occ_match:
        parent = occ_match.group(1).lower()
        occ_col = 'father_occupation' if parent in ('father', 'dad') else 'mother_occupation'
        # Optional: "students whose father is a farmer"
        occ_val_m = re.search(
            r'\b(?:is|was|are|=)\s+(?:a\s+|an\s+)?([a-zA-Z][a-zA-Z ]{2,30}?)(?:\s*$|[?.!,;])',
            effective_query, re.I
        )
        count_q = bool(re.search(r'\b(?:how\s+many|count)\b', eq))
        order = _order_by_clause(eq)
        if occ_val_m and not re.search(r'\bmanoj\b|\bstudent\b', occ_val_m.group(1), re.I):
            occ_val = occ_val_m.group(1).strip()
            if count_q:
                return (
                    f"SELECT COUNT(*) AS total_students FROM students s "
                    f"WHERE LOWER(s.`{occ_col}`) LIKE %s",
                    [f"%{occ_val.lower()}%"]
                )
            return (
                f"SELECT s.usn, s.name, s.`{occ_col}` FROM students s "
                f"WHERE LOWER(s.`{occ_col}`) LIKE %s {order}",
                [f"%{occ_val.lower()}%"]
            )
        # Generic: show all students with their occupation
        if not re.search(r'\b[A-Z][a-z]+ [A-Z]\b|\bmanoj\b', effective_query):
            if count_q:
                return (
                    f"SELECT COUNT(*) AS total_students FROM students s "
                    f"WHERE s.`{occ_col}` IS NOT NULL AND s.`{occ_col}` != ''",
                    []
                )
            return (
                f"SELECT s.usn, s.name, s.`{occ_col}` FROM students s "
                f"WHERE s.`{occ_col}` IS NOT NULL AND s.`{occ_col}` != '' {order}",
                []
            )

    # ── Kannada medium queries ─────────────────────────────────────────────────
    if re.search(r'\bkannada\s*medium\b', eq):
        count_q = bool(re.search(r'\b(?:how\s+many|count)\b', eq))
        if count_q:
            return ("SELECT COUNT(*) AS kannada_medium_students FROM students s WHERE UPPER(TRIM(s.kannada_medium)) IN ('YES', 'Y')", [])
        return ("SELECT s.usn, s.name, s.kannada_medium, s.branch, s.district FROM students s WHERE UPPER(TRIM(s.kannada_medium)) IN ('YES', 'Y') ORDER BY s.usn ASC", [])

    # ── Physically handicapped queries ─────────────────────────────────────────
    if re.search(r'\bphysically\s*handicapped\b|\bph\s+students\b|\bspecially\s*abled\b|\bdisabled\s+students\b', eq):
        count_q = bool(re.search(r'\b(?:how\s+many|count)\b', eq))
        if count_q:
            return ("SELECT COUNT(*) AS ph_students FROM students s WHERE UPPER(TRIM(s.physically_handicapped)) IN ('YES', 'Y')", [])
        return ("SELECT s.usn, s.name, s.physically_handicapped, s.branch FROM students s WHERE UPPER(TRIM(s.physically_handicapped)) IN ('YES', 'Y') ORDER BY s.usn ASC", [])

    # ── Year-only batch queries (no branch) — run BEFORE branch+year so
    #    "2023 students" doesn't accidentally get parsed as branch=STUDENTS etc.
    year_only_match = re.search(
        r'\b(20\d{2})\s*(?:batch|year|admitted|joining|passed|graduated|batch\s*of|admission|intake)\b',
        effective_query, re.I
    )
    if not year_only_match:
        year_only_match = re.search(
            r'\b(?:joined|admitted|enrolled|batch|admission)\s+(?:in|of|from|for)?\s*(20\d{2})\b',
            effective_query, re.I
        )
    if not year_only_match:
        year_only_match = re.search(
            r'\bwho\s+(?:joined|admitted|enrolled)\s+in\s+(20\d{2})\b',
            effective_query, re.I
        )
    if not year_only_match:
        year_only_match = re.search(
            r'\b(20\d{2})\s+(?:students|student|batch)\b|\b(?:students|student|batch)\s+(?:of|from|in)\s+(20\d{2})\b',
            effective_query, re.I
        )
    if not year_only_match:
        year_only_match = re.search(
            r'\bshow\s+(20\d{2})\s+(?:students|student|batch)\b',
            effective_query, re.I
        )
    if year_only_match:
        yr_str = year_only_match.group(1) or year_only_match.group(2)
        if yr_str:
            yr = int(yr_str)
            count_q = bool(re.search(r'\b(?:how\s+many|count|number\s+of)\b', eq))
            order = _order_by_clause(effective_query)
            where_year, yparams = _year_where_clause(yr)
            if count_q:
                return (
                    f"SELECT COUNT(*) AS total_students FROM students s WHERE {where_year}",
                    yparams
                )
            return (
                f"SELECT s.usn, s.name, s.admission_year, s.current_sem "
                f"FROM students s "
                f"WHERE {where_year} "
                f"{order}",
                yparams
            )

    # ── Branch + batch (year) queries ─────────────────────────────────────────
    branch_batch = re.search(
        r'\b([A-Za-z]{2,6})\s*(?:branch|dept|department|stream)?\s*'
        r'(?:students?)?\s*(?:admitted\s+in|batch\s*of|batch|year|joining|from|fron|in|of)?\s*'
        r'(20\d{2})\s*(?:batch|year|admitted|joining)?\b',
        effective_query, re.I
    )
    if not branch_batch:
        branch_batch = re.search(
            r'\b(20\d{2})\s*(?:batch|year|admitted|joining)?\s*'
            r'(?:students?)?\s*(?:admitted\s+in|batch\s*of|batch|year|joining|from|fron|in|of)?\s*'
            r'([A-Za-z]{2,6})\s*(?:branch|dept|department|stream)?\b',
            effective_query, re.I
        )
        if branch_batch:
            br_raw, yr_raw = branch_batch.group(2), branch_batch.group(1)
        else:
            br_raw, yr_raw = None, None
    else:
        br_raw, yr_raw = branch_batch.group(1), branch_batch.group(2)

    if br_raw and yr_raw:
        br = br_raw.upper()
        yr = int(yr_raw)
        _SKIP = {'THE', 'AND', 'FOR', 'ALL', 'ARE', 'FROM', 'FRON', 'WITH', 'SHOW',
                 'GIVE', 'GET', 'TOP', 'HOW', 'WHAT', 'WHO', 'LIST', 'FIND',
                 'ADMITTED', 'BATCH', 'YEAR', 'SHOW', 'STUDENTS', 'STUDENT',
                 'WHO', 'JOINED', 'INTO', 'JUST', 'NAME', 'CODE', 'USN', 'YEAR',
                 'MONTH', 'DAY', 'DATA', 'DATE', 'TIME'}
        if br not in _SKIP:
            count_q = bool(re.search(r'\b(?:how\s+many|count)\b', eq))
            order = _order_by_clause(effective_query)
            where_branch = "(UPPER(COALESCE(s.branch, '')) = %s OR UPPER(COALESCE(s.branch, '')) LIKE %s OR UPPER(COALESCE(s.year_and_branch, '')) LIKE %s)"
            where_year, yparams = _year_where_clause(yr)
            params = [br, f"%{br}%", f"%{br}%"] + yparams
            if count_q:
                return (
                    f"SELECT COUNT(*) AS total_students FROM students s "
                    f"WHERE {where_branch} AND {where_year}",
                    params
                )
            return (
                f"SELECT s.usn, s.name, s.branch, s.admission_year, s.current_sem "
                f"FROM students s "
                f"WHERE {where_branch} AND {where_year} "
                f"{order}",
                params
            )

    # ── Rural/urban/location queries ──────────────────────────────────────────
    address_query = _address_query(effective_query)
    if address_query:
        return address_query

    if re.search(r"\b(?:how\s+many|count|number\s+of)\b.*\bstudents?\b", eq):
        return "SELECT COUNT(*) AS total_students FROM students"

    if re.search(r'\b(show|list|display|get)?\s*all\s+students\b', eq):
        return ("SELECT s.usn, s.name, s.current_sem, s.email, s.phone, s.status "
                f"FROM students s {_order_by_clause(eq)}")

    # ── Specific single-field queries for a named student ────────────────────
    _SINGLE_FIELD_PATTERNS = [
        (r'\b(?:phone|mobile|contact)\s*(?:number|no)?\b', 'phone'),
        (r'\bparents?\s*(?:phone|mobile|contact)\b', 'parents_phone'),
        (r'\bemergency\s*(?:contact|number|phone)\b', 'emergency_contact_number'),
        (r'\bemail\b', 'email'),
        (r'\bpermanent\s+address\b', 'permanent_address'),
        (r'\bcurrent\s+address\b', 'current_address'),
        (r'\baddress\b', 'address'),
        (r'\bvillage\b', 'village'),
        (r'\barea\s*type\b', 'area_type'),
        (r'\barea\b', 'area'),
        (r'\bregion\b', 'region'),
        (r'\btaluk\b', 'taluk'),
        (r'\bdistrict\b', 'district'),
        (r'\bstate\b', 'state'),
        (r'\bpin\s*code\b|\bpincode\b|\bpostal\s*code\b', 'pin_code'),
        (r'\bpost\s*office\b', 'post_office'),
        (r'\bfather\s*(?:s\s+)?\s*name\b|\bdad\s*name\b', 'father_name'),
        (r'\bmother\s*(?:s\s+)?\s*name\b|\bmom\s*name\b', 'mother_name'),
        (r'\bfather\s*(?:s\s+)?\s*(?:occupation|job|profession|work)\b', 'father_occupation'),
        (r'\bmother\s*(?:s\s+)?\s*(?:occupation|job|profession|work)\b', 'mother_occupation'),
        (r'\bblood\s*group\b', 'blood_group'),
        (r'\b(?:dob|date\s*of\s*birth|birth\s*date)\b', 'dob'),
        (r'\bcurrent\s*sem(?:ester)?\b', 'current_sem'),
        (r'\b(?:which\s+)?branch\b|\bdepartment\b|\bdept\b', 'branch'),
        (r'\baadhar\b', 'aadhar_no'),
        (r'\bgender\b', 'gender'),
        (r'\breligion\b', 'religion'),
        (r'\bcaste\b', 'caste'),
        (r'\bhk\s*status\b|\bhk\s*non.hk\b', 'hk_status'),
        (r'\bquota\b|\breservation\b', 'quota'),
        (r'\bdistance\b', 'distance_from_college'),
        (r'\bkannada\s*medium\b', 'kannada_medium'),
        (r'\bphysically\s*handicapped\b|\bdisabled\b', 'physically_handicapped'),
        (r'\bbacklogs?\b|\barrears?\b', 'backlogs'),
    ]

    for field_pat, field_col in _SINGLE_FIELD_PATTERNS:
        if re.search(field_pat, effective_query, re.I):
            # Check for explicit USN in query
            usn_m = re.search(r'\b(?=[A-Za-z0-9]*\d)(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{6,20}\b', effective_query)
            if usn_m:
                col_sql = f"COALESCE(s.`{field_col}`, '') AS `{field_col}`" if field_col == 'branch' else f"s.`{field_col}`"
                return (
                    f"SELECT s.usn, s.name, {col_sql} FROM students s WHERE UPPER(s.usn) = %s ORDER BY s.usn ASC",
                    [usn_m.group(0).upper()]
                )

            # Extract student name by stripping field and query keywords
            cand = re.sub(
                r'\b(?:what\s+is\s+(?:the\s+)?|which\s+|show\s+(?:me\s+)?|give\s+(?:me\s+)?|get\s+|tell\s+me\s+(?:the\s+)?|display\s+|find\s+)?'
                + field_pat +
                r'(?:\s+(?:is|of|for|does|belong\s+to|details?))?\b',
                '',
                effective_query,
                flags=re.I
            )
            cand = re.sub(r"^\s*(?:what\s+is\s+(?:the\s+)?|which\s+|show\s+|give\s+|tell\s+me\s+|get\s+|find\s+|the\s+|student\s+)+", '', cand, flags=re.I)
            cand = cand.strip(" \t\r\n?.!,;:")
            cand = re.sub(r"(?:['’]s|s')\s*$", '', cand).strip(" \t\r\n?.!,;:")

            _STOP = {'show', 'give', 'display', 'get', 'what', 'is', 'the', 'a', 'an',
                     'of', 'for', 'student', 'students', 'me', 'all', 'list', 'find',
                     'blood', 'phone', 'mobile', 'email', 'address', 'father', 'mother', 'which', 'branch'}
            cand_words = [w for w in cand.lower().split() if w not in _STOP]
            if cand and cand_words and len(cand) >= 2:
                safe_name = cand
                col_sql = f"COALESCE(s.`{field_col}`, '') AS `{field_col}`" if field_col == 'branch' else f"s.`{field_col}`"
                # Check exact name match first
                return (
                    f"SELECT s.usn, s.name, {col_sql} FROM students s WHERE LOWER(TRIM(s.name)) = LOWER(%s) ORDER BY s.usn ASC",
                    [safe_name]
                )

    student_query = _student_lookup_query(effective_query)
    if student_query:
        return student_query

def _clean_llm_sql(sql: str, effective_query: str | None = None) -> str:
    """Post-process LLM-generated SQL to remove common anti-patterns:
    1. Remove overly-broad year-portion USN LIKE '%23%' filters that falsely match
       digits elsewhere in the USN (e.g. USN 4HG20CV235 has trailing 23 but is 2020 batch).
       Correct year-from-USN uses SUBSTRING(usn,4,2) instead.
    2. Rewrite CGPA-instead-of-SGPA patterns when the user explicitly asked for
       semester SGPA.
    3. Remove invalid ORDER BY clauses that reference non-selected window expressions.
    """
    if not sql:
        return sql

    cleaned = sql
    target_sem: int | None = None
    sem_sgpa_context = False

    # ── 1. Remove bad USN LIKE '%YY%' (two-digit) portion filters ────────────
    # Pattern: OR usn LIKE '%<2 digits>%' / AND usn LIKE '%<2 digits>%' with any alias
    cleaned = re.sub(
        r'\b(OR|AND)\s+(?:(?:s|students)\.)?`?usn`?\s+LIKE\s+[\'"][%_]?\s*\d{2}\s*[%_][\'"]',
        ' ', cleaned, flags=re.I
    )
    # Also strip USN LIKE patterns that use placeholder LIKE %s instead of literals
    # (e.g. the LLM produces "OR s.usn LIKE %s" to match a 2-digit year — removes it).
    cleaned = re.sub(
        r'\b(OR|AND)\s+(?:(?:s|students)\.)?`?usn`?\s+LIKE\s+%s\b',
        ' ', cleaned, flags=re.I
    )
    # Clean up accidental double-spaces / double ORs / double ANDs / empty parens
    cleaned = re.sub(r'\b(OR|AND)\s+(?:OR|AND)\b', r'\1', cleaned, flags=re.I)
    cleaned = re.sub(r'\(\s+(OR|AND)\b', '(', cleaned, flags=re.I)
    cleaned = re.sub(r'\b(OR|AND)\s+\)', ')', cleaned, flags=re.I)
    cleaned = re.sub(r'\(\s*\(', '(', cleaned)
    cleaned = re.sub(r'\)\s*\)', ')', cleaned)
    cleaned = re.sub(r'\(\s*\)', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    # ── 2. Per-semester SGPA: if query has semester + sgpa + numeric filter
    #    and generated SQL uses the CGPA aggregate, rewrite to per-sem sgpa ───
    if effective_query:
        target_sem = _detect_target_semester(effective_query)
        if target_sem is not None and re.search(r"\bsgpa\b", effective_query, re.I):
            sem_sgpa_context = True
            cgpa_aggregate_subq = (
                r"\(\s*SELECT\s+AVG\(\s*`?m`?\.`?sgpa`?\s*\)\s+FROM\s+`?marks`?\s+`?m`?\s+"
                r"WHERE\s+`?m`?\.`?usn`?\s*=\s*`?s`?\.`?usn`?\s+AND\s+`?m`?\.`?sgpa`?\s+IS\s+NOT\s+NULL\s*\)"
            )
            per_sem_expr = (
                f"(SELECT m.sgpa FROM marks m WHERE m.usn=s.usn AND m.semester={target_sem} "
                f"AND m.sgpa IS NOT NULL LIMIT 1)"
            )
            cleaned = re.sub(cgpa_aggregate_subq, per_sem_expr, cleaned, flags=re.I)
            # Also fix any generic "cgpa" alias to sgpa
            cleaned = re.sub(r'\bAS\s+`?cgpa`?\b', 'AS sgpa', cleaned, flags=re.I)

    # ── 3. Strip COALESCE wrapper around a per-sem sgpa if we just rewrote it ─
    # Fallback coalesce strip: COALESCE(per_sem_subquery, fallback) → per_sem_subquery
    if sem_sgpa_context and target_sem is not None:
        # Remove any leading COALESCE( and trailing , <fallback>) around a
        # semester-SGPA scalar subquery we just rewrote.
        cleaned = re.sub(
            r'COALESCE\s*\(\s*(\(\s*SELECT\s+m\.sgpa\s+FROM\s+marks\s+m\s+WHERE\s+m\.usn\s*=\s*s\.usn\s+AND\s+m\.semester\s*=\s*\d+\s+AND\s+m\.sgpa\s+IS\s+NOT\s+NULL\s+LIMIT\s+1\s*\)\s*),\s*[^)]+\)',
            r'\1', cleaned, flags=re.I
        )
        # Simpler fallback case: inner sgpa subquery followed by comma + fallback
    # ── 4. Clean stray OR conditions between current_sem and marks for current student queries ─
    if effective_query and target_sem is not None:
        marks_hist = bool(re.search(
            r"\b(?:students?\s+)?who\s+(?:have|got|scored|taken|appeared\s+in)\b.*\bmarks?\b|"
            r"\bmarks?\s+(?:for|of|in)\b.*\bsem(?:ester)?\b",
            effective_query.lower(),
        ))
        if not marks_hist:
            cleaned = re.sub(
                r'\(\s*(?:(?:s|students)\.)?current_sem\s*=\s*' + str(target_sem) + r'\s+OR\s+EXISTS\s*\([^)]+\)\s*\)',
                f's.current_sem = {target_sem}',
                cleaned, flags=re.I
            )

    return cleaned


def generate_sql_query(natural_query: str, user_role: str, retry_count: int = 0) -> dict:
    schema = _load_schema_context()

    # Sprint 2: Preprocess Kannada/mixed queries
    normalized_query, lang = normalize_query(natural_query)
    lang_context = build_language_context(natural_query, normalized_query, lang)

    # Use normalized query for SQL generation
    effective_query = normalized_query if normalized_query != natural_query else natural_query

    # ── Step 1: Rule-based matching (deterministic, authoritative) ───────────
    fallback_query = _rule_based_fallback_sql(effective_query)
    fallback_sql = None
    fallback_params = []
    if fallback_query:
        fallback_sql, fallback_params = fallback_query if isinstance(fallback_query, tuple) else (fallback_query, [])

        # ── Validation: rule-built SQL must still pass sem/branch checks ──
        ok_rule, _err_rule = _validate_semester_branch_sql(
            fallback_sql, effective_query, fallback_params
        )
        if ok_rule:
            return {
                "success": True,
                "sql": fallback_sql,
                "raw": fallback_sql,
                "query_dict": {"operation": "select", "sql": fallback_sql, "params": fallback_params},
                "response_language": lang if 'lang' in locals() else 'english',
            }
        # Rule-based SQL failed validation → rebuild explicitly via comprehensive handler
        tsem = _detect_target_semester(effective_query)
        tbr  = _extract_branches(effective_query)
        rebuilt = _build_comprehensive_student_query(effective_query, tsem, tbr)
        if rebuilt:
            r_sql, r_params = rebuilt
            return {
                "success": True,
                "sql": r_sql,
                "raw": r_sql,
                "query_dict": {"operation": "select", "sql": r_sql, "params": r_params},
                "response_language": lang if 'lang' in locals() else 'english',
            }


    # ── Step 2: LLM generation with strict semester/branch prompt injection ──
    extra_sem_branch_rules = ""
    tsem = _detect_target_semester(effective_query)
    tbr  = _extract_branches(effective_query)
    if tsem is not None:
        marks_hist = bool(re.search(
            r"\b(?:students?\s+)?who\s+(?:have|got|scored|taken|appeared\s+in)\b.*\bmarks?\b|"
            r"\bmarks?\s+(?:for|of|in)\b.*\bsem(?:ester)?\b",
            effective_query.lower(),
        ))
        if marks_hist:
            sem_instruction = f"EXISTS (SELECT 1 FROM marks m WHERE m.usn = s.usn AND m.semester = {tsem})"
        else:
            sem_instruction = f"s.current_sem = {tsem}"
        extra_sem_branch_rules += (
            f"\nMANDATORY SEMESTER RULE: The user explicitly requested semester = {tsem}.\n"
            f"  Your WHERE clause MUST contain: {sem_instruction}.\n"
            f"  NEVER use >=, <=, >, <, or any semester value other than EXACTLY {tsem}.\n"
            f"  NEVER add OR conditions that would include other semesters or historical marks.\n"
        )
    if tbr:
        for b in tbr:
            aliases = _normalize_branch(b) or (b.upper(),)
            extra_sem_branch_rules += (
                f"\nMANDATORY BRANCH RULE: user requested branch = {b} (aliases: {aliases}).\n"
                f"  Your WHERE clause MUST restrict UPPER(s.branch) / s.year_and_branch / s.usn to these aliases.\n"
                f"  NEVER omit the branch filter. NEVER return all branches.\n"
            )

    schema_with_context = lang_context + schema if lang_context else schema
    prompt = _SYSTEM_PROMPT.format(schema=schema_with_context, query=effective_query, role=user_role)
    if extra_sem_branch_rules:
        # Inject just before the final USER QUERY line
        prompt = prompt.replace(
            "USER QUERY: {query}",
            "═══════════════════════════════════════════════════════\n"
            + extra_sem_branch_rules +
            "═══════════════════════════════════════════════════════\n"
            "USER QUERY: {query}"
        )
    raw = llm_service.generate_query(prompt).strip()

    if raw.startswith("ERROR:"):
        if fallback_sql:
            raw = fallback_sql
            raw_sql = fallback_sql
        else:
            return {"success": False, "error_msg": raw, "sql": None}
    else:
        raw_sql = _strip_markdown(raw)

    sql = raw_sql

    if not _is_safe_dml(sql):
        if fallback_sql:
            sql = fallback_sql
        elif retry_count < 2:
            return generate_sql_query(
                natural_query + " (Output ONLY a valid SQL — SELECT, INSERT, UPDATE, or DELETE.)",
                user_role, retry_count + 1
            )
        else:
            return {"success": False, "error_msg": "Could not generate a valid SQL query.", "sql": None}

    op = re.match(r'^\s*(\w+)', sql.upper()).group(1).lower()

    if op == 'select':
        sql = _fix_window_order(sql)

    sql = _clean_llm_sql(sql, effective_query)

    # ── Step 3: SQL VALIDATION (semester + branch) before returning ───────────
    if op == 'select' and (tsem is not None or tbr):
        valid, err_msg = _validate_semester_branch_sql(sql, effective_query)
        if not valid:
            # Rebuild using the authoritative comprehensive handler instead of LLM
            rebuilt = _build_comprehensive_student_query(effective_query, tsem, tbr)
            if rebuilt:
                r_sql, r_params = rebuilt
                return {
                    "success": True,
                    "sql": r_sql,
                    "raw": r_sql,
                    "query_dict": {"operation": "select", "sql": r_sql, "params": r_params},
                    "response_language": lang if 'lang' in locals() else 'english',
                }
            # If comprehensive handler can't build, retry LLM once with explicit reminder
            if retry_count < 1:
                return generate_sql_query(
                    natural_query + f" (CRITICALLY IMPORTANT: {err_msg}. Use exact equality only.)",
                    user_role, retry_count + 1
                )

    params_for_dict = fallback_params if (sql == fallback_sql and fallback_params) else []

    result = {
        "success": True,
        "sql": sql,
        "raw": sql,
        "query_dict": {"operation": op, "sql": sql},
        "response_language": lang if 'lang' in dir() else 'english',
    }
    if params_for_dict:
        result["query_dict"]["params"] = params_for_dict
    return result


generate_mongo_query = generate_sql_query
