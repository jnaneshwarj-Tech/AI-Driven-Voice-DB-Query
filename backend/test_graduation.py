#!/usr/bin/env python3
"""
test_graduation.py
Quick test script for Graduation Management System
"""

from graduation_manager import parse_usn_full
from datetime import datetime


def test_usn_parsing():
    """Test USN parsing with various examples"""
    print("=" * 80)
    print("GRADUATION MANAGER - USN PARSING TESTS")
    print("=" * 80)
    print()
    
    test_cases = [
        ("4HG20CS032", "Regular student from 2020"),
        ("4HG21CS010", "Regular student from 2021"),
        ("4HG22CS055", "Regular student from 2022"),
        ("4HG23CS032", "Regular student from 2023"),
        ("4HG24CS401", "Lateral entry (2023 batch, 2024 USN)"),
        ("4HG25CS401", "Lateral entry (2024 batch, 2025 USN)"),
        ("4HG26CS401", "Lateral entry (2025 batch, 2026 USN)"),
        ("INVALID123", "Invalid USN"),
        (None, "None USN"),
    ]
    
    current_year = datetime.now().year
    print(f"Current Year: {current_year}")
    print(f"Current Month: {datetime.now().month}")
    print()
    
    for usn, description in test_cases:
        print(f"Test: {description}")
        print(f"USN: {usn}")
        
        result = parse_usn_full(usn)
        
        if result:
            print(f"✓ Parsed Successfully:")
            print(f"  Student Type: {result['student_type']}")
            print(f"  Branch: {result['branch']}")
            print(f"  Roll Number: {result['roll_number']}")
            print(f"  USN Year: {result['usn_year']}")
            print(f"  Admission Batch: {result['admission_batch']} {'(corrected for lateral)' if result['student_type'] == 'Lateral Entry' else ''}")
            print(f"  Graduation Year: {result['graduation_year']}")
            print(f"  Current Year: {result['current_year']}/4")
            print(f"  Current Semester: {result['current_sem']}/8")
            print(f"  Graduation Status: {result['graduation_status']}")
            
            # Verify graduation year calculation
            expected_grad = result['admission_batch'] + 4
            if result['graduation_year'] == expected_grad:
                print(f"  ✓ Graduation year correct: {result['admission_batch']} + 4 = {expected_grad}")
            else:
                print(f"  ✗ ERROR: Expected {expected_grad}, got {result['graduation_year']}")
        else:
            print(f"✗ Parsing Failed (Expected for invalid USNs)")
        
        print("-" * 80)
        print()


def test_graduation_status_logic():
    """Test graduation status calculation logic"""
    print("=" * 80)
    print("GRADUATION STATUS LOGIC TESTS")
    print("=" * 80)
    print()
    
    current_year = datetime.now().year
    
    # Test students who should be graduated
    print("Should be GRADUATED:")
    for year_offset in [5, 4, 3, 2]:
        grad_year = current_year - year_offset
        admission_year = grad_year - 4
        usn = f"4HG{str(admission_year)[2:]}CS032"
        result = parse_usn_full(usn)
        if result:
            status = "✓" if result['graduation_status'] == "GRADUATED" else "✗"
            print(f"  {status} {usn}: Admitted {admission_year}, Grad {grad_year} -> {result['graduation_status']}")
    
    print()
    
    # Test students who should be active
    print("Should be ACTIVE:")
    for year_offset in [-1, 0, 1, 2]:
        grad_year = current_year + year_offset
        admission_year = grad_year - 4
        usn = f"4HG{str(admission_year)[2:]}CS032"
        result = parse_usn_full(usn)
        if result:
            status = "✓" if result['graduation_status'] == "ACTIVE" else "✗"
            print(f"  {status} {usn}: Admitted {admission_year}, Grad {grad_year} -> {result['graduation_status']}")
    
    print()


def test_lateral_entry_batch_correction():
    """Test that lateral entry students get correct admission batch"""
    print("=" * 80)
    print("LATERAL ENTRY BATCH CORRECTION TEST")
    print("=" * 80)
    print()
    
    test_cases = [
        (24, 401, 2023),  # USN 2024, Roll 401 -> Admission 2023
        (25, 401, 2024),  # USN 2025, Roll 401 -> Admission 2024
        (26, 450, 2025),  # USN 2026, Roll 450 -> Admission 2025
    ]
    
    for usn_year, roll_no, expected_admission in test_cases:
        usn = f"4HG{usn_year}CS{roll_no}"
        result = parse_usn_full(usn)
        
        if result:
            status = "✓" if result['admission_batch'] == expected_admission else "✗"
            print(f"{status} {usn}:")
            print(f"   USN Year: 20{usn_year}")
            print(f"   Roll Number: {roll_no}")
            print(f"   Expected Admission: {expected_admission}")
            print(f"   Actual Admission: {result['admission_batch']}")
            print(f"   Graduation Year: {result['graduation_year']} (should be {expected_admission + 4})")
            
            if result['graduation_year'] == expected_admission + 4:
                print(f"   ✓ Graduates with {expected_admission} batch")
            else:
                print(f"   ✗ ERROR: Wrong graduation year")
        else:
            print(f"✗ Failed to parse {usn}")
        
        print()


if __name__ == "__main__":
    print()
    print("🎓 GRADUATION MANAGEMENT SYSTEM - TEST SUITE")
    print()
    
    try:
        test_usn_parsing()
        test_graduation_status_logic()
        test_lateral_entry_batch_correction()
        
        print("=" * 80)
        print("✓ ALL TESTS COMPLETED")
        print("=" * 80)
        print()
        
    except Exception as e:
        print()
        print(f"❌ TEST FAILED: {e}")
        print()
        import traceback
        traceback.print_exc()
