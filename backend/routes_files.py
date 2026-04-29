from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from datetime import datetime
from database import get_db_connection
from auth import get_current_user
from file_parser import parse_file

router = APIRouter(prefix="/api/files", tags=["File Management"])
_file_cache = {}
STUDENT_COLS = ["name","dob","year_of_joining","current_sem","father_name","mother_name","blood_group","address","status"]

def _safe_int(val):
    try: return int(float(val))
    except: return None

def _safe_dec(val):
    try:
        f = float(val); return round(f,2) if f==f else None
    except: return None

def _upsert_student(cur, usn, row):
    cur.execute("SELECT * FROM students WHERE usn=%s", (usn,))
    existing = cur.fetchone()
    if existing:
        updates, params = [], []
        for col in STUDENT_COLS:
            v = row.get(col)
            if v is not None and str(v).strip() not in ("","nan","None"):
                if col == "name" or existing.get(col) is None or str(existing.get(col)).strip() == "":
                    updates.append(f"{col}=%s"); params.append(v)
        if updates:
            params.append(usn)
            cur.execute(f"UPDATE students SET {','.join(updates)} WHERE usn=%s", tuple(params))
        return False
    else:
        fields, vals = ["usn"], [usn]
        for col in STUDENT_COLS:
            v = row.get(col)
            if v is not None and str(v).strip() not in ("","nan","None"):
                fields.append(col); vals.append(v)
        cur.execute(f"INSERT INTO students ({','.join(fields)}) VALUES ({','.join(['%s']*len(fields))})", tuple(vals))
        return True

def _upsert_mark(cur, usn, semester, sgpa):
    if sgpa is None: return False
    cur.execute("SELECT id FROM marks WHERE usn=%s AND semester=%s", (usn, semester))
    if cur.fetchone():
        cur.execute("UPDATE marks SET sgpa=%s WHERE usn=%s AND semester=%s", (sgpa, usn, semester))
        return False
    cur.execute("INSERT INTO marks (usn,semester,sgpa) VALUES (%s,%s,%s)", (usn, semester, sgpa))
    return True

def _clear_cache(conn):
    try:
        c = conn.cursor(); c.execute("DELETE FROM query_cache"); c.close()
    except: pass

def _safe_int(val):
    try: return int(float(val))
    except: return None

def _safe_dec(val):
    try:
        f = float(val); return round(f,2) if f==f else None
    except: return None

def _upsert_student(cur, usn, row):
    cur.execute("SELECT * FROM students WHERE usn=%s", (usn,))
    existing = cur.fetchone()
    if existing:
        updates, params = [], []
        for col in STUDENT_COLS:
            v = row.get(col)
            if v is not None and str(v).strip() not in ("","nan","None"):
                if col == "name" or existing.get(col) is None or str(existing.get(col)).strip() == "":
                    updates.append(f"{col}=%s"); params.append(v)
        if updates:
            params.append(usn)
            cur.execute(f"UPDATE students SET {','.join(updates)} WHERE usn=%s", tuple(params))
        return False
    else:
        fields, vals = ["usn"], [usn]
        for col in STUDENT_COLS:
            v = row.get(col)
            if v is not None and str(v).strip() not in ("","nan","None"):
                fields.append(col); vals.append(v)
        cur.execute(f"INSERT INTO students ({','.join(fields)}) VALUES ({','.join(['%s']*len(fields))})", tuple(vals))
        return True

def _upsert_mark(cur, usn, semester, sgpa):
    if sgpa is None: return False
    cur.execute("SELECT id FROM marks WHERE usn=%s AND semester=%s", (usn, semester))
    if cur.fetchone():
        cur.execute("UPDATE marks SET sgpa=%s WHERE usn=%s AND semester=%s", (sgpa, usn, semester))
        return False
    cur.execute("INSERT INTO marks (usn,semester,sgpa) VALUES (%s,%s,%s)", (usn, semester, sgpa))
    return True

