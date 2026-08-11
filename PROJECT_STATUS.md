# AI-Driven Database Query Automation System: Project Status & Documentation

## 📌 Project Overview
This project is a production-ready, full-stack **AI-Driven Voice & Text Based Database Query Automation System** focused on Student Data Management. It allows users to query, manipulate, and export database records using natural language (voice or text). The system securely translates user intent into optimized MySQL queries using the NVIDIA LLM API and a RAG (Retrieval-Augmented Generation) pipeline for schema awareness.

---

## 🏗️ Technology Stack

| Layer | Technology |
|---|---|
| **Frontend** | React.js 18, Vite, TailwindCSS |
| **Backend** | Python 3, FastAPI (REST API) |
| **Database** | MySQL (migrated from MongoDB → SQLite → MySQL) |
| **AI / LLM** | NVIDIA LLM API (Llama 3 70B) |
| **Data Tools** | Pandas, ReportLab, SQLParse |
| **Auth** | JWT tokens, bcrypt password hashing |
| **File Parsing** | openpyxl, pandas (CSV, Excel, JSON support) |

---

## ✅ Completed Features

### 🗄️ Database & Schema
- **MySQL fully operational** with connection pooling (pool size 20)
- **Auto-migration on startup** — `_add_col_if_missing()` ensures the schema self-heals on every server start
- **Students table** contains 23 columns covering full personal + academic profile:
  - Identity: `usn`, `name`, `dob`, `gender`, `aadhar_no`
  - Family: `father_name`, `mother_name`
  - Medical: `blood_group`
  - Social: `religion`, `caste`, `sub_caste`, `category`
  - Contact: `phone`, `email`
  - Address: `address`, `permanent_address`, `current_address`
  - Academic: `year_of_joining`, `current_sem`, `status`, `year_and_branch`
  - Meta: `source_file`
- **Marks table**: `usn`, `semester`, `sgpa`, `cgpa`, `year`
- **Schema metadata table**: AI reads live column list dynamically at query time
- **Query history & security logs** tables for audit trail

### 🤖 AI Query Engine (RAG Pipeline)
- Natural language → validated, optimized MySQL SQL
- **RAG schema indexing**: AI dynamically fetches live column list from `schema_metadata` before building every prompt
- **SQL Optimizer**: Rewrites `SELECT *` into explicit column lists
- **Window function CGPA**: Cumulative CGPA calculated per semester using `AVG() OVER (PARTITION BY...)` — never uses a stored column
- **Semester-first filter rule**: Top-N queries always filter by semester before ranking
- **Conditional JOIN logic**: Only JOINs the marks table if academic data is requested; personal-only queries target only the `students` table
- **Query wrapping**: Auto-wraps window-function results in subquery when `ORDER BY` references a computed alias

### 🔒 Security
- **AST-based SQL injection detection** via `sqlparse`
- **Blocklist enforcement**: Rejects `DROP`, `ALTER`, `TRUNCATE`, `CREATE`, `GRANT`, `REVOKE`
- **DELETE/UPDATE guard**: Requires `WHERE` clause — no blind bulk operations
- **Role-Based Access Control**:
  - `Admin` — SELECT only
  - `Staff` — Full CRUD (SELECT, INSERT, UPDATE, DELETE)
- **Double confirmation modals** on frontend before any DELETE is dispatched

### 📁 File Upload & Ingestion
- Accepts: CSV, Excel (xlsx/xls), JSON, PDF, TXT, PNG/JPG
- **AI Column Mapper** (`ai_column_mapper.py`): Normalizes arbitrary column names to canonical DB columns using exact + safe partial matching with 80+ alias entries
- **Wide-format unpivoting**: Converts wide GPA sheets (`1st Sem SGPA`, `2nd Sem CGPA`…) into long-format rows automatically
- **Upsert logic**: UPDATE if student exists, INSERT if new — always applies non-null values from new files (allows personal details file to enrich an existing academic record)
- **Strict data isolation**: Data tied to source file; deletions are file-scoped
- **USN validation**: Pattern-matched; rejects phone numbers, Aadhar numbers, and names from being treated as USNs

### 📅 Date Handling
- `_safe_date()` normalizes any date format (`8/26/2004`, `26-08-2004`, `August 26 2004`) to MySQL-compatible `YYYY-MM-DD` before inserting/updating the `dob` column

