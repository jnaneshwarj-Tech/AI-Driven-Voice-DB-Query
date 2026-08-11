# 🎓 Graduation Management System - Architecture Diagram

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     FRONTEND (React)                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  Dashboard   │  │  Analytics   │  │  Query Box   │         │
│  │  Component   │  │  Dashboard   │  │  (NLP)       │         │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘         │
│         │                  │                  │                  │
└─────────┼──────────────────┼──────────────────┼──────────────────┘
          │                  │                  │
          │ API Calls        │                  │
          ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                     BACKEND (FastAPI)                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │           routes_query.py (Query Engine)                │   │
│  │  /query/generate  │  /query/analytics  │  /query/sync  │   │
│  └────────┬──────────┴───────────┬─────────┴────────┬──────┘   │
│           │                      │                    │          │
│           │                      │                    │          │
│  ┌────────▼────────────┐  ┌─────▼──────────────┐   │          │
│  │ rag_sql_generator   │  │ graduation_manager │   │          │
│  │                     │  │                     │   │          │
│  │ • AI query parsing  │  │ • parse_usn_full() │◄──┘          │
│  │ • SQL generation    │  │ • get_analytics()  │              │
│  │ • Graduation rules  │  │ • enrich_data()    │              │
│  └────────┬────────────┘  └─────┬──────────────┘              │
│           │                     │                               │
│           │                     │                               │
│  ┌────────▼─────────────────────▼────────────────────────┐    │
│  │              routes_files.py (File Upload)             │    │
│  │  • _parse_usn() wrapper                               │    │
│  │  • Auto-calculate graduation on upload                │    │
│  └────────┬───────────────────────────────────────────────┘    │
│           │                                                     │
└───────────┼─────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────┐
│                   DATABASE (MySQL)                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐    │
│  │  students table                                        │    │
│  │  ┌──────────────────────────────────────────────────┐ │    │
│  │  │  usn                 VARCHAR(100) PK             │ │    │
│  │  │  name                VARCHAR(150)                │ │    │
│  │  │  admission_year      INT  ◄── STORED             │ │    │
│  │  │  current_year        INT  ◄── STORED             │ │    │
│  │  │  student_type        VARCHAR(50) ◄── STORED      │ │    │
│  │  │  estimated_semester  INT  ◄── STORED             │ │    │
│  │  │  ...                                             │ │    │
│  │  └──────────────────────────────────────────────────┘ │    │
│  │                                                        │    │
│  │  COMPUTED FIELDS (Never Stored):                     │    │
│  │  • graduation_year = admission_year + 4              │    │
│  │  • graduation_status = [ACTIVE | GRADUATED]          │    │
│  │    (calculated from current date)                    │    │
│  └────────────────────────────────────────────────────────┘    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Data Flow Diagrams

### Flow 1: File Upload with Automatic Graduation Calculation

```
┌──────────┐
│  Staff   │
│  Uploads │
│  Excel   │
└────┬─────┘
     │
     ▼
┌────────────────────────────────────────────┐
│  routes_files.py                           │
│  POST /files/upload                        │
│  POST /files/update-db/{filename}          │
└────┬───────────────────────────────────────┘
     │
     ▼
┌────────────────────────────────────────────┐
│  Parse Excel/CSV                           │
│  Extract: USN, Name, Marks, etc.           │
└────┬───────────────────────────────────────┘
     │
     ▼
┌────────────────────────────────────────────┐
│  _parse_usn(usn)                           │
│  ↓                                         │
│  graduation_manager.parse_usn_full(usn)    │
│                                            │
│  Returns:                                  │
│  • admission_batch (corrected)             │
│  • student_type (Regular/Lateral)          │
│  • current_year (1-4)                      │
│  • current_sem (1-8)                       │
│  • graduation_year (admission + 4)         │
│  • graduation_status (ACTIVE/GRADUATED)    │
└────┬───────────────────────────────────────┘
     │
     ▼
┌────────────────────────────────────────────┐
│  _upsert_student(cur, usn, data)           │
│                                            │
│  INSERT/UPDATE students SET:               │
│    admission_year = admission_batch        │
│    current_year = current_year             │
│    student_type = student_type             │
│    estimated_semester = current_sem        │
│    status = graduation_status              │
└────┬───────────────────────────────────────┘
     │
     ▼
┌────────────────────────────────────────────┐
│  MySQL Database                            │
│  Student record with graduation data ✓     │
└────────────────────────────────────────────┘
```