def _clear_cache(conn):
    try:
        c = conn.cursor(); c.execute("DELETE FROM query_cache"); c.close()
    except: pass


@router.post("/upload")
async def upload_file(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "Staff":
        raise HTTPException(403, "Only Staff can upload files.")
    content = await file.read()
    if not content: raise HTTPException(400, "Empty file.")
    ext = file.filename.rsplit(".",1)[-1].lower() if "." in file.filename else ""
    if ext not in {"csv","xlsx","xls","json","pdf","txt","png","jpg","jpeg"}:
        raise HTTPException(422, f"Unsupported: .{ext}")
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute("DELETE FROM uploaded_files WHERE filename=%s", (file.filename,))
        cur.execute(
            "INSERT INTO uploaded_files (filename,content_type,file_type,size_bytes,uploaded_by,uploaded_at,db_status) VALUES (%s,%s,%s,%s,%s,%s,'pending')",
            (file.filename, file.content_type or ext, ext, len(content), current_user["username"], datetime.now())
        )
        conn.commit()
    finally:
        cur.close(); conn.close()
    _file_cache[file.filename] = content
    return {"success":True,"filename":file.filename,"file_type":ext,"size_bytes":len(content),"db_status":"pending","message":"File uploaded. Click Update Database to save data."}


@router.post("/update-db/{filename}")
def update_database(filename: str, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "Staff":
        raise HTTPException(403, "Only Staff can update the database.")
    content = _file_cache.get(filename)
    if content is None: raise HTTPException(404, "File not in cache. Please re-upload.")
    try:
        parsed = parse_file(filename, content)
    except ValueError as e:
        raise HTTPException(422, str(e))
    gpa_data = parsed.get("gpa_data", [])
    mapped_recs = parsed.get("mapped_records", [])
    students_new = marks_new = 0
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        if gpa_data:
            for row in gpa_data:
                usn = str(row.get("usn","") or "").strip()
                name = str(row.get("name","") or "").strip()
                sem = _safe_int(row.get("semester"))
                sgpa = _safe_dec(row.get("sgpa")) or _safe_dec(row.get("cgpa"))
                if not usn:
                    if name: usn = f"AUTO_{name[:12].replace(' ','_').upper()}"
                    else: continue
                if _upsert_student(cur, usn, {"name": name}): students_new += 1
                if sem is not None and sgpa is not None:
                    if _upsert_mark(cur, usn, sem, sgpa): marks_new += 1
        elif mapped_recs:
            for row in mapped_recs:
                usn = str(row.get("usn","") or "").strip()
                name = str(row.get("name","") or "").strip()
                sem = _safe_int(row.get("semester"))
                sgpa = _safe_dec(row.get("sgpa")) or _safe_dec(row.get("cgpa"))
                if not usn and not name: continue
                if not usn: usn = f"AUTO_{name[:12].replace(' ','_').upper()}"
                srow = {col: row.get(col) for col in STUDENT_COLS}
                srow["name"] = name
                if _upsert_student(cur, usn, srow): students_new += 1
                if sem is not None and sgpa is not None:
                    if _upsert_mark(cur, usn, sem, sgpa): marks_new += 1
        _clear_cache(conn)
        cur.execute(
            "UPDATE uploaded_files SET db_status='saved',row_count=%s,students_saved=%s,marks_saved=%s,gpa_rows=%s,uploaded_at=%s WHERE filename=%s",
            (parsed["row_count"], students_new, marks_new, marks_new, datetime.now(), filename)
        )
        conn.commit()
    except Exception as e:
        conn.rollback(); raise HTTPException(500, f"DB error: {e}")
    finally:
        cur.close(); conn.close()
    _file_cache.pop(filename, None)
    return {"success":True,"filename":filename,"db_status":"saved","rows_parsed":parsed["row_count"],"students_saved":students_new,"marks_saved":marks_new,"gpa_rows_saved":marks_new,"column_mapping":parsed.get("column_mapping",{}),"message":f"Saved {students_new} student(s) and {marks_new} mark record(s)."}


@router.get("/list")
def list_files(current_user: dict = Depends(get_current_user)):
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT * FROM uploaded_files ORDER BY uploaded_at DESC")
        docs = cur.fetchall()
        for d in docs:
            if d.get("uploaded_at"): d["uploaded_at"] = str(d["uploaded_at"])
            if d.get("db_status") == "pending" and d["filename"] not in _file_cache:
                d["cache_expired"] = True
        return docs
    finally:
        cur.close(); conn.close()


@router.get("/parsed/{filename}")
def get_parsed_preview(filename: str, current_user: dict = Depends(get_current_user)):
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT s.usn, s.name, m.semester, m.sgpa, ROUND((SELECT AVG(m2.sgpa) FROM marks m2 WHERE m2.usn=s.usn),2) AS cgpa FROM students s LEFT JOIN marks m ON s.usn=m.usn ORDER BY s.name, m.semester LIMIT 100")
        return cur.fetchall()
    except: return []
    finally:
        cur.close(); conn.close()


@router.get("/gpa")
def get_gpa_data(current_user: dict = Depends(get_current_user)):
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT s.usn, s.name, m.semester, m.sgpa, ROUND((SELECT AVG(m2.sgpa) FROM marks m2 WHERE m2.usn=s.usn),2) AS cgpa FROM students s JOIN marks m ON s.usn=m.usn ORDER BY s.name, m.semester")
        return cur.fetchall()
    except: return []
    finally:
        cur.close(); conn.close()


@router.delete("/delete/{filename}")
def delete_file(filename: str, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "Staff":
        raise HTTPException(403, "Only Staff can delete files.")
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute("DELETE FROM uploaded_files WHERE filename=%s", (filename,))
        conn.commit()
    finally:
        cur.close(); conn.close()
    _file_cache.pop(filename, None)
    return {"success":True,"message":f"Deleted '{filename}'."}


@router.get("/validation")
def validation_dashboard(current_user: dict = Depends(get_current_user)):
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        issues = []
        cur.execute("SELECT usn FROM students WHERE name IS NULL OR name=''")
        for r in cur.fetchall(): issues.append({"type":"missing_name","usn":r["usn"],"detail":"Student has no name"})
        cur.execute("SELECT usn, semester, sgpa FROM marks WHERE sgpa < 0 OR sgpa > 10")
        for r in cur.fetchall(): issues.append({"type":"invalid_sgpa","usn":r["usn"],"semester":r["semester"],"detail":f"SGPA {r['sgpa']} out of range"})
        cur.execute("SELECT usn, semester FROM marks WHERE semester < 1 OR semester > 12")
        for r in cur.fetchall(): issues.append({"type":"invalid_semester","usn":r["usn"],"semester":r["semester"],"detail":"Semester out of valid range (1-12)"})
        cur.execute("SELECT usn, COUNT(*) AS cnt FROM marks GROUP BY usn HAVING cnt > 8")
        for r in cur.fetchall(): issues.append({"type":"too_many_semesters","usn":r["usn"],"detail":f"Has {r['cnt']} semester records"})
        cur.execute("SELECT COUNT(*) AS total FROM students"); ts = cur.fetchone()["total"]
        cur.execute("SELECT COUNT(*) AS total FROM marks"); tm = cur.fetchone()["total"]
        return {"total_students":ts,"total_marks":tm,"issues":issues,"issue_count":len(issues)}
    finally:
        cur.close(); conn.close()


@router.get("/duplicates")
def detect_duplicates(current_user: dict = Depends(get_current_user)):
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT name, COUNT(*) AS cnt, GROUP_CONCAT(usn) AS usns FROM students GROUP BY name HAVING cnt > 1")
        return cur.fetchall()
    finally:
        cur.close(); conn.close()
