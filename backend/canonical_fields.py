"""
canonical_fields.py — Central Canonical Field + Synonym Registry

ONE authoritative source of truth for field-name mapping across the
entire import pipeline. All other modules import from here.

Architecture (priority order):
  uploaded_column
    → normalize_header()
    → exact canonical match
    → exact synonym match
    → wide-format semester pattern
    → context-aware token rules  (whole-header, never bare "name" substring)
    → fuzzy match against registry (high threshold)
    → passthrough / ambiguous suggestion (never silent low-confidence guess)

Key rule:
  The COMPLETE header determines the field — NOT any single word inside it.
  "branch_name"  → branch       (NOT name)
  "father_name"  → father_name  (NOT name)
  "division_name"→ division     (NOT name)
  "domain_name"  → domain       (NOT name)
  "mother_name"  → mother_name  (NOT name)
"""

from __future__ import annotations

import re
from datetime import datetime
from difflib import SequenceMatcher

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: HEADER NORMALIZATION
# ─────────────────────────────────────────────────────────────────────────────

def normalize_header(raw: str) -> str:
    """
    Normalize a column header to lowercase-underscore form.
    Preserves all semantic tokens — does NOT strip context.

    Examples:
      "Branch Name"   → "branch_name"
      "STUDENT NAME"  → "student_name"
      "Father's Name" → "father_s_name"
      "  SGPA  "      → "sgpa"
    """
    s = str(raw).strip()
    s = re.sub(r'[^a-zA-Z0-9]+', '_', s)
    s = s.lower().strip('_')
    return s


def _is_empty(val) -> bool:
    if val is None:
        return True
    try:
        # pandas / numpy NaN
        if val != val:
            return True
    except Exception:
        pass
    s = str(val).strip()
    return s == '' or s.lower() in ('nan', 'none', 'null')


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: SYNONYM REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

