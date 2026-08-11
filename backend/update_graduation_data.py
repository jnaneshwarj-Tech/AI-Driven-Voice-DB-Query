#!/usr/bin/env python3
"""
update_graduation_data.py
One-time migration script to update all existing students with graduation data.
Run this after deploying the Graduation Management System.

Usage:
    python update_graduation_data.py
"""

from database import db_conn, write_audit_log
from graduation_manager import parse_usn_full
from routes_undo import create_undo_snapshot, finalize_undo_snapshot
import sys


def update_all_students():
    """
    Iterate through all students and update their graduation-related fields
    based on USN parsing.
    """
    print("=" * 80)
    print("GRADUATION DATA MIGRATION")
    print("=" * 80)
    print()
    
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        
        # Get all students
        cur.execute("SELECT usn FROM students")
        students = cur.fetchall()
        
        total = len(students)
        affected_usns = [s['usn'] for s in students if s.get('usn')]
        updated = 0
        skipped = 0
        errors = []
        
        print(f"Found {total} students to process...")
        print()
        
        conn.autocommit = False
        conn.start_transaction()
        undo_token = create_undo_snapshot(
            "SEMESTER_UPDATE", affected_usns, "system:graduation-migration",
            "Graduation data migration", conn=conn
        ) if affected_usns else ""
        try:
            for idx, student in enumerate(students, 1):
                usn = student.get("usn")
            
                if not usn:
                    skipped += 1
                    continue
            
            # Parse USN to get graduation data
                usn_data = parse_usn_full(usn)
            
                if not usn_data:
                    skipped += 1
                    errors.append(f"Could not parse USN: {usn}")
                    continue
            
            # Update student record
                try:
                    cur.execute(
                    """UPDATE students 
                       SET admission_year = %s,
                           current_year = %s,
                           student_type = %s,
                           estimated_semester = %s,
                           current_sem = %s,
                           status = %s
                       WHERE usn = %s""",
                    (
                        usn_data['admission_batch'],
                        usn_data['current_year'],
                        usn_data['student_type'],
                        usn_data['current_sem'],
                        usn_data['current_sem'],
                        usn_data['graduation_status'],
                        usn
                    )
                    )
                    updated += 1
                
                # Progress indicator
                    if idx % 50 == 0 or idx == total:
                        print(f"Progress: {idx}/{total} ({(idx/total)*100:.1f}%)")
                
                except Exception as e:
                    errors.append(f"Error updating {usn}: {str(e)}")
                    skipped += 1
        
            if undo_token:
                finalize_undo_snapshot(undo_token, affected_usns, conn)
            cur.execute(
                "INSERT INTO audit_log (username, role, action, target_table, target_id, summary, success) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                ("system:graduation-migration", "Staff", "UPDATED", "students", "bulk",
                 f"Graduation data migration updated {updated} student(s).", 1),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
    
    print()
    print("=" * 80)
    print("MIGRATION COMPLETE")
    print("=" * 80)
    print(f"Total Students: {total}")
    print(f"✓ Updated: {updated}")
    print(f"✗ Skipped: {skipped}")
    print()
    
    if errors:
        print(f"Errors encountered: {len(errors)}")
        print()
        for error in errors[:10]:  # Show first 10 errors
            print(f"  • {error}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more errors")
        print()
    
    return updated, skipped, errors, undo_token


def verify_graduation_data():
    """
    Verify that graduation data was correctly applied.
    """
    print("=" * 80)
    print("VERIFICATION")
    print("=" * 80)
    print()
    
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        
        # Check graduation status distribution
        cur.execute(
            """SELECT status, COUNT(*) as count 
               FROM students 
               GROUP BY status"""
        )
        status_dist = cur.fetchall()
        
        print("Graduation Status Distribution:")
        for row in status_dist:
            print(f"  {row['status']}: {row['count']} students")
        print()
        
        # Check student type distribution
        cur.execute(
            """SELECT student_type, COUNT(*) as count 
               FROM students 
               WHERE student_type IS NOT NULL
               GROUP BY student_type"""
        )
        type_dist = cur.fetchall()
        
        print("Student Type Distribution:")
        for row in type_dist:
            print(f"  {row['student_type']}: {row['count']} students")
        print()
        
        # Sample records
        cur.execute(
            """SELECT usn, name, student_type, admission_year, current_year, 
                      current_sem, status
               FROM students 
               WHERE admission_year IS NOT NULL
               ORDER BY usn ASC
               LIMIT 5"""
        )
        samples = cur.fetchall()
        
        print("Sample Updated Records:")
        print("-" * 80)
        for s in samples:
            grad_year = s['admission_year'] + 4 if s['admission_year'] else None
            print(f"USN: {s['usn']}")
            print(f"  Name: {s['name']}")
            print(f"  Type: {s['student_type']}")
            print(f"  Admission Batch: {s['admission_year']}")
            print(f"  Graduation Year: {grad_year}")
            print(f"  Current Year/Sem: {s['current_year']}/{s['current_sem']}")
            print(f"  Status: {s['status']}")
            print()
        
        cur.close()


if __name__ == "__main__":
    print()
    print("🎓 GRADUATION MANAGEMENT SYSTEM - DATA MIGRATION")
    print()
    print("This script will update all existing student records with:")
    print("  • Corrected admission batch (including lateral entry adjustments)")
    print("  • Student type (Regular / Lateral Entry)")
    print("  • Current year and semester")
    print("  • Graduation year (calculated)")
    print("  • Graduation status (ACTIVE / GRADUATED)")
    print()
    
    response = input("Continue? [y/N]: ").strip().lower()
    
    if response != 'y':
        print("Migration cancelled.")
        sys.exit(0)
    
    print()
    
    try:
        updated, skipped, errors, undo_token = update_all_students()
        if undo_token:
            print(f"Undo token: {undo_token}")
        print()
        verify_graduation_data()
        
        if errors:
            sys.exit(1)
        else:
            print("✓ Migration completed successfully!")
            print()
            sys.exit(0)
            
    except Exception as e:
        print()
        print(f"❌ FATAL ERROR: {e}")
        print()
        import traceback
        traceback.print_exc()
        sys.exit(1)
