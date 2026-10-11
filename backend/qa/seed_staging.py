"""Build the isolated staging database used by the master QA run.

Structure comes from the live schema (qa/staging_structure.sql); the data is
100% synthetic and deterministic, so every phase can compute expected answers
from this database without ever touching production records.

Usage:  MYSQL_DB=student_db_staging python -m qa.seed_staging
"""
import hashlib
import os
import random
import sys

import mysql.connector
from config import settings

STAGING_DB = os.environ.get("MYSQL_DB", "student_db_staging")
if STAGING_DB == "student_db":
    sys.exit("Refusing to seed the production database name 'student_db'.")

YEAR = 2026
Q = "QA24"          # marks every synthetic USN so a stray row is recognisable
BRANCHES = ["CS", "ECR", "CIV", "MEC"]
DISTRICTS = ["Dharwad", "Belagavi", "Bengaluru Urban", "Kolar", "Mysuru", ""]
VILLAGES = ["Hubballi", "Dharwad", "Gokak", "Malur", "Hunsur", ""]
AREA_TYPES = ["Rural", "Urban", ""]
CASTES = ["General", "OBC", "SC", "ST", ""]
RELIGIONS = ["Hindu", "Muslim", "Christian", ""]
FATHER_OCC = ["Farmer", "Teacher", "Business", "Govt Service", "Labour", ""]
MOTHER_OCC = ["Homemaker", "Teacher", "Farmer", ""]
FEE_TYPES = ["Tuition", "VTU", "PD", "IDP"]
FEE_STATUSES = ["Paid", "Not Paid", "Partially Paid", "pending", ""]
BLOOD = ["O+", "B+", "A+", "AB+", ""]

# Kannada-script and romanised names exercise the multilingual parser.
KANNADA_NAMES = ["ಮನೋಜ ಕುಮಾರ್", "ಲಕ್ಷ್ಮೀ ದೇವಿ", "ರಾಹುಲ್ ಪಟೀಲ್"]
KANNADA_VILLAGES = ["ಧಾರವಾಡ", "ಗೋಕಾಕ್", "ಹುಬ್ಬಳ್ಳಿ"]

TRUNCATE = [
    "students", "student_personal", "marks", "semester_gpa", "student_fees",
    "student_backlogs", "student_lifecycle_events", "student_lifecycle_status",
    "readmission_requests", "student_history", "student_field_sources",
    "audit_log", "query_history", "export_logs", "deletion_logs",
    "global_undo_snapshots", "file_delete_provenance_snapshots", "query_cache",
    "validation_log", "soft_deleted_students", "uploaded_data", "upload_versions",
    "users",
]

# Lifecycle fixtures: (count, status) pairs covering every implemented state.
LIFECYCLE_MIX = [
    ("Active", 34),
    ("Temporarily Discontinued", 4),
    ("Discontinued-Review Req", 3),
    ("Dropout-College Recorded", 5),
    ("Readmission Requested", 3),
    ("Readmission Approved", 2),
    ("Rejoined-Active", 3),
    ("Graduated", 4),
    ("Transferred", 2),
    ("Admission Cancelled", 2),
    ("Other", 1),
]

LIFECYCLE_REASONS = {
    "Active": ("admitted and continuing", "Academic"),
    "Temporarily Discontinued": ("medical leave for one semester", "Medical"),
    "Discontinued-Review Req": ("discontinued, pending review", "Administrative"),
    "Dropout-College Recorded": ("financial difficulty", "Financial"),
    "Readmission Requested": ("readmission requested for 5th semester", "Academic"),
    "Readmission Approved": ("readmission approved by the college", "Academic"),
    "Rejoined-Active": ("rejoined after medical leave", "Medical"),
    "Graduated": ("completed B.E. course", "Academic"),
    "Transferred": ("transferred to another college", "Administrative"),
    "Admission Cancelled": ("cancellation of admission", "Administrative"),
    "Other": ("other recorded reason", "Administrative"),
}


