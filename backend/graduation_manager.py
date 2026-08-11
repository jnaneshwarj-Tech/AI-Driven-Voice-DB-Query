"""
graduation_manager.py — Automatic Graduation Management System
Dynamically calculates Student Type, Admission Batch, Current Year, Current Semester,
Graduation Year, and Graduation Status from USN following VTU rules.

USN Format: 4HG20CS032
- 4 = Degree (4-year BE)
- HG = College Code
- 20 = USN Year
- CS = Branch
- 032 = Roll Number

Rules:
- Regular Student: Roll Number < 400
  * Admission Batch = USN Year
  * Duration = 4 years (8 semesters)
- Lateral Entry Student: Roll Number >= 400
  * Actual Admission Batch = USN Year - 1 (VTU issues new USN when joining 2nd year)
  * Duration = 3 years (6 semesters from 3rd semester)
  
Graduation Year = Admission Batch + 4 (for both types)
Graduation Status = GRADUATED if current_year >= graduation_year, else ACTIVE
"""

import re
from datetime import datetime
from typing import Optional, Dict, Any


def parse_usn_full(usn: str) -> Optional[Dict[str, Any]]:
    """
    Parse USN and calculate all graduation-related fields dynamically.
    
    Returns dict with:
        - degree: Course code (e.g., 4 for 4-year BE)
        - college_code: College identifier (e.g., HG)
        - usn_year: Year from USN (e.g., 20 for 2020)
        - branch: Department code (e.g., CS)
        - roll_number: Student roll number (e.g., 32 or 401)
        - student_type: "Regular" or "Lateral Entry"
        - admission_batch: Actual admission year (corrected for lateral)
        - current_year: Calculated academic year (1-4)
        - current_sem: Calculated current semester (1-8)
        - estimated_semester: Same as current_sem (for compatibility)
        - graduation_year: Expected year of graduation
        - graduation_status: "ACTIVE" or "GRADUATED"
        - is_graduated: Boolean for easy filtering
        
    Returns None if USN format is invalid.
    """
    if not usn:
        return None
        
    usn = str(usn).strip().upper()
    
    # VTU USN pattern: 4HG20CS032 or similar
    # Pattern: {degree}{college}{year}{branch}{roll}
    match = re.match(r'^(\d)([A-Z]{2,3})(\d{2})([A-Z]{2,4})(\d{2,3})$', usn)
    
    if not match:
        return None
    
    degree = int(match.group(1))  # 4 for 4-year BE
    college_code = match.group(2)  # HG
    usn_year_short = int(match.group(3))  # 20
    branch = match.group(4)  # CS
    roll_number = int(match.group(5))  # 032 or 401
    
    # Convert 2-digit year to 4-digit (20 → 2020)
    usn_year = 2000 + usn_year_short
    
    # Determine student type and actual admission batch
    is_lateral = roll_number >= 400
    student_type = "Lateral Entry" if is_lateral else "Regular"
    
    # CRITICAL VTU RULE: Lateral students get new USN but belong to previous batch
    # Example: 4HG24CS401 joined in 2023 batch (2nd year), gets 2024 USN
    if is_lateral:
        admission_batch = usn_year - 1
    else:
        admission_batch = usn_year
    
    # Calculate graduation year (4 years from admission for both types)
    graduation_year = admission_batch + degree
    
    # Calculate current academic position based on today's date
    now = datetime.now()
    current_calendar_year = now.year
    current_month = now.month
    
    # VTU academic year: July to June
    # Odd semester: July to December
    # Even semester: January to June
    
    # Calculate years since admission
    if current_month >= 7:  # July onwards = new academic year started
        years_since_admission = current_calendar_year - admission_batch
    else:  # Jan-June = still in previous academic year
        years_since_admission = current_calendar_year - admission_batch - 1
    
    # Calculate current semester
    # For lateral entry, they start from semester 3 (2nd year)
    if is_lateral:
        # Lateral: starts at sem 3, duration is 6 semesters (3-8)
        base_semester = 3
        if current_month >= 7:  # Odd semester
            calc_sem = base_semester + (years_since_admission * 2)
        else:  # Even semester
            calc_sem = base_semester + (years_since_admission * 2) - 1
    else:
        # Regular: starts at sem 1, duration is 8 semesters (1-8)
        if current_month >= 7:  # Odd semester
            calc_sem = (years_since_admission * 2) + 1
        else:  # Even semester
            calc_sem = years_since_admission * 2
    
    # Clamp semester to valid range
    calc_sem = max(1, min(8, calc_sem))
    
    # Calculate current year (1-4)
    current_year = (calc_sem + 1) // 2
    current_year = max(1, min(degree, current_year))
    
    # Determine graduation status dynamically (never store this)
    if current_calendar_year >= graduation_year:
        # Additional check: if it's before July of graduation year, still active
        if current_calendar_year == graduation_year and current_month < 7:
            graduation_status = "ACTIVE"
            is_graduated = False
        else:
            graduation_status = "GRADUATED"
            is_graduated = True
    else:
        graduation_status = "ACTIVE"
        is_graduated = False
    
    return {
        "degree": degree,
        "college_code": college_code,
        "usn_year": usn_year,
        "branch": branch,
        "roll_number": roll_number,
        "student_type": student_type,
        "admission_batch": admission_batch,  # Corrected admission year
        "current_year": current_year,
        "current_sem": calc_sem,
        "estimated_semester": calc_sem,  # Alias for compatibility
        "graduation_year": graduation_year,
        "graduation_status": graduation_status,
        "is_graduated": is_graduated,
    }