---

### Flow 2: Natural Language Query with Graduation Filter

```
┌──────────┐
│  User    │
│  Types   │
│  Query   │
└────┬─────┘
     │
     │ "show graduated students"
     ▼
┌────────────────────────────────────────────┐
│  routes_query.py                           │
│  POST /query/generate                      │
└────┬───────────────────────────────────────┘
     │
     ▼
┌────────────────────────────────────────────┐
│  rag_sql_generator.py                      │
│  generate_sql_query(query, role)           │
│                                            │
│  AI Understands:                           │
│  "graduated" = graduation query            │
│                                            │
│  Applies Synonym Rules:                    │
│  graduated/alumni/passed out               │
│  → WHERE YEAR(CURDATE()) >= (s.admission_year + 4)
└────┬───────────────────────────────────────┘
     │
     ▼
┌────────────────────────────────────────────┐
│  Generated SQL:                            │
│                                            │
│  SELECT s.usn, s.name, s.student_type,     │
│         s.admission_year,                  │
│         (s.admission_year + 4) AS graduation_year
│  FROM students s                           │
│  WHERE YEAR(CURDATE()) >= (s.admission_year + 4)
│  ORDER BY s.usn ASC;                       │
└────┬───────────────────────────────────────┘
     │
     ▼
┌────────────────────────────────────────────┐
│  MySQL Executes Query                      │
│  Returns: All graduated students           │
└────┬───────────────────────────────────────┘
     │
     ▼
┌────────────────────────────────────────────┐
│  Frontend Dashboard                        │
│  Displays: Table with graduated students   │
│  Columns: USN, Name, Type, Admission,      │
│           Graduation Year, Status           │
└────────────────────────────────────────────┘
```

---

### Flow 3: Analytics Dashboard with Graduation Stats

```
┌──────────┐
│  User    │
│  Opens   │
│Analytics │
└────┬─────┘
     │
     ▼
┌────────────────────────────────────────────┐
│  AnalyticsDashboard.jsx                    │
│  useEffect(() => load())                   │
└────┬───────────────────────────────────────┘
     │
     ▼
┌────────────────────────────────────────────┐
│  API Call:                                 │
│  GET /query/analytics                      │
└────┬───────────────────────────────────────┘
     │
     ▼
┌────────────────────────────────────────────┐
│  routes_query.py                           │
│  @router.get("/analytics")                 │
│                                            │
│  Calls:                                    │
│  graduation_manager.get_graduation_analytics()
└────┬───────────────────────────────────────┘
     │
     ▼
┌────────────────────────────────────────────┐
│  graduation_manager.py                     │
│  get_graduation_analytics()                │
│                                            │
│  FOR each student:                         │
│    1. Parse USN                            │
│    2. Calculate graduation data            │
│    3. Aggregate statistics                 │
│                                            │
│  Returns:                                  │
│  {                                         │
│    total_active: 850,                      │
│    total_graduated: 320,                   │
│    graduated_this_year: 95,                │
│    next_graduation_batch: 2027,            │
│    graduation_by_year: {...},              │
│    graduation_by_branch: {...},            │
│    admission_batch_distribution: {...},    │
│    student_type_distribution: {...}        │
│  }                                         │
└────┬───────────────────────────────────────┘
     │
     ▼
┌────────────────────────────────────────────┐
│  Frontend Renders:                         │
│  • Stat Cards                              │
│  • Student Type Distribution               │
│  • Graduation by Branch                    │
│  • Graduation by Year Chart                │
│  • Admission Batch Chart                   │
└────────────────────────────────────────────┘
```

