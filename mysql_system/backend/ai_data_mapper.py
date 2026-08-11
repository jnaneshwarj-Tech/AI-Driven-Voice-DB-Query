"""
ai_data_mapper.py
AI-powered file analysis: classifies columns and maps data to correct tables.
Uses keyword heuristics + LLM fallback.
"""
import pandas as pd
import json
from llm_service import llm_service

# Column keyword maps
PERSONAL_COLS  = {'usn','first_name','last_name','name','email','phone','address','blood_group','father_name','mother_name','father','mother'}
ACADEMIC_COLS  = {'department','dept','admission_year','current_semester','year','branch'}
GPA_COLS       = {'sgpa','cgpa','semester','sem','gpa','grade_point'}
MARKS_COLS     = {'subject','subject_name','internal','internal_marks','external','external_marks','total','total_marks','marks'}


def _normalize_col(col: str) -> str:
    return col.strip().lower().replace(' ', '_').replace('-', '_')


def classify_columns(columns: list[str]) -> dict:
    """Return which table each column belongs to."""
    mapping = {}
    for col in columns:
        nc = _normalize_col(col)
        if nc in PERSONAL_COLS:
            mapping[col] = 'personal'
        elif nc in ACADEMIC_COLS:
            mapping[col] = 'academic'
        elif nc in GPA_COLS:
            mapping[col] = 'gpa'
        elif nc in MARKS_COLS:
            mapping[col] = 'marks'
        else:
            mapping[col] = 'unknown'
    return mapping


def _col(df: pd.DataFrame, candidates: list[str]):
    """Find first matching column name (case-insensitive)."""
    norm = {c.lower().replace(' ', '_'): c for c in df.columns}
    for c in candidates:
        if c in norm:
            return norm[c]
    return None


def map_and_insert(df: pd.DataFrame, db_execute_write, db_execute_query) -> dict:
    """
    Analyze dataframe, classify columns, upsert into correct MySQL tables.
    Returns summary of what was inserted/updated.
    """
    df.columns = [_normalize_col(c) for c in df.columns]
    df = df.where(pd.notnull(df), None)

    col_map = classify_columns(list(df.columns))
    summary = {"personal": 0, "academic": 0, "gpa": 0, "marks": 0, "errors": []}

    usn_col = _col(df, ['usn', 'roll_no', 'roll_number'])
    if not usn_col:
        return {"error": "No USN/roll_no column found. Cannot identify students."}

    for _, row in df.iterrows():
        usn = str(row[usn_col]).strip() if row[usn_col] else None
        if not usn:
            continue

        # Get or create student_id
        existing = db_execute_query("SELECT student_id FROM students_personal WHERE usn = %s", (usn,))
        if existing:
            student_id = existing[0]['student_id']
        else:
            # Insert minimal personal record
            db_execute_write(
                "INSERT IGNORE INTO students_personal (usn) VALUES (%s)", (usn,)
            )
            res = db_execute_query("SELECT student_id FROM students_personal WHERE usn = %s", (usn,))
            student_id = res[0]['student_id']

        # ── Personal fields ──────────────────────────────────────
        personal_fields = {
            'first_name': _col(df, ['first_name', 'name']),
            'last_name':  _col(df, ['last_name']),
            'email':      _col(df, ['email']),
            'phone':      _col(df, ['phone']),
            'address':    _col(df, ['address']),
            'blood_group':_col(df, ['blood_group']),
            'father_name':_col(df, ['father_name', 'father']),
            'mother_name':_col(df, ['mother_name', 'mother']),
        }
        p_updates = {k: row[v] for k, v in personal_fields.items() if v and row.get(v) is not None}
        if p_updates:
            sets = ', '.join(f"{k} = %s" for k in p_updates)
            db_execute_write(
                f"UPDATE students_personal SET {sets} WHERE student_id = %s",
                (*p_updates.values(), student_id)
            )
            summary['personal'] += 1

        # ── Academic fields ──────────────────────────────────────
        dept_col = _col(df, ['department', 'dept', 'branch'])
        yr_col   = _col(df, ['admission_year', 'year'])
        sem_col  = _col(df, ['current_semester', 'semester', 'sem'])
        if dept_col or yr_col:
            dept = row.get(dept_col) if dept_col else None
            yr   = row.get(yr_col)   if yr_col   else None
            sem  = row.get(sem_col)  if sem_col  else None
            acad = db_execute_query("SELECT academic_id FROM students_academic WHERE student_id = %s", (student_id,))
            if acad:
                updates = {}
                if dept: updates['department'] = dept
                if yr:   updates['admission_year'] = int(yr)
                if sem:  updates['current_semester'] = int(sem)
                if updates:
                    sets = ', '.join(f"{k} = %s" for k in updates)
                    db_execute_write(f"UPDATE students_academic SET {sets} WHERE student_id = %s",
                                     (*updates.values(), student_id))
            else:
                db_execute_write(
                    "INSERT INTO students_academic (student_id, department, admission_year, current_semester) VALUES (%s,%s,%s,%s)",
                    (student_id, dept, int(yr) if yr else None, int(sem) if sem else None)
                )
            summary['academic'] += 1

        # ── GPA fields ───────────────────────────────────────────
        sgpa_col = _col(df, ['sgpa', 'sem_gpa'])
        cgpa_col = _col(df, ['cgpa', 'cumulative_gpa'])
        sem_col2 = _col(df, ['semester', 'sem'])
        if (sgpa_col or cgpa_col) and sem_col2:
            sem  = int(row[sem_col2]) if row.get(sem_col2) is not None else None
            sgpa = float(row[sgpa_col]) if sgpa_col and row.get(sgpa_col) is not None else None
            cgpa = float(row[cgpa_col]) if cgpa_col and row.get(cgpa_col) is not None else None
            if sem:
                db_execute_write(
                    """INSERT INTO semester_gpa (student_id, semester, sgpa, cgpa)
                       VALUES (%s, %s, %s, %s)
                       ON DUPLICATE KEY UPDATE sgpa = VALUES(sgpa), cgpa = VALUES(cgpa)""",
                    (student_id, sem, sgpa, cgpa)
                )
                summary['gpa'] += 1

        # ── Marks fields ─────────────────────────────────────────
        subj_col = _col(df, ['subject_name', 'subject', 'course'])
        int_col  = _col(df, ['internal_marks', 'internal', 'cie'])
        ext_col  = _col(df, ['external_marks', 'external', 'see'])
        tot_col  = _col(df, ['total_marks', 'total'])
        sem_col3 = _col(df, ['semester', 'sem'])
        if subj_col and sem_col3:
            sem  = int(row[sem_col3]) if row.get(sem_col3) is not None else None
            subj = str(row[subj_col]) if row.get(subj_col) else None
            int_ = int(row[int_col])  if int_col  and row.get(int_col)  is not None else None
            ext_ = int(row[ext_col])  if ext_col  and row.get(ext_col)  is not None else None
            tot_ = int(row[tot_col])  if tot_col  and row.get(tot_col)  is not None else None
            if sem and subj:
                db_execute_write(
                    """INSERT INTO marks (student_id, semester, subject_name, internal_marks, external_marks, total_marks)
                       VALUES (%s,%s,%s,%s,%s,%s)
                       ON DUPLICATE KEY UPDATE internal_marks=VALUES(internal_marks),
                       external_marks=VALUES(external_marks), total_marks=VALUES(total_marks)""",
                    (student_id, sem, subj, int_, ext_, tot_)
                )
                summary['marks'] += 1

    return summary
