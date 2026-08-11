# 🎓 Automatic Graduation Management System

## Overview
Fully automatic graduation tracking system that intelligently determines Student Type, Admission Batch, Current Year, Current Semester, Graduation Year, and Graduation Status directly from the USN following VTU rules.

**Key Feature:** All graduation data is calculated dynamically from USN and current date. No manual updates required—the system automatically updates every year.

---

## 📋 Table of Contents
1. [USN Parsing Rules](#usn-parsing-rules)
2. [Student Types](#student-types)
3. [Graduation Calculation](#graduation-calculation)
4. [Natural Language Queries](#natural-language-queries)
5. [Dashboard Analytics](#dashboard-analytics)
6. [Reports & Exports](#reports--exports)
7. [API Endpoints](#api-endpoints)
8. [Database Schema](#database-schema)
9. [Migration Guide](#migration-guide)
10. [Testing Examples](#testing-examples)

---

## 🔍 USN Parsing Rules

### USN Format
```
4HG20CS032
│││││││└── Roll Number (032)
││││││└─── Branch Code (CS = Computer Science)
│││││└──── USN Year (20 = 2020)
││││└───── College Code (HG)
│││└────── Degree Type (4 = 4-year BE)
```

### Components
- **Degree**: Course duration (4 for 4-year BE)
- **College Code**: Institution identifier (e.g., HG, KG, etc.)
- **USN Year**: 2-digit year embedded in USN
- **Branch**: Department code (CS, EC, ME, CV, etc.)
- **Roll Number**: Student identifier within batch

---

## 👥 Student Types

### Regular Students
- **Criteria**: Roll Number < 400
- **Admission Batch**: USN Year
- **Duration**: 4 years (8 semesters)
- **Starting Semester**: 1

**Examples:**
```
USN: 4HG20CS032
- Roll Number: 32 (< 400) → Regular Student
- USN Year: 2020
- Admission Batch: 2020
- Graduation Year: 2020 + 4 = 2024
```

```
USN: 4HG23CS010
- Roll Number: 10 (< 400) → Regular Student
- Admission Batch: 2023
- Graduation Year: 2027
```

### Lateral Entry Students
- **Criteria**: Roll Number >= 400
- **Admission Batch**: USN Year - 1 (Critical VTU Rule!)
- **Duration**: 3 years (6 semesters from semester 3)
- **Starting Semester**: 3

**VTU Rule Explanation:**
When students join directly into 2nd year (lateral entry), VTU issues a NEW USN with the CURRENT year. However, they academically belong to the PREVIOUS admission batch.

**Examples:**
```
USN: 4HG24CS401
- Roll Number: 401 (>= 400) → Lateral Entry
- USN Year: 2024
- Actual Admission Batch: 2024 - 1 = 2023
- Joined 2nd year in 2024, but belongs to 2023 batch
- Graduation Year: 2023 + 4 = 2027 (same as 2023 regular batch)
```

```
USN: 4HG25CS401
- Admission Batch: 2025 - 1 = 2024
- Graduation Year: 2028
```

---

## 🎓 Graduation Calculation

### Graduation Year Formula
```
Graduation Year = Admission Batch + 4
```
Applies to BOTH regular and lateral entry students.

### Graduation Status
**Dynamically calculated—never permanently stored:**

```python
if current_calendar_year >= graduation_year:
    if current_calendar_year == graduation_year and current_month < 7:
        status = "ACTIVE"  # Still studying (before July)
    else:
        status = "GRADUATED"
else:
    status = "ACTIVE"
```

**Logic:**
- Students graduate in June/July
- If current year > graduation year → GRADUATED
- If current year == graduation year AND month >= July → GRADUATED
- Otherwise → ACTIVE

### Current Semester Calculation
Based on VTU academic calendar:
- **Odd Semesters**: July to December
- **Even Semesters**: January to June

**For Regular Students:**
```python
years_since_admission = current_year - admission_batch
if current_month >= 7:  # Odd semester
    semester = (years_since_admission * 2) + 1
else:  # Even semester
    semester = years_since_admission * 2
```

**For Lateral Entry Students:**
```python
# Start from semester 3
base_semester = 3
if current_month >= 7:  # Odd semester
    semester = base_semester + (years_since_admission * 2)
else:  # Even semester
    semester = base_semester + (years_since_admission * 2) - 1
```

---

## 💬 Natural Language Queries

The AI/NLP engine understands various ways to ask about graduation:

### Query Categories

#### 1. Graduated Students
```
✓ Show graduated students
✓ Show graduates
✓ Show alumni
✓ Passed out students
✓ Completed students
✓ Graduation list
✓ Who graduated
✓ Students who completed degree
```

#### 2. Active Students
```
✓ Show active students
✓ Current students
✓ Enrolled students
✓ Who is studying
✓ Students still studying
```

#### 3. Graduation Year Filtering
```
✓ Show 2024 graduates
✓ Graduated in 2024
✓ 2024 graduation list
✓ Show 2025 graduates
✓ Next year graduates
```

#### 4. Admission Batch Filtering
```
✓ Show 2023 admission batch
✓ Students admitted in 2023
✓ 2023 batch students
✓ Show 2022 admission
```

#### 5. Student Type Filtering
```
✓ Show lateral entry students
✓ Show regular students
✓ Lateral students only
✓ Direct admission students
```

#### 6. Combined Queries
```
✓ Show graduated Computer Science students
✓ 2024 graduates from CS department
✓ Active lateral entry students
✓ Graduated students of 2023 admission batch
✓ Show CSE graduates with CGPA > 8
```

### Generated SQL Examples

**Query:** "Show graduated students"
```sql
SELECT s.usn, s.name, s.student_type, s.admission_year, 
       (s.admission_year + 4) AS graduation_year
FROM students s
WHERE YEAR(CURDATE()) >= (s.admission_year + 4)
ORDER BY s.usn ASC;
```

**Query:** "Show 2024 graduates"
```sql
SELECT s.usn, s.name, s.student_type, s.admission_year, 
       (s.admission_year + 4) AS graduation_year
FROM students s
WHERE (s.admission_year + 4) = 2024
ORDER BY s.usn ASC;
```

**Query:** "Show 2023 admission batch"
```sql
SELECT s.usn, s.name, s.student_type, s.admission_year, 
       s.current_year
FROM students s
WHERE s.admission_year = 2023
ORDER BY s.usn ASC;
```

**Important:** Includes BOTH regular 2023 students (USN: 4HG23CS0XX) AND lateral students (USN: 4HG24CS4XX) since both belong to 2023 admission batch.

---

## 📊 Dashboard Analytics

### New Graduation Analytics Section

#### Summary Cards
1. **Total Active Students**: Count of currently enrolled students
2. **Total Graduated Students**: Count of alumni
3. **Graduated This Year**: Students who graduated in current calendar year
4. **Next Graduation Batch**: Upcoming graduation year

#### Charts & Visualizations

**1. Student Type Distribution**
- Regular Students count
- Lateral Entry Students count

**2. Graduation Status by Branch**
- Active vs Graduated breakdown per department
- CS, EC, ME, CV, etc.

**3. Graduation Distribution by Year**
- Bar chart showing student count per graduation year
- Helps visualize incoming graduation batches

**4. Admission Batch Distribution**
- Bar chart showing students per admission batch
- Identifies batch sizes over years

---

## 📄 Reports & Exports

All export formats (PDF, Excel, CSV) now include:

### Additional Fields
- **Student Type**: Regular / Lateral Entry
- **Admission Batch**: Corrected admission year
- **Current Year**: 1-4
- **Current Semester**: 1-8
- **Graduation Year**: Calculated as admission_batch + 4
- **Graduation Status**: ACTIVE / GRADUATED

### Export Locations
- **Dashboard Reports**: Include graduation data in student listings
- **PDF Reports**: Graduation fields in header section
- **Excel Exports**: Dedicated columns for graduation data
- **CSV Exports**: Graduation metadata section

---

## 🔌 API Endpoints

### Get Graduation Analytics
```http
GET /api/query/analytics
```

**Response:**
```json
{
  "graduation_analytics": {
    "total_active": 850,
    "total_graduated": 320,
    "graduated_this_year": 95,
    "next_graduation_batch": 2027,
    "graduation_by_year": {
      "2024": 105,
      "2025": 110,
      "2026": 98,
      "2027": 102
    },
    "graduation_by_branch": {
      "CS": {"active": 200, "graduated": 80},
      "EC": {"active": 180, "graduated": 75},
      "ME": {"active": 150, "graduated": 60}
    },
    "admission_batch_distribution": {
      "2020": 105,
      "2021": 110,
      "2022": 108,
      "2023": 102,
      "2024": 95
    },
    "student_type_distribution": {
      "Regular": 780,
      "Lateral Entry": 70
    }
  }
}
```

### VTU Semester Sync
```http
POST /api/query/sync-vtu
```

Bulk updates all students with latest graduation data based on current date.

**Response:**
```json
{
  "success": true,
  "message": "VTU Sync complete. Updated 850 students.",
  "restore_tokens": [...],
  "undo_available": true
}
```

---

## 🗄️ Database Schema

### Students Table Updates
```sql
ALTER TABLE students ADD COLUMN admission_year INT;
ALTER TABLE students ADD COLUMN current_year INT;
ALTER TABLE students ADD COLUMN student_type VARCHAR(50);
ALTER TABLE students ADD COLUMN estimated_semester INT;
```

**Note:** `graduation_year` and `graduation_status` are NEVER stored—always calculated dynamically.

### Computed Fields
```sql
-- Graduation Year (computed)
(admission_year + 4) AS graduation_year

-- Graduation Status (computed)
CASE 
  WHEN YEAR(CURDATE()) >= (admission_year + 4) THEN 'GRADUATED'
  ELSE 'ACTIVE'
END AS graduation_status
```

---

## 🚀 Migration Guide

### Step 1: Deploy Code
1. Copy new files:
   - `backend/graduation_manager.py`
   - `backend/update_graduation_data.py`

2. Updated files:
   - `backend/routes_files.py`
   - `backend/routes_query.py`
   - `backend/rag_sql_generator.py`
   - `backend/database.py`
   - `frontend/src/components/AnalyticsDashboard.jsx`

### Step 2: Update Database Schema
```bash
# Backend will auto-create columns on startup
python backend/database.py
```

### Step 3: Migrate Existing Data
```bash
cd backend
python update_graduation_data.py
```

This script will:
- Parse USN for all existing students
- Calculate admission batch (with lateral adjustments)
- Set student type (Regular / Lateral Entry)
- Calculate current year and semester
- Set graduation status

### Step 4: Verify Migration
```bash
# Check sample records
python -c "
from database import db_conn
with db_conn() as conn:
    cur = conn.cursor(dictionary=True)
    cur.execute('SELECT usn, name, student_type, admission_year, current_year, status FROM students LIMIT 5')
    for row in cur.fetchall():
        print(row)
"
```

### Step 5: Test Queries
Try these queries in the dashboard:
- "Show graduated students"
- "Show 2024 graduates"
- "Show active students"
- "Show 2023 admission batch"

---

## 🧪 Testing Examples

### Test Case 1: Regular Student
```python
from graduation_manager import parse_usn_full

result = parse_usn_full("4HG20CS032")
# Expected:
{
    'student_type': 'Regular',
    'admission_batch': 2020,
    'graduation_year': 2024,
    'graduation_status': 'GRADUATED',  # If current year >= 2024
    'current_year': 4,  # or 5+ if overstaying
    'current_sem': 8
}
```

### Test Case 2: Lateral Entry Student
```python
result = parse_usn_full("4HG24CS401")
# Expected:
{
    'student_type': 'Lateral Entry',
    'admission_batch': 2023,  # Note: 2024 - 1
    'graduation_year': 2027,
    'graduation_status': 'ACTIVE',
    'current_year': 2,
    'current_sem': 4
}
```

### Test Case 3: Edge Cases
```python
# Invalid USN
result = parse_usn_full("INVALID")
# Returns: None

# Missing USN
result = parse_usn_full(None)
# Returns: None

# Temporary USN
result = parse_usn_full("AUTO_MANOJJR123")
# Returns: None (auto-generated USNs don't follow VTU pattern)
```

---

## ⚠️ Important Notes

### Do NOT Store Graduation Status
The `status` field in the students table should reflect graduation status but is recalculated on every query. Never trust stored status—always compute from admission_year.

### Lateral Entry Admission Batch
**Critical:** Lateral entry students' admission batch is USN year - 1. This ensures they graduate with their actual batch, not the year they received their USN.

### Automatic Updates
The system automatically updates:
- ✅ Current semester (based on month)
- ✅ Current year (based on semesters elapsed)
- ✅ Graduation status (based on current date vs graduation year)

No manual intervention required—runs on each query.

### Performance
- USN parsing is lightweight (regex + date math)
- Graduation analytics cached for 5 minutes
- Batch operations use efficient SQL
- No performance impact on normal queries

---

## 🛠️ Troubleshooting

### Issue: Graduation status not updating
**Solution:** Graduation status is calculated dynamically. Check if admission_year is set correctly.

### Issue: Lateral students showing wrong graduation year
**Solution:** Verify admission_batch = usn_year - 1. Run migration script again.

### Issue: "Show 2023 admission batch" missing lateral students
**Solution:** Ensure SQL filters by admission_year (not USN year). RAG generator handles this automatically.

### Issue: Analytics not showing graduation data
**Solution:** Check that `get_graduation_analytics()` is called in `/api/query/analytics` endpoint.

---

## 📈 Future Enhancements

Potential additions (not in current implementation):
- Placement tracking linked to graduation year
- Alumni database with graduation year indexing
- Automatic email notifications for upcoming graduations
- Graduation certificate generation
- Historical graduation trends analysis

---

## 📚 References

- **VTU Academic Regulations**: 4-year BE program structure
- **VTU USN Format**: Official USN generation rules
- **VTU Lateral Entry**: Direct admission to 2nd year policy

---

## ✅ Checklist

Before marking as complete:
- [ ] Backend graduation_manager.py deployed
- [ ] Database columns created
- [ ] Existing data migrated
- [ ] Analytics dashboard shows graduation stats
- [ ] Natural language queries working ("show graduates")
- [ ] Export formats include graduation fields
- [ ] VTU sync endpoint functional
- [ ] Documentation reviewed
- [ ] Test cases verified

---

**Version:** 1.0.0  
**Last Updated:** August 4, 2026  
**Status:** Production Ready ✅