---

## USN Parsing Logic Flow

```
Input: USN = "4HG24CS401"
         │
         ▼
┌────────────────────────────────────────────┐
│  Regex Parse: ^(\d)([A-Z]{2,3})(\d{2})([A-Z]{2,4})(\d{2,3})$
│                                            │
│  Captures:                                 │
│  • degree = 4                              │
│  • college_code = HG                       │
│  • usn_year_short = 24                     │
│  • branch = CS                             │
│  • roll_number = 401                       │
└────┬───────────────────────────────────────┘
     │
     ▼
┌────────────────────────────────────────────┐
│  Convert Year: usn_year = 2000 + 24 = 2024 │
└────┬───────────────────────────────────────┘
     │
     ▼
┌────────────────────────────────────────────┐
│  Check Roll Number:                        │
│  if roll_number >= 400:                    │
│      student_type = "Lateral Entry"        │
│      admission_batch = usn_year - 1 = 2023 │
│  else:                                     │
│      student_type = "Regular"              │
│      admission_batch = usn_year = 2024     │
└────┬───────────────────────────────────────┘
     │
     ▼
┌────────────────────────────────────────────┐
│  Calculate Graduation:                     │
│  graduation_year = admission_batch + 4     │
│                  = 2023 + 4                │
│                  = 2027                    │
└────┬───────────────────────────────────────┘
     │
     ▼
┌────────────────────────────────────────────┐
│  Calculate Current Position:               │
│  current_month = 8 (August)                │
│  current_year = 2026                       │
│  years_since_admission = 2026 - 2023 = 3   │
│                                            │
│  if current_month >= 7: # Odd semester     │
│      semester = 3 + (3 * 2) = 9            │
│      # Clamp to 8: semester = 8            │
│  current_year = (8 + 1) // 2 = 4           │
└────┬───────────────────────────────────────┘
     │
     ▼
┌────────────────────────────────────────────┐
│  Calculate Status:                         │
│  if 2026 >= 2027:                          │
│      status = "GRADUATED"                  │
│  else:                                     │
│      status = "ACTIVE"  ✓                  │
└────┬───────────────────────────────────────┘
     │
     ▼
┌────────────────────────────────────────────┐
│  Return Complete Data:                     │
│  {                                         │
│    degree: 4,                              │
│    college_code: "HG",                     │
│    usn_year: 2024,                         │
│    branch: "CS",                           │
│    roll_number: 401,                       │
│    student_type: "Lateral Entry",          │
│    admission_batch: 2023,  ← Corrected!    │
│    current_year: 4,                        │
│    current_sem: 8,                         │
│    graduation_year: 2027,                  │
│    graduation_status: "ACTIVE",            │
│    is_graduated: false                     │
│  }                                         │
└────────────────────────────────────────────┘
```

---

## Database Schema Relationships

```
┌─────────────────────────────────────────────────────────┐
│                   students                               │
├─────────────────────────────────────────────────────────┤
│  PK  usn                VARCHAR(100)                    │
│      name               VARCHAR(150)                    │
│      dob                DATE                            │
│      ─────────────────────────────────────────────────  │
│  ✓   admission_year     INT         ← STORED            │
│  ✓   current_year       INT         ← STORED            │
│  ✓   student_type       VARCHAR(50) ← STORED            │
│  ✓   estimated_semester INT         ← STORED            │
│      ─────────────────────────────────────────────────  │
│  🚫  graduation_year    (NOT STORED - COMPUTED)         │
│  🚫  graduation_status  (NOT STORED - COMPUTED)         │
│      ─────────────────────────────────────────────────  │
│      father_name        VARCHAR(150)                    │
│      mother_name        VARCHAR(150)                    │
│      ...                                                │
└─────────────────────────────────────────────────────────┘
            │
            │ 1:N relationship
            ▼
┌─────────────────────────────────────────────────────────┐
│                   marks                                  │
├─────────────────────────────────────────────────────────┤
│  PK  id                 INT                             │
│  FK  usn                VARCHAR(100) → students.usn     │
│      semester           INT                             │
│      sgpa               DECIMAL(4,2)                    │
│      year               INT                             │
└─────────────────────────────────────────────────────────┘
```