def get_graduation_analytics() -> Dict[str, Any]:
    """
    Calculate graduation analytics across all students.
    
    Returns:
        - total_active: Count of active students
        - total_graduated: Count of graduated students
        - graduated_this_year: Count graduated in current calendar year
        - next_graduation_batch: Year of next graduating batch
        - graduation_by_year: Dict of {year: count}
        - graduation_by_branch: Dict of {branch: {active: count, graduated: count}}
        - admission_batch_distribution: Dict of {batch: count}
        - student_type_distribution: {Regular: count, "Lateral Entry": count}
    """
    from database import db_conn
    
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT usn FROM students")
        all_students = cur.fetchall()
        cur.close()
    
    stats = {
        "total_active": 0,
        "total_graduated": 0,
        "graduated_this_year": 0,
        "next_graduation_batch": None,
        "graduation_by_year": {},
        "graduation_by_branch": {},
        "admission_batch_distribution": {},
        "student_type_distribution": {"Regular": 0, "Lateral Entry": 0},
    }
    
    current_year = datetime.now().year
    upcoming_grad_years = []
    
    for student in all_students:
        usn = student.get("usn")
        if not usn:
            continue
            
        parsed = parse_usn_full(usn)
        if not parsed:
            continue
        
        # Student type distribution
        st = parsed["student_type"]
        stats["student_type_distribution"][st] = stats["student_type_distribution"].get(st, 0) + 1
        
        # Admission batch distribution
        ab = parsed["admission_batch"]
        stats["admission_batch_distribution"][ab] = stats["admission_batch_distribution"].get(ab, 0) + 1
        
        # Graduation status
        if parsed["is_graduated"]:
            stats["total_graduated"] += 1
            if parsed["graduation_year"] == current_year:
                stats["graduated_this_year"] += 1
        else:
            stats["total_active"] += 1
            upcoming_grad_years.append(parsed["graduation_year"])
        
        # Graduation by year
        gy = parsed["graduation_year"]
        stats["graduation_by_year"][gy] = stats["graduation_by_year"].get(gy, 0) + 1
        
        # Graduation by branch
        branch = parsed["branch"]
        if branch not in stats["graduation_by_branch"]:
            stats["graduation_by_branch"][branch] = {"active": 0, "graduated": 0}
        
        if parsed["is_graduated"]:
            stats["graduation_by_branch"][branch]["graduated"] += 1
        else:
            stats["graduation_by_branch"][branch]["active"] += 1
    
    # Next graduation batch
    if upcoming_grad_years:
        stats["next_graduation_batch"] = min(upcoming_grad_years)
    
    return stats


def enrich_student_data(students: list) -> list:
    """
    Enrich student records with graduation data computed on-the-fly.
    
    Args:
        students: List of student dicts with 'usn' field
        
    Returns:
        Same list with added graduation fields
    """
    enriched = []
    
    for student in students:
        usn = student.get("usn")
        if not usn:
            enriched.append(student)
            continue
        
        parsed = parse_usn_full(usn)
        if not parsed:
            enriched.append(student)
            continue
        
        # Merge graduation data into student record
        student_enriched = {**student}
        student_enriched.update({
            "student_type": parsed["student_type"],
            "admission_batch": parsed["admission_batch"],
            "current_year": parsed["current_year"],
            "current_sem": parsed["current_sem"],
            "graduation_year": parsed["graduation_year"],
            "graduation_status": parsed["graduation_status"],
            "branch": parsed["branch"] if "branch" not in student else student["branch"],
        })
        
        enriched.append(student_enriched)
    
    return enriched


def filter_by_graduation_status(students: list, status: str) -> list:
    """
    Filter students by graduation status.
    
    Args:
        students: List of student records
        status: "ACTIVE" or "GRADUATED"
        
    Returns:
        Filtered list
    """
    filtered = []
    
    for student in students:
        usn = student.get("usn")
        if not usn:
            continue
            
        parsed = parse_usn_full(usn)
        if not parsed:
            continue
        
        if parsed["graduation_status"] == status.upper():
            filtered.append({**student, **parsed})
    
    return filtered


def filter_by_graduation_year(students: list, year: int) -> list:
    """
    Filter students by graduation year.
    
    Args:
        students: List of student records
        year: Graduation year to filter
        
    Returns:
        Filtered list with graduation data
    """
    filtered = []
    
    for student in students:
        usn = student.get("usn")
        if not usn:
            continue
            
        parsed = parse_usn_full(usn)
        if not parsed:
            continue
        
        if parsed["graduation_year"] == year:
            filtered.append({**student, **parsed})
    
    return filtered


def filter_by_admission_batch(students: list, batch: int) -> list:
    """
    Filter students by admission batch (including lateral adjustments).
    
    Args:
        students: List of student records
        batch: Admission batch year
        
    Returns:
        Filtered list including both regular and lateral students of that batch
    """
    filtered = []
    
    for student in students:
        usn = student.get("usn")
        if not usn:
            continue
            
        parsed = parse_usn_full(usn)
        if not parsed:
            continue
        
        if parsed["admission_batch"] == batch:
            filtered.append({**student, **parsed})
    
    return filtered