### 📤 Export
- Query results downloadable as **CSV**, **Excel**, **PDF** via `StreamingResponse`
- Export driven directly from LLM query results

### 🎙️ Voice Input
- `webkitSpeechRecognition` integrated on frontend — click microphone, speak query, runs automatically

### 📊 UI Features
- Query history sidebar (last 10 queries per session)
- Audit log view
- File Explorer with upload status, row counts, and delete controls
- Validation dashboard: detects missing names, invalid SGPA ranges, duplicate students
- Academic Performance table with semester-wise SGPA + cumulative CGPA trend arrows

---

## 🔧 Bugs Fixed (This Session)

| Error | Fix Applied |
|---|---|
| `1406: Data too long for 'usn'` | Expanded `usn` from `VARCHAR(20)` → `VARCHAR(100)` across all schema files, `database.py`, `init_mysql.py`, `rag_sql_generator.py`, `schema_metadata.json` |
| `1292: Incorrect date value '8/26/2004'` | Added `_safe_date()` using `pandas.to_datetime()` to normalize any date format to `YYYY-MM-DD` before DB insert |
| Personal details not saving from 2nd file | Fixed upsert guard — now always writes non-null values from new uploads instead of skipping if column already had a value |
| Father name query returning SGPA rows | Updated LLM prompt rule: JOIN marks only when academic data is needed; personal-only queries go to `students` table alone |
| Missing columns (`caste`, `permanent_address`, etc.) | Added 6 new columns to `students` table; updated `STUDENT_COLS`, `_COL_MAX`, column mapper, LLM schema, and DB seed |
| Broken SQL example in LLM prompt | Fixed orphaned SQL line that had no `Q:` prefix |
| Double comma syntax error in `database.py` | Fixed `,,` typo in seed list |
| USN guard blocking valid long USNs | Updated hard-coded `len(usn) > 20` guard to `len(usn) > 100` |

---

## 📂 Key Files & Their Roles

| File | Role |
|---|---|
| `backend/main.py` | FastAPI app entry point |
| `backend/database.py` | Connection pool, table creation, auto-migration |
| `backend/routes_files.py` | File upload, parse, upsert into MySQL |
| `backend/routes_query.py` | Receive NL query → generate SQL → execute → return results |
| `backend/rag_sql_generator.py` | RAG prompt builder + NVIDIA LLM call + SQL safety checks |
| `backend/ai_column_mapper.py` | Normalizes CSV column names to canonical DB columns |
| `backend/file_parser.py` | Parses CSV/Excel/JSON into records + extracts GPA data |
| `backend/query_security_validator.py` | AST-based SQL injection & destructive query blocker |
| `backend/llm_service.py` | NVIDIA API wrapper |
| `backend/auth.py` | JWT login/registration |
| `backend/routes_export.py` | CSV/Excel/PDF export endpoints |
| `backend/fuzzy_search.py` | Fuzzy name/USN search fallback |
| `backend/schema_metadata.json` | Static schema reference for AI |
| `backend/init_mysql.py` | One-time DB + default user initialization script |
| `frontend/src/` | React app — Dashboard, Login, Voice, Export UI |
| `mysql_system/database/schema.sql` | Reference SQL schema for college DB |
| `PROJECT_STATUS.md` | This file — full project status documentation |

---

## 🚀 How to Run

```bash
# Backend
cd backend
.venv\Scripts\activate
python main.py          # runs on http://localhost:8000

# Frontend (separate terminal)
cd frontend
npm run dev             # runs on http://localhost:5173
```

**Login credentials:**
- Admin: `admin` / `admin123` (SELECT only)
- Staff: `staff` / `staff123` (full CRUD)

---

## 📋 Sample Queries That Work

```
show all students
manoj j r father name
show personal details of all students
show marks of all students
top 5 students in semester 3
overall cgpa of all students
show all details of USN 4HG23CS032
show students in CSE department
compare students in semester 2
```

---

## 🗺️ Remaining Roadmap

| Feature | Status |
|---|---|
| Query result caching (Redis / query_cache table) | ❌ Not started |
| Dynamic CGPA stored calculation | ❌ Uses window function (correct but not persisted) |
| Charts & visualizations (bar/pie/line auto-detect) | ❌ Not started |
| Data validation dashboard (UI) | ⚠️ Backend endpoint exists, no dedicated UI page |
| AI-assisted PDF/unstructured file ingestion | ❌ Not started |
| WebSocket for long-running queries | ❌ Not started |
