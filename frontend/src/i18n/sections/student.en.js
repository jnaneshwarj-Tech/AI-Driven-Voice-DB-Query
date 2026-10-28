/**
 * English strings for the combined student detail view
 * (src/components/CombinedStudentView.jsx).
 *
 * Every value here reproduces the exact wording the component rendered before
 * the token/i18n pass, so the English screen is unchanged. Data itself — USNs,
 * names, branch codes, fee/backlog status strings, unmapped DB column names —
 * never routes through this file.
 */
export default {
  // ── Section headings ─────────────────────────────────────────────────────
  'student.personalInfo': 'Personal Information',
  'student.family': 'Family & Background',
  'student.parentsOccupation': "Parents' Occupation",
  'student.personalIdentity': 'Personal Identity',
  'student.contact': 'Contact Details',
  'student.address': 'Address',
  'student.admissionDetails': 'Admission Details',
  'student.graduationStatus': 'Graduation Status',
  'student.academicInfo': 'Academic Information',
  'student.backlogs': 'Backlogs / Arrears',
  'student.fees': 'Fee Details',

  // ── Header chips and actions ─────────────────────────────────────────────
  'student.section': 'Section:',
  'student.sem': 'Sem:',
  'student.semShort': 'Sem',
  'student.batch': 'Batch:',
  'student.grad': 'Grad:',
  'student.type': 'Type',
  'student.admissionBatch': 'Admission Batch',
  'student.graduationYear': 'Graduation Year',
  'student.editDetails': 'Edit details',
  'student.editFees': 'Edit fees',

  // ── Statuses the frontend owns (never a DB value) ────────────────────────
  'student.graduated': 'GRADUATED',
  'student.active': 'ACTIVE',
  'student.feePaid': '✓ Paid',
  'student.feeNotPaid': '✗ Not Paid',
  'student.feePartial': '~ Partial',
  'student.year': 'Year {y}',

  // ── Fees / backlogs sub-sections ─────────────────────────────────────────
  'student.loadingFees': 'Loading fees…',
  'student.loadingBacklogs': 'Loading backlogs…',
  'student.noBacklogs': '✓ No backlogs',
  'student.cleared': 'Cleared',
  'student.feeVtu': 'VTU Fees',
  'student.feePd': 'PD Fees',
  'student.feeIdp': 'IDP / Tuition Fees',
  'student.feeTuitionPaid': 'Tuition Fees Paid',
  'student.feeTuitionRemaining': 'Tuition Remaining',

  // ── Empty states ─────────────────────────────────────────────────────────
  'student.personalUnavailable': 'Personal information not available.',
  'student.academicUnavailable': 'No academic records found.',
  'student.noAcademicShort': 'No academic records',

  // ── Column labels (key = DB column, value = what staff read) ────────────
  // Columns absent from this list keep their raw field name on screen: those
  // are API/database field names and stay untranslated on purpose.
  'student.field.dob': 'Date of Birth',
  'student.field.bloodGroup': 'Blood Group',
  'student.field.aadharNo': 'Aadhar No',
  'student.field.fatherName': "Father's Name",
  'student.field.motherName': "Mother's Name",
  'student.field.fatherOccupation': "Father's Occupation",
  'student.field.motherOccupation': "Mother's Occupation",
  'student.field.parentsPhone': 'Parents Phone',
  'student.field.emergencyContact': 'Emergency Contact',
  'student.field.permanentAddress': 'Permanent Address',
  'student.field.currentAddress': 'Current Address',
  'student.field.joiningYear': 'Joining Year',
  'student.field.admissionYear': 'Admission Year',
  'student.field.yearAndBranch': 'Year & Branch',
  'student.field.currentSem': 'Current Semester',
  'student.field.areaType': 'Area Type',
  'student.field.hkStatus': 'HK / Non-HK Status',
  'student.field.quota': 'Admission Quota',
  'student.field.distanceFromCollege': 'Distance from College',
  'student.field.kannadaMedium': 'Kannada Medium',
  'student.field.physicallyHandicapped': 'Physically Handicapped',
  'student.field.snqQuota': 'SNQ Quota',
  'student.field.pinCode': 'PIN Code',
  'student.field.postOffice': 'Post Office',
  'student.field.backlogs': 'Backlogs',
  'student.field.gender': 'Gender',
  'student.field.email': 'Email',
  'student.field.phone': 'Phone',
  'student.field.guardianName': 'Guardian Name',
  'student.field.religion': 'Religion',
  'student.field.caste': 'Caste',
  'student.field.subCaste': 'Sub Caste',
  'student.field.category': 'Category',
  'student.field.village': 'Village',
  'student.field.area': 'Area',
  'student.field.region': 'Region',
  'student.field.taluk': 'Taluk',
  'student.field.district': 'District',
  'student.field.state': 'State',
  'student.field.address': 'Address',
};