---

## Component Integration Map

```
┌───────────────────────────────────────────────────────────────┐
│  FRONTEND LAYER                                               │
├───────────────────────────────────────────────────────────────┤
│                                                               │
│  Dashboard.jsx ──────┐                                        │
│  (Main Page)         │                                        │
│                      │                                        │
│  AnalyticsDashboard ─┼─► API: /query/analytics               │
│  (Charts & Stats)    │   Returns: graduation_analytics       │
│                      │                                        │
│  QueryBox ───────────┼─► API: /query/generate                │
│  (NLP Search)        │   Input: "show graduated students"    │
│                      │   Returns: SQL results                │
│                      │                                        │
│  FileExplorer ───────┼─► API: /files/upload                  │
│  (Upload Excel)      │   API: /files/update-db/{filename}    │
│                      │   Triggers: Automatic graduation calc  │
│                      │                                        │
└──────────────────────┼───────────────────────────────────────┘
                       │
                       │ HTTP/JSON
                       │
┌──────────────────────▼───────────────────────────────────────┐
│  BACKEND LAYER (FastAPI)                                     │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  routes_query.py ────┐                                       │
│  • /query/generate   ├─► rag_sql_generator.py               │
│  • /query/analytics  │   (AI SQL Generation + Graduation)   │
│  • /query/sync-vtu   │                                       │
│                      │                                       │
│  routes_files.py ────┼─► graduation_manager.py              │
│  • /files/upload     │   • parse_usn_full()                 │
│  • /files/update-db  │   • get_graduation_analytics()       │
│                      │   • enrich_student_data()             │
│                      │   • filter_by_graduation_status()     │
│                      │                                       │
└──────────────────────┼──────────────────────────────────────┘
                       │
                       │ SQL
                       │
┌──────────────────────▼──────────────────────────────────────┐
│  DATABASE LAYER (MySQL)                                     │
├─────────────────────────────────────────────────────────────┤
│  • students table (with graduation fields)                  │
│  • marks table (SGPA/CGPA data)                             │
│  • schema_metadata (for AI context)                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Key Design Principles

### 1. **Single Source of Truth**
```
USN → Parse → Admission Batch → Graduation Year
                    ↑
              (Corrected for Lateral Entry)
```

### 2. **Never Store What Can Be Computed**
```
❌ DON'T STORE: graduation_year, graduation_status
✅ DO STORE: admission_year, student_type, current_year
✅ COMPUTE: graduation_year = admission_year + 4
✅ COMPUTE: status = current_year >= graduation_year ? "GRADUATED" : "ACTIVE"
```

### 3. **VTU Lateral Entry Rule**
```
Regular Student:      Lateral Entry Student:
USN: 4HG20CS032       USN: 4HG24CS401
Roll: 032 (< 400)     Roll: 401 (>= 400)
Admission: 2020       USN Year: 2024
Graduation: 2024      Admission: 2023  ← CRITICAL CORRECTION
                      Graduation: 2027
```

### 4. **Zero Maintenance Architecture**
```
┌─────────────┐     ┌──────────────┐     ┌───────────────┐
│  User Query │ ──► │ Parse USN    │ ──► │ Calculate     │
│             │     │ (from DB)    │     │ (from date)   │
└─────────────┘     └──────────────┘     └───────────────┘
                                                  │
                                                  ▼
                                          Always Accurate!
                                          No Manual Updates
```

---

**Architecture Version:** 1.0.0  
**Last Updated:** August 4, 2026  
**Status:** Production Ready ✅