def _pw(role):
    """Deterministic bcrypt-free password hash placeholder is not usable; use bcrypt."""
    import bcrypt
    return bcrypt.hashpw(role.encode(), bcrypt.gensalt()).decode()


def first_names(rng):
    return rng.choice([
        "Manoj", "Rahul", "Lakshmi", "Priya", "Vinod", "Sneha", "Kiran",
        "Ananya", "Rohit", "Pooja", "Suresh", "Neha", "Deepak", "Shruti",
        "Ganesh", "Divya", "Nikhil", "Trisha", "Vijay", "Kavya",
    ])


def connect():
    return mysql.connector.connect(
        host=settings.MYSQL_HOST,
        port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD,
        database=STAGING_DB,
        autocommit=False,
    )


def seed(conn):
    rng = random.Random(20261011)
    cur = conn.cursor()

    cur.execute("SET FOREIGN_KEY_CHECKS=0")
    for t in TRUNCATE:
        cur.execute(f"TRUNCATE TABLE `{t}`")
    cur.execute("SET FOREIGN_KEY_CHECKS=1")

    for uname, role in [("qa_admin", "Admin"), ("qa_staff", "Staff"), ("qa_viewer", "Viewer")]:
        cur.execute(
            "INSERT INTO users (username,email,password_hash,role) VALUES (%s,%s,%s,%s)",
            (uname, f"{uname}@qa.invalid", _pw(uname), role),
        )

    # ---- students ----------------------------------------------------------
    rows = []
    seq = 0
    for status, count in LIFECYCLE_MIX:
        for _ in range(count):
            seq += 1
            branch = BRANCHES[rng.randrange(len(BRANCHES))]
            yy = rng.choice(["21", "22", "23", "24"])
            usn = f"9QA{yy}{branch}{seq:03d}"
            adm_year = 2000 + int(yy)
            name = f"{first_names(rng)} {first_names(rng)}"
            rows.append(dict(usn=usn, name=name, branch=branch, yy=yy,
                             adm_year=adm_year, status=status))

    # Deliberate duplicates: same name, different USN (identity ambiguity).
    rows[3]["name"] = rows[4]["name"] = "Rahul Kumar"
    rows[5]["name"] = "Rahul Kumar"
    # Multilingual fixtures
    rows[7]["name"] = KANNADA_NAMES[0]
    rows[8]["name"] = KANNADA_NAMES[1]
    rows[9]["name"] = KANNADA_NAMES[2]

    # Named anchors: a few regression tests look students up by a specific VTU
    # USN, so those USNs must exist in any database the suite runs against.
    for usn, sem, adm in [("4HG23CS032", 6, 2023), ("4HG24CS007", 4, 2024)]:
        rows.append(dict(usn=usn, name=f"QA Anchor {usn}", branch="CS",
                         yy=str(adm)[2:], adm_year=adm, status="Active",
                         anchor_sem=sem))

    STUDENT_COLS = [
        "usn", "name", "dob", "year_of_joining", "current_sem", "status",
        "father_name", "mother_name", "blood_group", "address", "gender",
        "religion", "category", "email", "phone", "year_and_branch", "caste",
        "sub_caste", "permanent_address", "current_address", "aadhar_no",
        "source_file", "admission_year", "current_year", "student_type",
        "estimated_semester", "branch", "division", "domain", "village",
        "area_type", "area", "taluk", "district", "state", "cgpa",
        "father_occupation", "mother_occupation", "parents_phone",
        "kannada_medium", "pin_code", "backlogs", "lifecycle_status",
        "usn_provisional", "dynamic_data", "distance_from_college",
    ]
    students_sql = (
        "INSERT INTO students (" + ",".join(STUDENT_COLS) + ") VALUES ("
        + ",".join(["%s"] * len(STUDENT_COLS)) + ")"
    )
    total = 0
    for idx, r in enumerate(rows):
        sem = r.get("anchor_sem") or rng.choice([2, 4, 6, 8])
        # Boundary values the brief demands: exactly 8.0, 7.5, 6.0.
        if idx == 0:
            cgpa = 8.00
        elif idx == 1:
            cgpa = 7.50
        elif idx == 2:
            cgpa = 6.00
        else:
            cgpa = round(rng.uniform(4.2, 9.4), 2)
        district = rng.choice(DISTRICTS)
        village = rng.choice(VILLAGES + KANNADA_VILLAGES)
        # Missing personal details, complete academics (Phase 3 fixture).
        sparse = idx in (10, 11, 12)
        adm_year = r["adm_year"]
        cur.execute(students_sql, (
            r["usn"], r["name"],
            f"200{rng.choice(['4','5','6','7'])}-0{rng.randint(1,9)}-{rng.randint(10,28)}",
            adm_year, sem, "ACTIVE",
            "" if sparse else first_names(rng) + "appa",
            "" if sparse else first_names(rng) + "amma",
            rng.choice(BLOOD),
            "" if sparse else f"{village or 'Hubballi'}, Karnataka",
            rng.choice(["Male", "Female"]),
            rng.choice(RELIGIONS), rng.choice(CASTES),
            "" if sparse else f"{r['usn'].lower()}@qa.invalid",
            "" if sparse or idx % 5 == 0 else f"9{rng.randint(100000000, 999999999)}",
            f"{sem//2} Year {r['branch']}",
            rng.choice(CASTES), rng.choice(["", "Sub"]),
            "" if sparse else f"Perm {village}", f"Cur {village}",
            "" if sparse else f"{rng.randint(100000000000, 999999999999)}",
            "qa_seed.xlsx", adm_year, YEAR - adm_year + 1,
            rng.choice(["Regular", "Lateral"]), sem, r["branch"],
            rng.choice(["A", "B"]), "", village,
            rng.choice(AREA_TYPES), "", "Dharwad", district, "Karnataka",
            cgpa, rng.choice(FATHER_OCC),
            # mother's phone missing is a specific Phase 3 filter
            # Phase 3 filter: mother's contact number missing for some rows
            rng.choice(MOTHER_OCC),
            "" if sparse or idx % 3 == 0 else f"9{rng.randint(10000000, 99999999)}",
            rng.choice(["Yes", "No", ""]),
            f"5800{rng.randint(10, 99)}", "", r["status"], 0,
            None, rng.choice(["", "3", "12", "28", "45", "49", "60", "85", "150"]),
        ))
        r["cgpa"] = cgpa
        r["sem"] = sem
        r["district"] = district
        total += 1

    cur.execute("SELECT usn, student_id FROM students")
    sid = dict(cur.fetchall())

    # ---- personal mirror + marks (authoritative CGPA) ----------------------
    for r in rows:
        cur.execute(
            "INSERT INTO student_personal (student_id,father_name,mother_name,blood_group,address) "
            "VALUES (%s,%s,%s,%s,%s)",
            (sid[r["usn"]], f"{first_names(rng)}appa", f"{first_names(rng)}amma",
             rng.choice(BLOOD), r["district"]),
        )
        sgpas = []
        for s in range(1, r["sem"] + 1):
            target = r["cgpa"] + round(rng.uniform(-0.9, 0.9), 2)
            sg = max(3.0, min(10.0, round(target, 2)))
            sgpas.append(sg)
            cur.execute(
                "INSERT INTO marks (usn,semester,sgpa,cgpa,year,name,father_name) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (r["usn"], s, sg, sg, YEAR - (r["adm_year"] - 2021), r["name"], ""),
            )
            cur.execute(
                "INSERT INTO semester_gpa (student_id,semester,sgpa,cgpa,year) "
                "VALUES (%s,%s,%s,%s,%s)",
                (sid[r["usn"]], s, sg, sg, YEAR),
            )

    # ---- backlogs ----------------------------------------------------------
    backlog_counts = {}
    for idx, r in enumerate(rows):
        n = 0 if idx % 2 == 0 else rng.choice([0, 1, 2, 3])
        if idx in (0, 1):          # zero-backlog high-CGPA fixtures
            n = 0
        backlog_counts[r["usn"]] = n
        for b in range(n):
            cur.execute(
                "INSERT INTO student_backlogs (usn,subject,semester,year,raw_text,cleared) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (r["usn"], f"18CS{400+b*7}", max(1, r["sem"] - b),
                 str(r["adm_year"]), "", rng.choice([0, 0, 1])),
            )

    # ---- fees --------------------------------------------------------------
    fee_status_by_usn = {}
    for idx, r in enumerate(rows):
        # College-shaped data: most students are clear, dues concentrate on a
        # minority, so "who paid" is provably a larger set than "who did not".
        has_due = rng.random() < 0.3
        st = []
        for ft in FEE_TYPES:
            if idx % 7 == 0 and ft in ("VTU", "PD"):
                status = "Not Paid"
            elif not has_due:
                status = "Paid"
            else:
                status = rng.choice(["Not Paid", "pending", "Partially Paid", "Paid", "no"])
            due = 0 if status == "Paid" else rng.choice([0, 1500, 3200, 4500, 7000])
            cur.execute(
                "INSERT INTO student_fees (usn,fee_type,year,status,amount_paid,remaining_amount) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (r["usn"], ft, min(4, (r["sem"] + 1) // 2), status,
                 "0" if status == "Not Paid" else "52000", str(due)),
            )
            st.append((ft, status, due))
        fee_status_by_usn[r["usn"]] = st

    # ---- lifecycle current-state + event history ---------------------------
    for r in rows:
        status = r["status"]
        reason, cat = LIFECYCLE_REASONS[status]
        eff = f"2026-0{rng.randint(1, 8)}-1{rng.randint(0, 8)}"
        cur.execute(
            "INSERT INTO student_lifecycle_status "
            "(usn,current_status,effective_date,last_enrolled_semester,"
            " last_enrolled_academic_year,scheme,reason,document_ref,updated_by,reason_category) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (r["usn"], status, eff, r["sem"] - 1 if status != "Active" else None,
             "2023-24", "VTU-2022", reason, "", "qa_admin", cat),
        )
        cur.execute(
            "INSERT INTO student_lifecycle_events "
            "(usn,event_type,from_status,to_status,effective_date,"
            " last_enrolled_semester,last_enrolled_academic_year,academic_year,"
            " scheme,reason,reason_category,actor_username,actor_role) "
            "VALUES (%s,'status_change','Active',%s,%s,%s,'2023-24','2023-24',%s,%s,%s,'qa_admin','Admin')",
            (r["usn"], status, eff, r["sem"], "VTU-2022", reason, cat),
        )

    conn.commit()

    # ---- report the fixture invariants the later phases rely on ------------
    cur.execute("SELECT COUNT(*) FROM students")
    n_students = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM marks")
    n_marks = cur.fetchone()[0]
    print(json_summary(rows, backlog_counts, fee_status_by_usn, n_students, n_marks))


def json_summary(rows, bl, fee, n_students, n_marks):
    import json
    active = sum(1 for r in rows if r["status"] == "Active")
    dist = {}
    for r in rows:
        dist[r["district"] or "(blank)"] = dist.get(r["district"] or "(blank)", 0) + 1
    return json.dumps({
        "students": n_students, "marks_rows": n_marks, "active": active,
        "statuses": {s: sum(1 for r in rows if r["status"] == s) for _, s in
                     [(c, s) for s, c in LIFECYCLE_MIX]},
        "districts": dist,
        "with_backlogs": sum(1 for v in bl.values() if v > 0),
        "unpaid": sum(1 for v in fee.values() if any(s in ("Not Paid", "pending") for _, s, _ in v)),
    }, indent=2)


def main():
    conn = connect()
    try:
        seed(conn)
        print(f"STAGING_SEED_OK db={STAGING_DB}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