SYNONYM_REGISTRY: dict[str, list[str]] = {

    "usn": [
        "usn", "student_usn", "student_usn_number",
        "university_seat_number", "university_seat_no",
        "register_number", "register_no",
        "registration_number", "registration_no",
        "student_registration_number",
        "roll_no", "roll_number",
        "reg_no", "reg_number",
        "enrollment_no", "enrollment_number",
        "student_id", "usno", "rno",
    ],

    "name": [
        "name", "student_name", "full_name", "student_full_name",
        "candidate_name", "first_name", "sname",
    ],

    "branch": [
        "branch", "branch_name", "department", "department_name",
        "dept", "dept_name", "stream", "stream_name",
        "program", "program_branch", "course",
        "branch_department", "programme", "engineering_branch",
        "course_name", "course_branch", "study_branch",
    ],

    "division": [
        "division", "division_name", "section", "section_name",
        "class", "class_section", "division_section", "class_division",
    ],

    "domain": [
        "domain", "domain_name", "specialization", "specialization_name",
        "area_of_specialization", "specialization_domain",
        "elective_domain", "project_domain",
    ],

    "semester": [
        "semester", "sem", "semester_number", "semester_no",
        "sem_no", "current_semester", "current_sem",
    ],

    "sgpa": [
        "sgpa", "sem_gpa", "semester_gpa", "gpa",
        "grade_point", "grade_point_average",
        "semester_grade_point_average",
    ],

    "cgpa": [
        "cgpa", "cum_gpa", "cumulative_gpa", "cgpa_percent",
        "cumulative_grade_point_average",
    ],

    "father_name": [
        "father_name", "father", "fathers_name", "father_s_name",
        "parent_father_name",
    ],

    "mother_name": [
        "mother_name", "mother", "mothers_name", "mother_s_name",
        "parent_mother_name",
    ],

    "father_occupation": [
        "father_occupation", "fathers_occupation", "father_s_occupation",
        "father_job", "father_profession", "father_work",
        "father_s_job", "father_s_work",
    ],

    "mother_occupation": [
        "mother_occupation", "mothers_occupation", "mother_s_occupation",
        "mother_job", "mother_profession", "mother_work",
        "mother_s_job", "mother_s_work",
    ],

    "guardian_name": [
        "guardian_name", "guardian", "parent_name", "parent_guardian_name",
    ],

    "dob": [
        "dob", "date_of_birth", "birth_date", "birthdate",
        "date_of_birth_dob", "d_o_b",
    ],

    "age": ["age", "student_age"],

    "year_of_joining": [
        "year_of_joining", "joining_year", "admission_year",
        "year_of_admission", "batch_year", "batch", "year_joined",
        "year_of_entry", "admission_batch",
    ],

    "blood_group": [
        "blood_group", "blood", "bloodgroup", "blood_type",
    ],

    "gender": ["gender", "sex"],

    "student_type": [
        "student_type", "student type", "admission_type", "entry_type",
        "lateral", "lateral_entry", "lateral entry", "le", "direct second year",
        "direct 2nd year",
    ],

    "religion": ["religion", "faith"],

    "caste": ["caste", "caste_category", "caste_name"],

    "sub_caste": ["sub_caste", "sub_caste_category", "subcaste"],

    "category": [
        "category", "sub_category", "reservation_category",
        "social_category", "community",
    ],

    "address": [
        "address", "student_address", "residential_address",
    ],
    "village": [
        "village", "native_village", "village_name", "hamlet",
        "gram", "grama", "native_place", "native", "native_gram",
        "village_town", "village_or_town",
        "place", "place_name", "student_place", "home_place",
    ],
    "taluk": [
        "taluk", "taluka", "tehsil", "sub_district", "subdistrict", "taluk_name", "tahsil", "mandal",
    ],
    "district": [
        "district", "district_name", "dist", "district_code",
    ],
    "state": [
        "state", "state_name", "province", "country_state", "state_name_1",
    ],
    "region": [
        "region", "residential_region", "district_region", "geographic_region",
        "location_region", "student_region", "geographic_area", "home_region",
    ],

    # area_type stores RURAL / URBAN classification
    "area_type": [
        "area_type", "rural_urban", "urban_rural", "rural_or_urban",
        "residence_type", "location_type", "region_type", "region_category",
        "region_rural_urban", "area_classification", "rural", "urban",
        "student_area_type", "residential_type", "locality_type",
        "area_category", "village_city", "village_or_city",
        "rural_urban_classification", "rur_urb",
        # Google Form field "Reason" contains Rural/Urban value
        "reason",
    ],

    # area = geographic locality (city/district/area name)
    "area": [
        "area", "locality", "local_area", "residential_area",
        "area_name", "location", "location_name", "city", "town",
        "city_town", "urban_area", "local_region",
    ],

    "permanent_address": [
        "permanent_address", "home_address", "native_address",
    ],
    "current_address": [
        "current_address", "local_address", "present_address", "hostel_address",
    ],

    "phone": [
        "phone", "phone_number", "mobile", "mobile_number", "mobile_no",
        "phone_no", "contact", "contact_number", "cell", "cell_number",
    ],

    "emergency_contact_number": [
        "emergency_contact_number", "emergency_contact", "emergency_contact_no",
        "emergency_phone", "emergency_phone_number", "emergency_number",
        "emergency_mobile", "emergency_mobile_number", "emergency phone",
        "emergency phone number", "emergency_contact_mobile",
        "emergency_contact_person", "kin_contact", "guardian_contact",
        "parent_emergency_contact", "emergency",
    ],

    "email": [
        "email", "email_id", "e_mail", "e_mail_id", "email_address",
        "student_email", "student_email_id", "student_e_mail_id",
        "mail", "mail_id",
    ],

    "aadhar_no": [
        "aadhar_no", "aadhar", "aadhaar", "aadhar_number", "aadhaar_number",
        "student_aadhar_no", "aadhar_card_no", "uid",
    ],

    "status": ["status", "student_status", "enrollment_status", "admission_status"],

    "current_year": [
        "current_year", "year", "academic_year", "study_year", "year_of_study",
    ],

    "year_and_branch": [
        "year_and_branch", "year_branch", "class_detail",
    ],

    "source_file": [
        "source_file", "file_name", "imported_from",
    ],

    # ── New Google Form fields (2024 batch) ───────────────────────────────────

    "father_occupation": [
        "father_occupation", "father_s_occupation", "fathers_occupation",
        "father_job", "fathers_job", "father_profession",
        "father_s_profession", "fathers_profession",
        "paternal_occupation", "parent_father_occupation",
        "father_occupation_detail", "occupation_of_father",
    ],

    "mother_occupation": [
        "mother_occupation", "mother_s_occupation", "mothers_occupation",
        "mother_job", "mothers_job", "mother_profession",
        "mother_s_profession", "mothers_profession",
        "maternal_occupation", "parent_mother_occupation",
        "mother_occupation_detail", "occupation_of_mother",
    ],

    "parents_phone": [
        "parents_phone", "parents_phone_number", "parent_phone",
        "parent_mobile", "parents_mobile", "parents_mobile_number",
        "parents_mobile_no", "parents_contact",
        "parent_contact_number", "family_phone", "guardian_phone",
        "parent_phone_no", "parents_phone_no", "parents_number",
        "parents_contact_number", "guardian_contact_number", "guardians_phone",
        "guardians_contact_number", "guardian_mobile", "guardian_phone_no",
        "abhibhataka_mahati",
    ],

    # Mother / father SPECIFIC contact numbers. Registered separately so a file
    # that carries a mother-only column is preferred over the general parent
    # contact during smart search (see intent_fields.resolve_contact).
    "mother_phone": [
        "mother_phone", "mother_s_phone", "mothers_phone", "mother_phone_number",
        "mother_mobile", "mother_s_mobile", "mothers_mobile", "mother_mobile_number",
        "mother_contact", "mother_contact_number", "mothers_contact_number",
        "mother_number", "mother_s_number", "mothers_number", "tayi_mahati",
        "thaye_phone", "ತಾಯಿ_ದೂರವಾಣಿ",
    ],

    "father_phone": [
        "father_phone", "father_s_phone", "fathers_phone", "father_phone_number",
        "father_mobile", "father_s_mobile", "fathers_mobile", "father_mobile_number",
        "father_contact", "father_contact_number", "fathers_contact_number",
        "father_number", "father_s_number", "fathers_number", "tande_mahati",
        "thande_phone", "ತಂದೆ_ದೂರವಾಣಿ",
    ],

    "hk_status": [
        "hk_status", "hk_non_hk", "hk", "non_hk",
        "hyd_karnataka", "hyderabad_karnataka", "hk_region",
        "hk_quota", "hk_category", "hk_non_hk_status",
    ],

    "quota": [
        "quota", "reservation_details", "quota_reservation_details",
        "quota_reservation", "reservation", "reservation_category_details",
        "admission_quota", "quota_type", "quota_details",
    ],

    "distance_from_college": [
        "distance_from_college", "distance", "distance_km",
        "distance_from_home_to_college_km", "distance_from_home",
        "home_college_distance", "distance_home_college",
        "distance_from_home_to_college",
    ],

    "kannada_medium": [
        "kannada_medium", "medium", "medium_of_instruction",
        "school_medium", "kannada_medium_school",
        "medium_kannada", "kannada_school",
    ],

    "physically_handicapped": [
        "physically_handicapped", "handicapped", "disabled",
        "physical_disability", "disability_status", "ph_status",
        "specially_abled", "ph", "physically_challenged",
    ],

    "pin_code": [
        "pin_code", "pincode", "postal_code", "zip_code",
        "zip", "pin", "postal_pin", "pin_no",
    ],

    "post_office": [
        "post_office", "post", "po", "postal_office",
        "post_office_name", "nearest_post_office",
    ],

    "backlogs": [
        "backlogs", "backlog", "arrears", "pending_subjects",
        "failed_subjects", "backlog_details", "subject_backlogs",
        "pending_exams", "backlogs_required_format",
        "backlog_subjects", "failed_papers",
        # Google Form long header normalizes to this
        "backlogs_required_format_subject_semester_year",
        "backlogs_required_format_subject_semester",
        "backlog_subject_semester_year",
    ],

    "snq_quota": [
        "snq_quota", "snq", "sports_news_quota",
        "snq_quota_status", "special_quota",
    ],

    # ── Fee fields (map all VTU/PD/IDP variations to canonical names) ─────────

    "fee_vtu_1": [
        "fee_vtu_1", "vtu_fees_1st_year", "vtu_fee_year1",
        "vtu_fees_1", "vtu_1st_year", "vtu_fees_year_1",
        "vtu_fees_1st",
    ],
    "fee_vtu_2": [
        "fee_vtu_2", "vtu_fees_2nd_year", "vtu_fee_year2",
        "vtu_fees_2", "vtu_2nd_year", "vtu_fees_year_2",
    ],
    "fee_vtu_3": [
        "fee_vtu_3", "vtu_fees_3rd_year", "vtu_fee_year3",
        "vtu_fees_3", "vtu_3rd_year", "vtu_fees_year_3",
    ],
    "fee_vtu_4": [
        "fee_vtu_4", "vtu_fees_4th_year", "vtu_fee_year4",
        "vtu_fees_4", "vtu_4th_year", "vtu_fees_year_4",
        "vtu_fees_4th",
    ],
    "fee_pd_1": [
        "fee_pd_1", "pd_fees_1st_year", "pd_fee_year1",
        "pd_fees_1", "pd_1st_year", "pd_fees_year_1",
    ],
    "fee_pd_2": [
        "fee_pd_2", "pd_fees_2nd_year", "pd_fee_year2",
        "pd_fees_2", "pd_2nd_year", "pd_fees_year_2",
    ],
    "fee_pd_3": [
        "fee_pd_3", "pd_fees_3rd_year", "pd_fee_year3",
        "pd_fees_3", "pd_3rd_year", "pd_fees_year_3",
    ],
    "fee_pd_4": [
        "fee_pd_4", "pd_fees_4th_year", "pd_fee_year4",
        "pd_fees_4", "pd_4th_year", "pd_fees_year_4",
    ],
    "fee_idp_1": [
        "fee_idp_1", "idp_tuition_fees_1st_year", "idp_1st_year",
        "idp_fees_1", "idp_fee_year1",
        "idp_tuition_fees_if_you_partially_paid_enter_your_amount_details_below_1st_year",
    ],
    "fee_idp_2": [
        "fee_idp_2", "idp_tuition_fees_2nd_year", "idp_2nd_year",
        "idp_fees_2", "idp_fee_year2",
        "idp_tuition_fees_if_you_partially_paid_enter_your_amount_details_below_2nd_year",
    ],
    "fee_idp_3": [
        "fee_idp_3", "idp_tuition_fees_3rd_year", "idp_3rd_year",
        "idp_fees_3", "idp_fee_year3",
        "idp_tuition_fees_if_you_partially_paid_enter_your_amount_details_below_3rd_year",
    ],
    "fee_idp_4": [
        "fee_idp_4", "idp_tuition_fees_4th_year", "idp_4th_year",
        "idp_fees_4", "idp_fee_year4",
        "idp_tuition_fees_if_you_partially_paid_enter_your_amount_details_below_4th_year",
        "idp_tuition_fees_if_your_are_not_paid_or_partially_paid_please_select_option_correctly_4th_year",
    ],
    "fee_tuition_paid": [
        "fee_tuition_paid", "tuition_fees_already_paid",
        "tuition_fess_already_paid",
        "tuition_fees_paid", "tuition_paid",
        # Google Form long header
        "tuition_fees_already_paid_it_is_applicable_for_partially_paid_students",
        "tuition_fees_already_paid_applicable_for_partially_paid_students",
        "tuition_already_paid",
    ],
    "fee_tuition_remaining": [
        "fee_tuition_remaining", "tuition_fess_remaining_amount",
        "tuition_fees_remaining_amount", "tuition_remaining",
        "remaining_fee", "fee_remaining",
    ],

    # ── CGPA alias (for "Overall CGPA" column header in forms) ──────────────
    "overall_cgpa": [
        "overall_cgpa", "cgpa_overall", "final_cgpa",
        "cumulative_cgpa", "total_cgpa",
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: CONTEXT-AWARE RULES (whole-header token logic)
# Longer / more specific prefixes win. Bare "name" alone → student name.
# ─────────────────────────────────────────────────────────────────────────────

# (token_prefix_tuple, canonical) — checked against normalized header tokens
_CONTEXT_RULES: list[tuple[tuple[str, ...], str]] = [
    # --- occupation rules must come BEFORE bare father/mother so they win ---
    (('father', 'occupation'), 'father_occupation'),
    (('fathers', 'occupation'), 'father_occupation'),
    (('father', 'job'), 'father_occupation'),
    (('father', 'profession'), 'father_occupation'),
    (('father', 'work'), 'father_occupation'),
    (('mother', 'occupation'), 'mother_occupation'),
    (('mothers', 'occupation'), 'mother_occupation'),
    (('mother', 'job'), 'mother_occupation'),
    (('mother', 'profession'), 'mother_occupation'),
    (('mother', 'work'), 'mother_occupation'),
    # --- generic parent/guardian name rules ---
    (('father',), 'father_name'),
    (('fathers',), 'father_name'),
    (('mother',), 'mother_name'),
    (('mothers',), 'mother_name'),
    (('guardian',), 'guardian_name'),
    (('branch',), 'branch'),
    (('department',), 'branch'),
    (('dept',), 'branch'),
    (('stream',), 'branch'),
    (('division',), 'division'),
    (('section',), 'division'),
    (('domain',), 'domain'),
    (('specialization',), 'domain'),
    (('student', 'name'), 'name'),
    (('full', 'name'), 'name'),
    (('candidate', 'name'), 'name'),
]

# Tokens that indicate the field is NOT just a name
_NON_NAME_TOKENS = frozenset({'occupation', 'job', 'profession', 'work', 'phone', 'number', 'contact'})


def _context_match(norm: str) -> str | None:
    """Match complete-header context. Never maps solely because 'name' is a substring."""
    tokens = [t for t in norm.split('_') if t]
    if not tokens:
        return None

    # Backlog/arrears columns arrive with long Google-Form prompts such as
    # "Backlogs (Required Formate: Subject, semester, year ...)". Any header
    # carrying a backlog token is the canonical backlogs field.
    if {'backlog', 'backlogs', 'arrears'} & set(tokens):
        return 'backlogs'

    # Bare "name" only
    if tokens == ['name']:
        return 'name'

    # Prefer longest matching prefix rule
    best = None
    best_len = 0
    for prefix, canon in _CONTEXT_RULES:
        plen = len(prefix)
        if plen > best_len and tokens[:plen] == list(prefix):
            # "..._name" or exact prefix field
            if tokens == list(prefix) or (len(tokens) > plen and tokens[-1] == 'name') or tokens == list(prefix) + ['name']:
                best = canon
                best_len = plen
            elif tokens[:plen] == list(prefix) and plen >= 1 and prefix[0] in (
                'father', 'fathers', 'mother', 'mothers', 'guardian',
                'branch', 'department', 'dept', 'stream', 'division',
                'section', 'domain', 'specialization',
            ):
                # Only map to the generic name if there are no non-name tokens
                token_set = set(tokens)
                if not token_set.intersection(_NON_NAME_TOKENS):
                    best = canon
                    best_len = plen
    return best


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4: REVERSE LOOKUP
# ─────────────────────────────────────────────────────────────────────────────

_REVERSE: dict[str, str] = {}
_CONFLICTS: list[str] = []
_ALL_SYNONYMS: list[tuple[str, str]] = []  # (synonym, canonical) for fuzzy

for _canon, _syns in SYNONYM_REGISTRY.items():
    # Skip ordinal aliases that are really wide-sem helpers stored as keys
    if re.match(r'^\d+(st|nd|rd|th)_sem_sgpa$', _canon):
        for _syn in _syns:
            # map to wide form via parse; store synonym → we'll resolve in map_column
            pass
        continue
    for _syn in _syns:
        if _syn in _REVERSE and _REVERSE[_syn] != _canon:
            _CONFLICTS.append(f"CONFLICT: '{_syn}' → both '{_REVERSE[_syn]}' and '{_canon}'")
        else:
            _REVERSE[_syn] = _canon
            _ALL_SYNONYMS.append((_syn, _canon))

# Ordinal semester SGPA aliases → wide canonical form (sem_N_sgpa)
for _n in range(1, 9):
    _ord = {1: '1st', 2: '2nd', 3: '3rd'}.get(_n, f'{_n}th')
    for _syn in (
        f'{_ord}_sem_sgpa', f'{_ord}_semester_sgpa',
        f'{_ord}_sem_gpa', f'semester_{_n}_sgpa',
    ):
        if _syn not in _REVERSE:
            _REVERSE[_syn] = f'sem_{_n}_sgpa'
            _ALL_SYNONYMS.append((_syn, f'sem_{_n}_sgpa'))

if _CONFLICTS:
    import warnings
    for _c in _CONFLICTS:
        warnings.warn(_c, stacklevel=2)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5: WIDE-FORMAT SEMESTER PATTERN
# ─────────────────────────────────────────────────────────────────────────────

_WIDE_A = re.compile(
    r'^(\d+)(?:st|nd|rd|th)?[_\s]*sem(?:ester)?[_\s]*(?P<m>cgpa|sgpa|gpa)$',
    re.IGNORECASE,
)
_WIDE_B = re.compile(
    r'^(?P<m>cgpa|sgpa|gpa)[_\s]*sem(?:ester)?[_\s]*(\d+)$',
    re.IGNORECASE,
)
_WIDE_C = re.compile(
    r'^sem(?:ester)?[_\s]*(\d+)[_\s]*(?P<m>cgpa|sgpa|gpa)$',
    re.IGNORECASE,
)
_WIDE_D = re.compile(
    r'^sem[_\s]*(\d+)[_\s]*(?P<m>cgpa|sgpa|gpa)$',
    re.IGNORECASE,
)
_WIDE_E = re.compile(
    r'^(\d+)(?:st|nd|rd|th)?[_\s]*sem(?:ester)?$',
    re.IGNORECASE,
)
_WIDE_F = re.compile(
    r'^sem(?:ester)?[_\s]*(\d+)$',
    re.IGNORECASE,
)


def parse_wide_sem_col(norm: str):
    """Return (sem_num, metric) for wide-format columns, else None."""
    for pat in (_WIDE_A, _WIDE_B, _WIDE_C, _WIDE_D):
        m = pat.match(norm)
        if m:
            grps = m.groups()
            num = next((g for g in grps if g and g.isdigit()), None)
            metric_raw = m.group('m').lower()
            metric = 'sgpa' if metric_raw in ('sgpa', 'gpa') else 'cgpa'
            if num:
                return int(num), metric
    for pat in (_WIDE_E, _WIDE_F):
        m = pat.match(norm)
        if m:
            num = m.group(1)
            if num and num.isdigit():
                return int(num), 'sgpa'
    return None


_FUZZY_THRESHOLD = 0.88


def _fuzzy_match(norm: str) -> tuple[str | None, float, list[dict]]:
    """
    Fuzzy match against all known synonyms.
    Returns (best_canonical_or_None, confidence, alternatives).
    Only auto-accepts when uniquely above threshold.
    """
    scored: dict[str, float] = {}
    for syn, canon in _ALL_SYNONYMS:
        ratio = SequenceMatcher(None, norm, syn).ratio()
        if ratio >= _FUZZY_THRESHOLD - 0.05:
            scored[canon] = max(scored.get(canon, 0.0), ratio)

    if not scored:
        return None, 0.0, []

    ranked = sorted(scored.items(), key=lambda x: -x[1])
    alternatives = [
        {'canonical': c, 'confidence': round(s, 3), 'reason': 'fuzzy synonym match'}
        for c, s in ranked[:5]
    ]
    best_c, best_s = ranked[0]
    # Ambiguous if top two are close
    if len(ranked) > 1 and (best_s - ranked[1][1]) < 0.05 and ranked[1][1] >= _FUZZY_THRESHOLD - 0.05:
        return None, best_s, alternatives
    if best_s >= _FUZZY_THRESHOLD:
        return best_c, best_s, alternatives
    return None, best_s, alternatives


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6: PUBLIC MAPPING API
# ─────────────────────────────────────────────────────────────────────────────

def map_column(raw: str) -> tuple[str, str, float, list[dict]]:
    """
    Map one raw header → canonical field.

    Returns (canonical, mapping_type, confidence, suggestions)
    mapping_type: exact|synonym|wide_sem|context|fuzzy|passthrough|ambiguous
    """
    norm = normalize_header(raw)

    # 1. Wide-format semester pattern (before synonym so sgpa_sem3 ≠ semester)
    wide = parse_wide_sem_col(norm)
    if wide:
        sem_num, metric = wide
        return f'sem_{sem_num}_{metric}', 'wide_sem', 1.0, []

    # 2. Exact reverse lookup (canonical + synonyms)
    if norm in _REVERSE:
        return _REVERSE[norm], 'synonym', 1.0, []

    # 3. Context-aware whole-header rules
    ctx = _context_match(norm)
    if ctx:
        return ctx, 'context', 0.95, []

    # 4. Fuzzy fallback
    fuzzy_c, fuzzy_s, alts = _fuzzy_match(norm)
    if fuzzy_c:
        return fuzzy_c, 'fuzzy', fuzzy_s, alts
    if alts:
        return norm, 'ambiguous', fuzzy_s, alts

    # 5. Passthrough — do not silently guess
    return norm, 'passthrough', 0.0, []


def map_columns(raw_columns: list[str]) -> dict[str, str]:
    """Map all raw headers once. Returns {raw_col: canonical_col}."""
    return {col: map_column(col)[0] for col in raw_columns}


def map_columns_detailed(raw_columns: list[str]) -> dict:
    """
    Full mapping report for UI / confirmation flows.
    """
    mapping = {}
    details = []
    ambiguous = []
    for col in raw_columns:
        canon, mtype, conf, suggestions = map_column(col)
        mapping[col] = canon
        entry = {
            'uploaded_column': col,
            'canonical_field': canon,
            'mapping_type': mtype,
            'confidence': conf,
            'suggestions': suggestions,
        }
        details.append(entry)
        if mtype == 'ambiguous':
            ambiguous.append(entry)
    return {
        'mapping': mapping,
        'details': details,
        'ambiguous': ambiguous,
        'needs_confirmation': len(ambiguous) > 0,
    }


def apply_mapping(records: list[dict], mapping: dict[str, str]) -> list[dict]:
    """
    Rename keys to canonical fields.

    CRITICAL: when multiple source columns map to the same canonical field,
    NEVER overwrite a non-empty value with an empty/None/NaN value.
    First non-empty value wins (column order preserved).
    """
    result = []
    for rec in records:
        new_rec: dict = {}
        for k, v in rec.items():
            canonical = mapping.get(k, normalize_header(k))
            if canonical not in new_rec:
                new_rec[canonical] = v
            elif _is_empty(new_rec[canonical]) and not _is_empty(v):
                new_rec[canonical] = v
            # else keep existing non-empty
        result.append(new_rec)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7: FORMAT DETECTION + UNPIVOT
# ─────────────────────────────────────────────────────────────────────────────

def detect_file_format(col_mapping: dict[str, str]) -> str:
    canonical_values = set(col_mapping.values())
    has_long = 'semester' in canonical_values and 'sgpa' in canonical_values
    has_wide = any(re.match(r'sem_\d+_(sgpa|cgpa)$', v) for v in canonical_values)
    if has_long and has_wide:
        return 'mixed'
    if has_wide:
        return 'wide'
    return 'long'


def extract_marks_from_row(mapped_row: dict) -> list[dict]:
    """
    Extract all (semester, sgpa[, cgpa]) mark tuples from one mapped row.
    Handles long-format (semester+sgpa) and wide-format (sem_N_sgpa) together.
    """
    marks: dict[int, dict] = {}

    # Wide columns
    for k, v in mapped_row.items():
        m = re.match(r'^sem_(\d+)_(sgpa|cgpa)$', str(k))
        if not m or _is_empty(v):
            continue
        sem_num = int(m.group(1))
        metric = m.group(2)
        try:
            fval = round(float(v), 2)
            if fval != fval:  # NaN
                continue
        except (ValueError, TypeError):
            continue
        marks.setdefault(sem_num, {'semester': sem_num})[metric] = fval

    # Long-format columns
    sem = mapped_row.get('semester')
    sgpa = mapped_row.get('sgpa')
    cgpa = mapped_row.get('cgpa')
    if not _is_empty(sem):
        try:
            sem_num = int(float(sem))
        except (ValueError, TypeError):
            sem_num = None
        if sem_num is not None:
            entry = marks.setdefault(sem_num, {'semester': sem_num})
            if not _is_empty(sgpa):
                try:
                    f = round(float(sgpa), 2)
                    if f == f:
                        entry['sgpa'] = f
                except (ValueError, TypeError):
                    pass
            if not _is_empty(cgpa):
                try:
                    f = round(float(cgpa), 2)
                    if f == f:
                        entry.setdefault('cgpa', f)
                except (ValueError, TypeError):
                    pass

    return [marks[s] for s in sorted(marks) if 'sgpa' in marks[s] or 'cgpa' in marks[s]]


def extract_wide_semester_rows(
    records: list[dict], col_mapping: dict[str, str]
) -> list[dict]:
    """Unpivot wide-format semester columns into long-format mark rows."""
    mapped = apply_mapping(records, col_mapping)
    rows = []
    for rec in mapped:
        usn = str(rec.get('usn', '') or '').strip() if not _is_empty(rec.get('usn')) else ''
        name = str(rec.get('name', '') or '').strip() if not _is_empty(rec.get('name')) else ''
        if not usn and not name:
            continue
        for mark in extract_marks_from_row(rec):
            row = {'usn': usn, 'name': name, **mark}
            # carry personal fields
            for k, v in rec.items():
                if k not in row and not re.match(r'^sem_\d+_(sgpa|cgpa)$', str(k)):
                    if k not in ('semester', 'sgpa', 'cgpa'):
                        row[k] = v
            rows.append(row)
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8: VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

REQUIRED_FIELDS = {'usn', 'name'}

# The import accepts the project's alphanumeric USN forms while rejecting
# placeholders such as INVALID001 and malformed identifiers before any DB work.
_USN_VALUE_RE = re.compile(r'^[0-9][A-Za-z0-9/-]{7,99}$')
_EMAIL_VALUE_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
_VALID_BRANCHES = {
    'CSE', 'CS', 'ISE', 'IT', 'ECE', 'EC', 'EEE', 'EE', 'ME', 'MECH',
    'CIVIL', 'CE', 'AIML', 'AI', 'AIDS', 'CSD', 'CSBS', 'IOT', 'ROBOTICS',
    'CHEMICAL', 'CH', 'ARCH', 'MBA', 'MCA',
    'COMPUTER SCIENCE AND ENGINEERING', 'INFORMATION SCIENCE AND ENGINEERING',
    'ELECTRONICS AND COMMUNICATION ENGINEERING', 'ELECTRICAL AND ELECTRONICS ENGINEERING',
    'MECHANICAL ENGINEERING', 'CIVIL ENGINEERING',
    'ARTIFICIAL INTELLIGENCE AND MACHINE LEARNING',
    'ARTIFICIAL INTELLIGENCE AND DATA SCIENCE',
    'COMPUTER SCIENCE AND DESIGN', 'COMPUTER SCIENCE AND BUSINESS SYSTEMS',
}

_FIELD_LABELS = {
    'usn': 'USN (Student ID)',
    'name': 'Student Name',
}

_VALID_BLOOD_GROUPS = {
    'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'
}


def validate_field_value(field: str, value) -> tuple[bool, str | None]:
    """Validate a single field without rejecting the whole student row."""
    if _is_empty(value):
        return True, None

    raw = str(value).strip()
    normalized_field = field.lower().strip()
    if normalized_field in {'usn'}:
        return _USN_VALUE_RE.fullmatch(raw) is not None, f"USN {raw!r} is invalid."
    if normalized_field in {'email'}:
        return _EMAIL_VALUE_RE.fullmatch(raw) is not None, f"Email {raw!r} is invalid."
    if normalized_field in {'branch'}:
        return raw.upper() in _VALID_BRANCHES, f"Branch {raw!r} is invalid."
    if normalized_field in {'blood_group'}:
        return raw.upper() in _VALID_BLOOD_GROUPS, f"Blood group {raw!r} is invalid."
    if normalized_field in {'phone', 'emergency_contact_number'}:
        digits = re.sub(r'\D', '', raw)
        return len(digits) >= 10 and len(digits) <= 15, f"Phone {raw!r} is invalid."
    if normalized_field in {'dob'}:
        try:
            import pandas as pd
            pd.to_datetime(raw, dayfirst=True)
            return True, None
        except Exception:
            return False, f"DOB {raw!r} is invalid."
    if normalized_field in {'semester', 'current_sem'}:
        try:
            sem = int(float(raw))
            return 1 <= sem <= 12, f"Semester {raw!r} is invalid; expected 1-12."
        except (TypeError, ValueError):
            return False, f"Semester {raw!r} is invalid; expected 1-12."
    if normalized_field in {'sgpa', 'cgpa'}:
        err = validate_sgpa_value(raw)
        return err is None, err
    if normalized_field in {'year_of_joining', 'admission_year', 'current_year'}:
        try:
            year = int(float(raw))
            return 2000 <= year <= datetime.now().year + 1, f"{field.replace('_', ' ').title()} {raw!r} is invalid."
        except (TypeError, ValueError):
            return False, f"{field.replace('_', ' ').title()} {raw!r} is invalid."
    if normalized_field.endswith('_sgpa') or normalized_field.endswith('_cgpa'):
        err = validate_sgpa_value(raw)
        return err is None, err
    return True, None


def sanitize_row_fields(row: dict) -> tuple[dict, dict[str, str]]:
    """Return a row with invalid field values cleared and a per-field error report."""
    cleaned = dict(row)
    issues: dict[str, str] = {}

    for field, value in list(cleaned.items()):
        if _is_empty(value):
            cleaned[field] = None
            continue
        if re.fullmatch(r'sem_\d+_(sgpa|cgpa)', str(field)):
            ok, err = validate_field_value(field, value)
        else:
            ok, err = validate_field_value(field, value)
        if not ok:
            cleaned[field] = None
            issues[field] = err or f"Field {field} is invalid."

    return cleaned, issues


def validate_mapped_rows(
    mapped_records: list[dict], *, allow_academic_only_usns: set[str] | None = None
) -> dict:
    """
    Validate identity-critical fields at the row level while treating non-critical
    field errors as per-field issues that do not invalidate the whole student.
    """
    valid, invalid, errors = [], [], []
    allow_academic_only_usns = allow_academic_only_usns or set()

    for idx, row in enumerate(mapped_records, start=1):
        cleaned_row, field_issues = sanitize_row_fields(row)
        row_errors = []
        available_cols = list(row.keys())
        row_usn = '' if _is_empty(cleaned_row.get('usn')) else str(cleaned_row.get('usn')).strip()
        has_academic_data = (
            not _is_empty(cleaned_row.get('sgpa'))
            or any(
                re.fullmatch(r'sem_\d+_(sgpa|cgpa)', str(field)) and not _is_empty(value)
                for field, value in cleaned_row.items()
            )
        )

        for field in REQUIRED_FIELDS:
            if field == 'name' and row_usn in allow_academic_only_usns and has_academic_data:
                continue
            val = cleaned_row.get(field)
            if _is_empty(val):
                label = _FIELD_LABELS.get(field, field)
                row_errors.append(
                    f"Row {idx}: Required field '{label}' is missing or empty. "
                    f"Available columns: {available_cols}."
                )

        usn = cleaned_row.get('usn')
        if not _is_empty(usn) and not _USN_VALUE_RE.fullmatch(str(usn).strip()):
            row_errors.append(f"Row {idx}: USN {str(usn).strip()!r} is invalid.")

        if row_errors:
            invalid.append({
                'row_index': idx,
                'row': row,
                'errors': row_errors,
                'usn': None if _is_empty(row.get('usn')) else str(row.get('usn')).strip(),
                'name': None if _is_empty(row.get('name')) else str(row.get('name')).strip(),
                'problematic_fields': [
                    f for f in REQUIRED_FIELDS if _is_empty(cleaned_row.get(f))
                ],
                'field_issues': field_issues,
            })
            errors.extend(row_errors)
        else:
            cleaned_row['_field_issues'] = field_issues
            valid.append(cleaned_row)

    return {'valid': valid, 'invalid': invalid, 'errors': errors, 'field_issues': {}}


def validate_sgpa_value(sgpa) -> str | None:
    """Return error message if SGPA invalid, else None."""
    if _is_empty(sgpa):
        return None
    try:
        f = float(sgpa)
        if f != f:
            return 'SGPA is not a number'
        if f < 0 or f > 10:
            return f'SGPA {f} out of range (0-10)'
    except (ValueError, TypeError):
        return f'SGPA value {sgpa!r} is not numeric'
    return None
