"""
kannada_processor.py — Kannada / English / Mixed language query processor.

Responsibilities:
  1. detect_language()       — detect if text is Kannada, English, or Mixed
  2. normalize_query()       — translate Kannada keywords → English equivalents
                               so the SAME query pipeline handles all languages
  3. extract_search_term_multilingual() — extract student name/USN from any language
  4. is_complete_profile_intent() — detect "show everything about X" in any language
  5. get_response_language() — return what language to reply in

Architecture:
  Kannada/Mixed Query
       ↓
  normalize_query()         ← replaces Kannada keywords with English synonyms
       ↓
  Existing Query Pipeline   ← unchanged; same intent detection, SQL gen, etc.

Key principle:
  We do NOT create a separate Kannada query engine.
  We translate Kannada → English equivalents so the existing engine handles it.

Database always stores English/Latin script names.
Kannada name tokens (e.g. "ಮನೋಜ್") are extracted and used as-is for
LIKE queries because LLM will handle the transliteration context.
"""

from __future__ import annotations
import re
import unicodedata

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: UNICODE RANGE DETECTION
# ─────────────────────────────────────────────────────────────────────────────

# Kannada Unicode range: U+0C80 – U+0CFF
_KANNADA_RE = re.compile(r'[\u0C80-\u0CFF]+')
_LATIN_WORD_RE = re.compile(r'[A-Za-z]{2,}')


def detect_language(text: str) -> str:
    """
    Returns 'kannada', 'english', or 'mixed'.

    Rules:
      - If text has Kannada chars but no Latin words → 'kannada'
      - If text has both Kannada chars and Latin words → 'mixed'
      - Otherwise → 'english'
    """
    if not text:
        return 'english'
    has_kannada = bool(_KANNADA_RE.search(text))
    has_latin = bool(_LATIN_WORD_RE.search(text))
    if has_kannada and has_latin:
        return 'mixed'
    if has_kannada:
        return 'kannada'
    return 'english'


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: KANNADA → ENGLISH KEYWORD MAP
# ─────────────────────────────────────────────────────────────────────────────

# Maps Kannada words/phrases → English equivalents
# Used to normalize queries so existing intent detection works unchanged.
#
# IMPORTANT: Only map structural/intent words, NOT student names.
# Student names (Kannada script) are passed through as-is for the LLM.

_KANNADA_KEYWORDS: dict[str, str] = {
    # Actions
    'ಶೋ': 'show',
    'ತೋರಿಸಿ': 'show',
    'ತೋರಿ': 'show',
    'ಪ್ರದರ್ಶಿಸಿ': 'display',
    'ನೀಡಿ': 'give',
    'ಪಡೆಯಿರಿ': 'get',
    'ಹುಡುಕಿ': 'search',
    'ಪಟ್ಟಿ': 'list',
    'ತೋರ್ಪಡಿಸಿ': 'display',
    'ತೋರಿಸಿ': 'show',

    # Complete profile phrases (highest priority - checked first)
    'ಸಂಪೂರ್ಣ ಮಾಹಿತಿಯನ್ನು': 'complete information',
    'ಸಂಪೂರ್ಣ ಮಾಹಿತಿ': 'complete information',
    'ಎಲ್ಲಾ ಮಾಹಿತಿ': 'all information',
    'ಎಲ್ಲಾ ವಿವರ': 'all details',
    'ಸಂಪೂರ್ಣ ವಿವರ': 'complete details',
    'ಸಂಪೂರ್ಣ ವಿವರಗಳು': 'complete details',
    'ಎಲ್ಲಾ ಮಾಹಿತಿಯನ್ನು': 'all information',
    'ಪೂರ್ಣ ಮಾಹಿತಿ': 'full information',
    'ಪೂರ್ಣ ವಿವರ': 'full details',
    'ಸಂಪೂರ್ಣ ಪ್ರೊಫೈಲ್': 'complete profile',

    # Information words
    'ಡೀಟೇಲ್ಸ್': 'details',
    'ಇನ್ಫರ್ಮೇಶನ್': 'information',
    'ಮಾಹಿತಿ': 'information',
    'ಮಾಹಿತಿಯನ್ನು': 'information',
    'ವಿವರ': 'details',
    'ವಿವರಗಳು': 'details',
    'ಡೇಟಾ': 'data',
    'ದಾಖಲೆ': 'record',

    # Subject words
    'ಸ್ಟೂಡೆಂಟ್': 'student',
    'ಸ್ಟುಡೆಂಟ್': 'student',
    'ವಿದ್ಯಾರ್ಥಿ': 'student',
    'ವಿದ್ಯಾರ್ಥಿಗಳು': 'students',
    'ವಿದ್ಯಾರ್ಥಿಗಳನ್ನು': 'students',
    'ಹೆಸರು': 'name',
    'ಹೆಸರಿರುವ': 'name',
    'ಅವರ': 'of',          # possessive: "Manoj ಅವರ" = "of Manoj"
    'ಅವನ': 'of',
    'ಅವಳ': 'of',

    # Academic
    'ಮಾರ್ಕ್ಸ್': 'marks',
    'ಅಂಕ': 'marks',
    'ಅಂಕಗಳು': 'marks',
    'ಶ್ರೇಣಿ': 'grade',
    'ಜಿಪಿಎ': 'gpa',
    'ಸೆಮಿಸ್ಟರ್': 'semester',
    'ಸೆಮ್': 'sem',
    'ಒಂದನೇ': '1st',
    'ಮೊದಲ': '1st',
    'ಮೊದಲನೇ': '1st',
    'ಎರಡನೇ': '2nd',
    'ಮೂರನೇ': '3rd',
    'ನಾಲ್ಕನೇ': '4th',
    'ಐದನೇ': '5th',
    'ಆರನೇ': '6th',
    'ಏಳನೇ': '7th',
    'ಎಂಟನೇ': '8th',
    'ಫಲಿತಾಂಶ': 'result',
    'ಫಲಿತಾಂಶಗಳು': 'results',
    'ಶ್ರೇಯಾಂಕ': 'rank',
    'ಟಾಪ್': 'top',
    'ಅತ್ಯುತ್ತಮ': 'best',
    'ಅಕಾಡೆಮಿಕ್': 'academic',
    'ಶೈಕ್ಷಣಿಕ': 'academic',
    'ಪ್ರದರ್ಶನ': 'performance',
    'ಲ್ಯಾಟರಲ್ ಎಂಟ್ರಿ': 'lateral entry',
    'ಲ್ಯಾಟರಲ್': 'lateral',

    # Personal
    'ವೈಯಕ್ತಿಕ': 'personal',
    'ತಂದೆ': 'father',
    'ತಾಯಿ': 'mother',
    'ವಯಸ್ಸು': 'age',
    'ವಯಸ್ಸಿನ': 'age',
    'ವರ್ಷದ': 'years old',
    'ಹುಟ್ಟಿದ ದಿನಾಂಕ': 'date of birth',
    'ವಿಳಾಸ': 'address',
    'ಫೋನ್': 'phone',
    'ಮೊಬೈಲ್': 'mobile',
    'ಇಮೇಲ್': 'email',
    'ರಕ್ತದ ಗುಂಪು': 'blood group',
    'ಲಿಂಗ': 'gender',

    # Birth / date terms
    'ಹುಟ್ಟಿದ ದಿನಾಂಕ': 'date of birth',
    'ಹುಟ್ಟಿರುವ': 'born',
    'ಹುಟ್ಟಿರುವವರ': 'born',
    'ಹುಟ್ಟಿದವರು': 'born',
    'ಹುಟ್ಟಿದ': 'born',
    'ಹುಟ್ಟು': 'born',
    'ಜನನ': 'birth',

    # Geography
    'ನಗರದ': 'urban',
    'ನಗರ': 'urban',
    'ಜಿಲ್ಲೆಯ': 'district',
    'ಜಿಲ್ಲೆ': 'district',
    'ತಾಲೂಕಿನ': 'taluk',
    'ತಾಲೂಕು': 'taluk',
    'ರಾಜ್ಯದ': 'state',
    'ರಾಜ್ಯ': 'state',
    'ಗ್ರಾಮದ': 'rural',
    'ಹಳ್ಳಿ': 'village',

    # Range prepositions
    'ರಿಂದ': 'from',
    'ಮಧ್ಯೆಯ': 'between',
    'ಮಧ್ಯೆ': 'between',
    'ವರೆಗೆ': 'to',
    'ಮಟ್ಟಿಗೆ': 'to',

    # Department/Branch
    'ಶಾಖೆ': 'branch',
    'ವಿಭಾಗ': 'department',
    'ವಿಭಾಗದ': 'department',

    # Graduation
    'ಪದವಿ': 'graduation',
    'ಪದವಿ ಪಡೆದ': 'graduated',
    'ಪದವೀಧರ': 'graduated',
    'ಡಿಗ್ರಿ': 'degree',
    'ಉತ್ತೀರ್ಣ': 'passed',
    'ಸಕ್ರಿಯ': 'active',

    # Quantifiers
    'ಎಲ್ಲಾ': 'all',
    'ಎಲ್ಲ': 'all',
    'ಎಲ್ಲಾ': 'all',
    'ಸಂಪೂರ್ಣ': 'complete',
    'ಪೂರ್ಣ': 'full',
    'ಎಷ್ಟು': 'how many',
    'ಗ್ರಾಮೀಣ': 'rural',

    # Connectors / particles (often dropped)
    'ಆಫ್': 'of',
    'ಮತ್ತು': 'and',
    'ಅಥವಾ': 'or',
    'ಇನ್': 'in',
    'ಗೆ': '',
    'ಯಲ್ಲಿ': 'in',
    'ರಲ್ಲಿ': 'in',
    'ನಲ್ಲಿ': 'in',
    'ಆದ': 'who',

    # Romanized Kannada Conversational Keywords & Particles
    'details kodu': 'details',
    'details kodi': 'details',
    'information beku': 'information',
    'info beku': 'information',
    'details beku': 'details',
    'sampoorna mahiti': 'complete information',
    'sampurna mahiti': 'complete information',
    'sampoorna mahithi': 'complete information',
    'sampoorna vivara': 'complete details',
    'poorna mahiti': 'full information',
    'ella mahiti': 'all information',
    'ella vivara': 'all details',
    'avara sampoorna': 'complete',
    'avara': 'of',
    'avar': 'of',
    'avan': 'of',
    'aval': 'of',
    'sampoorna': 'complete',
    'sampurna': 'complete',
    'poorna': 'full',
    'mahiti': 'information',
    'mahithi': 'information',
    'maahiti': 'information',
    'torisi': 'show',
    'thorisi': 'show',
    'tori': 'show',
    'thori': 'show',
    'kodu': 'give',
    'kodi': 'give',
    'kodok': 'give',
    'beku': '',
    'biku': '',
    'ge': '',
    'vivara': 'details',
    'viwara': 'details',
    'vaiyaktika': 'personal',
    'shaikshanika': 'academic',
    'yella': 'all',
    'ellaa': 'all',
    'ella': 'all',
    'vidyarthigalu': 'students',
    'vidyarthi': 'student',
    'eshtu': 'how much',
    'estu': 'how much',
    'enthu': 'how much',
    'yestu': 'how much',
    'vilasa': 'address',
    'vilaasa': 'address',
    'graameena': 'rural',
    'grameena': 'rural',
    'graameen': 'rural',
    'gramina': 'rural',
    'nagar': 'urban',
    'nagariya': 'urban',
    'ondane': '1st',
    'modalane': '1st',
    'modala': '1st',
    'eradane': '2nd',
    'moorane': '3rd',
    'moorané': '3rd',
    'murane': '3rd',
    'muru': '3',
    'nalkane': '4th',
    'aidane': '5th',
    'aarane': '6th',
    'elane': '7th',
    'yelane': '7th',
    'entane': '8th',
    'semistar': 'semester',
    'semister': 'semester',
    # Age / years (Romanized) — "21 varshada students" → "21 years old students"
    'varshada': 'years old',
    'varshadha': 'years old',
    'varshagalu': 'years',
    'varsha': 'years',
    'vayassu': 'age',
    'vayas': 'age',
    # Parent / identity terms (Romanized)
    'tande': 'father',
    'thande': 'father',
    'tandey': 'father',
    'tayi': 'mother',
    'taayi': 'mother',
    'hesaru': 'name',
    'hessaru': 'name',
    'hesarina': 'name',
    'iruva': 'having',
    'iruvа': 'having',
    'iruv': 'having',
    'rakta': 'blood',
    'rakthagumpa': 'blood group',
    # ── Student Lifecycle (spec §9) — Kannada Unicode → English ──
    'ಓದು ನಿಲ್ಲಿಸಿದ': 'discontinued studies',
    'ಓದು ನಿಲ್ಲಿಸು': 'discontinued studies',
    'ನಿಲ್ಲಿಸಿದ': 'discontinued',
    'ಕಾಲೇಜು ಬಿಟ್ಟ': 'dropout left college',
    'ಕಾಲೇಜು ಬಿಟ್ಟವರ': 'dropout left college',
    'ಬಿಟ್ಟ ವಿದ್ಯಾರ್ಥಿ': 'dropout student',
    'ಬಿಟ್ಟ': 'left',
    'ಪ್ರವೇಶ ನಿಷೇಧ': 'discontinued',
    'ವಿರಾಮ': 'discontinued',
    'ಮರು ಪ್ರವೇಶ': 'readmission',
    'ಮರುಪ್ರವೇಶ': 'readmission',
    'ಮರು ಸೇರ್ಪಡೆ': 'readmission',
    'ಮತ್ತೆ ಸೇರಿದ': 'rejoined',
    'ಮತ್ತೆ ಸೇರಿದ್ದ': 'rejoined',
    'ಮತ್ತೆ ಬಂದ': 'rejoined',
    'ಕಾಲೇಜಿಗೆ ಸೇರಿದ': 'rejoined',
    'ಕಾಲೇಜಿಗೆ ಬಂದ': 'rejoined',
    'ಕಾಲೇಜಿಗೆ': 'to college',
    'ಸೇರಿದ': 'joined',
    'ಕಾಯುತ್ತಿರುವ': 'waiting pending',
    'ಕಾಯುತಿರುವ': 'waiting pending',
    'ಕಾಯುತ್ತಿವ': 'waiting pending',
    'ಬಿಟ್ಟವರು': 'dropout',
    'ಬಿಟ್ಟವರ': 'dropout',
    'ಬಿಟ್ಟವರ್': 'dropout',
    'ದಾಖಲೆ ಇತಿಹಾಸ': 'status history',
    'ಸಂಪೂರ್ಣ ಇತಿಹಾಸ': 'complete status history',
    'ಇತಿಹಾಸ': 'history',
    # ── Student Lifecycle — Roman Kannada → English ──
    'odu nilistida': 'discontinued studies',
    'odu nilistid': 'discontinued studies',
    'nilistida': 'discontinued',
    'nilistid': 'discontinued',
    'college bitta': 'dropout left college',
    'koleju bitta': 'dropout left college',
    'bittida': 'left',
    'bitta': 'left',
    'maru pravesa': 'readmission',
    'maru pravesha': 'readmission',
    'readmission': 'readmission',
    'matte sere': 'rejoined',
    'matte join': 'rejoined',
    'matte serida': 'rejoined',
    'matte band': 'rejoined',
    'sere': 'joined',
}

# Compile sorted by length (longest first) to prevent partial replacements
_SORTED_KW = sorted(_KANNADA_KEYWORDS.items(), key=lambda x: -len(x[0]))

# Unambiguous Roman-Kannada marker words. These are never English words and never
# plausible personal names, so their presence (as a whole word) reliably indicates a
# Romanized-Kannada query even though the text contains no Kannada Unicode.
_ROMAN_KN_MARKERS = {
    'torisi', 'thorisi', 'tori', 'thori', 'mahiti', 'mahithi', 'maahiti',
    'avara', 'beku', 'biku', 'kodu', 'kodi', 'kodok', 'eshtu', 'estu', 'yestu',
    'vidyarthi', 'vidyarthigalu', 'varshada', 'varshadha', 'varshagalu', 'vayassu',
    'grameena', 'graameena', 'gramina', 'graameen', 'nagariya', 'sampoorna',
    'sampurna', 'vivara', 'viwara', 'iruva', 'hesaru', 'hessaru', 'semistar',
    'semister', 'moorane', 'shaikshanika', 'vaiyaktika', 'rakthagumpa', 'tande',
    'thande',
    # Lifecycle Roman-Kannada markers (never English words / names)
    'bitta', 'bittida', 'nilistida', 'nilistid', 'sere', 'serida', 'maru',
    'pravesa', 'pravesha', 'koleju', 'vivid', 'viva',
}
_ROMAN_KN_MARKER_RE = re.compile(
    r'\b(' + '|'.join(sorted(_ROMAN_KN_MARKERS, key=len, reverse=True)) + r')\b',
    re.I,
)


def contains_roman_kannada(text: str) -> bool:
    """True when ASCII text carries an unambiguous Romanized-Kannada marker word."""
    return bool(_ROMAN_KN_MARKER_RE.search(text or ''))


# Ordinal number suffixes in Kannada (e.g. "3ನೇ" → "3rd")
_KANNADA_ORDINAL_RE = re.compile(r'(\d+)ನೇ')

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: COMPLETE PROFILE INTENT PHRASES
# ─────────────────────────────────────────────────────────────────────────────

# English and Kannada phrases that indicate the user wants a complete profile
_COMPLETE_PROFILE_PATTERNS_EN = re.compile(
    r'\b('
    r'everything\s+about'
    r'|complete\s+information'
    r'|full\s+information'
    r'|complete\s+details'
    r'|full\s+details'
    r'|entire\s+profile'
    r'|all\s+information'
    r'|all\s+details'
    r'|both\s+academic\s+and\s+personal'
    r'|academic\s+and\s+personal'
    r'|personal\s+and\s+academic'
    r'|student\s+profile'
    r'|all\s+about'
    r'|tell\s+me\s+everything'
    r'|show\s+everything'
    r'|give\s+me\s+everything'
    r'|full\s+profile'
    r'|complete\s+profile'
    r')\b',
    re.IGNORECASE
)

# Kannada complete-profile phrases (pre-translation check)
_COMPLETE_PROFILE_PATTERNS_KN = re.compile(
    r'(ಸಂಪೂರ್ಣ\s+ಮಾಹಿತಿ'
    r'|ಎಲ್ಲಾ\s+ಮಾಹಿತಿ'
    r'|ಸಂಪೂರ್ಣ\s+ವಿವರ'
    r'|ಪೂರ್ಣ\s+ಮಾಹಿತಿ'
    r'|ಎಲ್ಲ\s+ವಿವರ'
    r'|ಸಂಪೂರ್ಣ\s+ಪ್ರೊಫೈಲ್)'
)


def is_complete_profile_intent(text: str) -> bool:
    """
    Returns True if the query intends a complete student profile.
    Checks both English and Kannada patterns.
    """
    if _COMPLETE_PROFILE_PATTERNS_KN.search(text):
        return True
    if _COMPLETE_PROFILE_PATTERNS_EN.search(text):
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4: QUERY NORMALIZATION
# ─────────────────────────────────────────────────────────────────────────────

# "Show details of <name>" phrased in Kannada word order. The head noun is
# excluded from the name group so a nameless "ವಿವರಗಳು ತೋರಿಸಿ" is not
# rewritten into a lookup of the word "details" itself.
_KN_QUALIFIER = r"(?:ಸಂಪೂರ್ಣ|ಎಲ್ಲಾ|ಎಲ್ಲ|ಪೂರ್ಣ)"
_KN_DETAIL_NOUNS = r"(?:ವಿವರಗಳು|ವಿವರ|ಮಾಹಿತಿ|ದಾಖಲೆಗಳು|ದಾಖಲೆ)"
_KN_DETAIL_VERBS = r"(?:ತೋರಿಸಿ|ಪ್ರದರ್ಶಿಸಿ|ಕೊಡಿ|ಕೊಡು|ನೀಡಿ|ಹುಡುಕಿ|ಬೇಕು|ಬೇಕೋ)"
_KN_POSSESSIVE = r"(?:ಅವರ|ಅವಳ|ಅವನ)"
# Kannada words have no ASCII word boundary, so "ಎ" of "ಎಲ್ಲಾ" would otherwise
# be a legal match start and the structural word would be split in half.
_KN_AT_START = r"(?<![\u0C80-\u0CFF])"
# The name in front of the Kannada request words is often Latin
# ("Ananya Ananya ವಿವರಗಳು ತೋರಿಸಿ"), so the name group accepts any script.
_KN_NOT_NOUN = (rf"{_KN_AT_START}(?!{_KN_QUALIFIER}|{_KN_DETAIL_NOUNS}|{_KN_POSSESSIVE}|{_KN_DETAIL_VERBS})"
                r"\S+")
_KN_DETAIL_FRAME_RE = re.compile(
    rf"(?P<who>{_KN_NOT_NOUN}(?:\s+{_KN_NOT_NOUN})*)"
    rf"(?:\s*{_KN_POSSESSIVE})?"
    rf"(?:\s*{_KN_QUALIFIER})?"
    rf"\s*(?:{_KN_AT_START}{_KN_DETAIL_NOUNS})(?![\u0C80-\u0CFF])"
    rf"(?:\s*{_KN_DETAIL_VERBS}(?![\u0C80-\u0CFF]))?"
)


def _detail_frame_replacement(match: re.Match) -> str:
    who = match.group("who").strip()
    qual = "complete " if match.group(0).count("ಸಂಪೂರ್ಣ") or \
        match.group(0).count("ಎಲ್ಲಾ") or match.group(0).count("ಪೂರ್ಣ") else ""
    return f"show {qual}details of {who}"


# The same verb-final order arrives romanised from the search box
# ("Ananya Ananya avara vivara torisi"), so it needs its own frame. The Kannada
# markers are distinctive enough that ordinary English never matches.
_KN_R_POSSESSIVE = r"avara|avar|avan|aval|adara"
_KN_R_QUALIFIER = r"sampoorna|sampurna|sampoor|poorna|purna|ella|yella|ellaa"
_KN_R_NOUN = r"vivara|viwara|vaiyaktika|mahiti|mahithi|maahiti|daakhile|details|detail|information|info|records|profile"
_KN_R_VERB = r"torisi|thorisi|tori|thori|kodu|kodi|kodok|beku|biku|huduki|nidedi"
# Staff mix scripts in one query: a Kannada-script name typed with romanised
# request words ("ಲಕ್ಷ್ಮೀ ದೇವಿ avara vivara torisi"), so the name group accepts
# either script while still refusing structural words of either spelling.
_KN_R_KN_STRUCT = rf"(?:{_KN_POSSESSIVE}|{_KN_QUALIFIER}|{_KN_DETAIL_NOUNS}|{_KN_DETAIL_VERBS})"
_KN_R_NOT_STRUCT = (rf"(?!(?:{_KN_R_POSSESSIVE}|{_KN_R_QUALIFIER}|{_KN_R_NOUN}|{_KN_R_VERB})\b)"
                    rf"(?!(?:{_KN_R_KN_STRUCT})(?:\s|$))"
                    r"(?:[A-Za-z][A-Za-z']*(?![A-Za-z'])|[\u0C80-\u0CFF]+)")
_KN_R_DETAIL_FRAME_RE = re.compile(
    rf"(?P<who>{_KN_R_NOT_STRUCT}(?:\s+{_KN_R_NOT_STRUCT})*)"
    rf"(?:\s+(?P<poss>{_KN_R_POSSESSIVE}|{_KN_POSSESSIVE}))?"
    rf"(?:\s+(?P<qual>{_KN_R_QUALIFIER}|{_KN_QUALIFIER}))?"
    rf"\s+(?P<noun>{_KN_R_NOUN})"
    rf"(?:\s+(?P<verb>{_KN_R_VERB}))?\b",
    re.I,
)


def _roman_detail_frame(match: re.Match) -> str:
    # Without a possessive or a Kannada verb the phrase is plain English
    # ("show details of Rahul"), which the engine already understands.
    if not match.group("poss") and not match.group("verb"):
        return match.group(0)
    qual = match.group("qual") or ""
    lowered = qual.lower()
    if lowered.startswith(("sam", "poo", "pur")) or qual.startswith(("ಸಂಪೂ", "ಪೂ")):
        prefix = "complete "
    else:
        prefix = "all " if qual else ""
    return f"show {prefix}details of {match.group('who').strip()}"


_KN_STRUCT_WORD_RE = re.compile(
    rf"^(?:{_KN_POSSESSIVE}|{_KN_QUALIFIER}|{_KN_DETAIL_NOUNS}|{_KN_DETAIL_VERBS})$")
_KN_R_STRUCT_WORD_RE = re.compile(
    rf"^(?:{_KN_R_POSSESSIVE}|{_KN_R_QUALIFIER}|{_KN_R_NOUN}|{_KN_R_VERB})$", re.I)


def is_structural_word(word: str) -> bool:
    """True when a lone token is a Kannada request word (ತೋರಿಸಿ, vivara, avara, …).

    Autocomplete must not fuzzy-match these against student names: "torisi" is
    closer to "Trisha" than any name the staff member could mean.
    """
    w = (word or "").strip()
    if not w:
        return False
    if w in _KANNADA_KEYWORDS or w.casefold() in _ROMAN_KN_MARKERS:
        return True
    return bool(_KN_STRUCT_WORD_RE.match(w) or _KN_R_STRUCT_WORD_RE.match(w))


def normalize_query(text: str) -> tuple[str, str]:
    """
    Normalize a Kannada/mixed/English query for the existing pipeline.

    Returns:
        (normalized_text, response_language)
        - normalized_text: query with Kannada structural words replaced by English
        - response_language: 'kannada', 'mixed', or 'english'

    Key behaviour:
      - Structural words (ತೋರಿಸಿ, ಸಂಪೂರ್ಣ, ಅಂಕ, etc.) → English equivalents
      - Student names in Kannada script are LEFT AS-IS
        (the LLM will handle them in LIKE queries naturally)
      - Ordinal numbers: "3ನೇ" → "3rd"
    """
    lang = detect_language(text)
    roman_kn = (lang == 'english') and contains_roman_kannada(text)
    if lang == 'english' and not roman_kn:
        return text, 'english'

    result = text

    result = re.sub(
        r"([\u0C80-\u0CFF]+(?:\s+[\u0C80-\u0CFF]+)*)\s+ಅವರ\s+ತಂದೆ\s+ಹೆಸರಿರುವ",
        r"students whose father name is \1",
        result,
    )

    # Kannada is verb-final: "ಮನೋಜ ಕುಮಾರ್ ಅವರ ವಿವರಗಳು ತೋರಿಸಿ" maps
    # word-for-word to "Manoj Kumar of details show", a string no English pattern
    # in the query engine recognises, so the request fell to the LLM and returned
    # other students. Reorder the "person + ಅವರ + details + verb" frame into the
    # canonical English lookup before the per-word replacements run.
    result = _KN_DETAIL_FRAME_RE.sub(_detail_frame_replacement, result)
    result = _KN_R_DETAIL_FRAME_RE.sub(_roman_detail_frame, result)

    # Replace ordinal suffixes: "3ನೇ" → "3rd", "5ನೇ" → "5th"
    def _ordinal_replace(m: re.Match) -> str:
        n = int(m.group(1))
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n, 'th')
        return f'{n}{suffix}'
    result = _KANNADA_ORDINAL_RE.sub(_ordinal_replace, result)

    # Replace Kannada keywords (longest match first to avoid partials).
    # Roman-Kannada keys are matched on word boundaries so that short tokens
    # ('ge', 'ella', …) never corrupt ordinary English words or names.
    for kn_word, en_word in _SORTED_KW:
        replacement = f' {en_word} ' if en_word else ' '
        if kn_word.isascii():
            result = re.sub(
                r'\b' + re.escape(kn_word) + r'\b',
                replacement.replace('\\', '\\\\'),
                result,
                flags=re.I,
            )
        elif kn_word in result:
            result = result.replace(kn_word, replacement)

    # Clean up multiple spaces
    result = re.sub(r'\s{2,}', ' ', result).strip()

    # Kannada case suffixes glue onto digits ("2006ರ", "2023ರ"). Strip any Kannada
    # letter run immediately after a number so the year stays machine-parseable.
    result = re.sub(r'(\d)[\u0C80-\u0CFF]+', r'\1 ', result)

    # Kannada is SOV, so the verb "born" (ಹುಟ್ಟಿರುವ) often trails its year operands.
    # Once mapped to English we may hold "... from ... between born". If a birth
    # intent carries two years, rewrite them into the canonical inclusive range the
    # query engine understands, independent of the original Kannada word order.
    if re.search(r'\bborn\b', result, re.I):
        _years = re.findall(r'\b(?:19|20)\d{2}\b', result)
        if len(_years) >= 2:
            _lo, _hi = sorted((int(_years[0]), int(_years[1])))
            rest = re.sub(r'\bborn\b|\b(?:19|20)\d{2}\b', ' ', result, flags=re.I)
            rest = re.sub(r'\b(?:from|between|and|to)\b', ' ', rest, flags=re.I)
            rest = re.sub(r'\s{2,}', ' ', rest).strip()
            result = f"born between {_lo} and {_hi} {rest}".strip()

    result = re.sub(r'\s{2,}', ' ', result).strip()

    return result, ('mixed' if roman_kn else lang)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5: SEARCH TERM EXTRACTION (MULTILINGUAL)
# ─────────────────────────────────────────────────────────────────────────────

# Stop words to ignore when extracting the target student name/USN
_STOP_WORDS_EN = {
    'show', 'give', 'me', 'display', 'list', 'get', 'find', 'fetch',
    'search', 'all', 'the', 'of', 'for', 'in', 'from', 'with', 'and',
    'or', 'by', 'about', 'student', 'students', 'marks', 'mark', 'gpa',
    'cgpa', 'sgpa', 'details', 'data', 'record', 'records', 'semester',
    'sem', 'result', 'results', 'top', 'best', 'highest', 'lowest',
    'complete', 'full', 'information', 'everything', 'entire', 'profile',
    'academic', 'personal', 'both', 'tell', 'kodu', 'kodi', 'kodok',
    'beku', 'biku', 'ge', 'kodi', 'vivara', 'viwara', 'mahithi',
}

# Kannada stop words (after normalization these become English, but before
# normalization we may still see them if used alone)
_STOP_WORDS_KN = {
    'ತೋರಿಸಿ', 'ಪ್ರದರ್ಶಿಸಿ', 'ನೀಡಿ', 'ಹುಡುಕಿ',
    'ಮಾಹಿತಿ', 'ವಿವರ', 'ಅಂಕ', 'ಶ್ರೇಣಿ',
    'ಸಂಪೂರ್ಣ', 'ಎಲ್ಲಾ', 'ಎಲ್ಲ', 'ಪೂರ್ಣ',
    'ವಿದ್ಯಾರ್ಥಿ', 'ವಿದ್ಯಾರ್ಥಿಗಳು', 'ಅವರ', 'ಅವನ', 'ಅವಳ',
    'ಕೊಡು', 'ಕೊಡಿ', 'ಬೇಕು', 'ಗೆ',
}

# USN pattern
_USN_PATTERN = re.compile(r'^[0-9][A-Za-z0-9]{4,}$')


def extract_search_term_multilingual(text: str) -> str | None:
    """
    Extract the student name or USN from a query in any language.

    Strategy:
      1. Normalize the query (Kannada → English keywords)
      2. Split into tokens
      3. Remove stop words
      4. If a USN-like token remains, return it
      5. Otherwise return remaining tokens as the name search term

    Returns None if no clear search term can be extracted.
    """
    normalized, lang = normalize_query(text)

    # Tokenize
    tokens = re.split(r'[\s,;]+', normalized.strip())

    # Filter out stop words and empty tokens
    candidate_tokens = []
    for tok in tokens:
        if not tok:
            continue
        # A trailing possessive is dropped ("Sneha's" → "sneha"), but a plain
        # word-final "s" must survive: rstrip("'s") turned "details" into
        # "detail", so the stop word was missed and the intent word leaked into
        # the extracted student name ("ಮನೋಜ ಕುಮಾರ್ details").
        tok_lower = re.sub(r"('s|s')$", "", tok.lower())
        if tok_lower in _STOP_WORDS_EN:
            continue
        if tok in _STOP_WORDS_KN:
            continue
        # Skip single characters and numbers only
        if len(tok) < 2:
            continue
        if tok.isdigit():
            continue
        candidate_tokens.append(tok)

    if not candidate_tokens:
        return None

    # Check for USN (first alphanumeric token starting with digit)
    for tok in candidate_tokens:
        if _USN_PATTERN.match(tok):
            return tok

    return ' '.join(candidate_tokens)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6: RESPONSE LANGUAGE HELPER
# ─────────────────────────────────────────────────────────────────────────────

_KANNADA_RESPONSE_INTRO = "ವಿದ್ಯಾರ್ಥಿ ಮಾಹಿತಿ"          # "Student information"
_KANNADA_NOT_FOUND      = "ಮಾಹಿತಿ ಲಭ್ಯವಿಲ್ಲ"          # "Information not available"
_KANNADA_PROFILE_HEADER = "ಸಂಪೂರ್ಣ ವಿದ್ಯಾರ್ಥಿ ಪ್ರೊಫೈಲ್"  # "Complete Student Profile"
_KANNADA_ACADEMIC       = "ಶೈಕ್ಷಣಿಕ ಮಾಹಿತಿ"             # "Academic Information"
_KANNADA_PERSONAL       = "ವೈಯಕ್ತಿಕ ಮಾಹಿತಿ"             # "Personal Information"


def get_response_labels(response_language: str) -> dict:
    """
    Return UI labels for the given response language.
    Used by the frontend to display appropriate section headers.
    """
    if response_language in ('kannada', 'mixed'):
        return {
            'profile_header': _KANNADA_PROFILE_HEADER,
            'personal_section': _KANNADA_PERSONAL,
            'academic_section': _KANNADA_ACADEMIC,
            'not_found': _KANNADA_NOT_FOUND,
            'language': response_language,
        }
    return {
        'profile_header': 'Complete Student Profile',
        'personal_section': 'Personal Information',
        'academic_section': 'Academic Information',
        'not_found': 'Information not available',
        'language': 'english',
    }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7: KANNADA-AWARE PROMPT CONTEXT
# ─────────────────────────────────────────────────────────────────────────────

def build_language_context(original_query: str, normalized_query: str, lang: str) -> str:
    """
    Build a language context string to prepend to the LLM prompt.
    Tells the LLM about the original language so it can respond appropriately.
    """
    if lang == 'english':
        return ''

    parts = [
        f'LANGUAGE CONTEXT: The user query was in {lang.upper()}.',
        f'Original query: {original_query}',
        f'Normalized to English: {normalized_query}',
    ]

    if lang in ('kannada', 'mixed'):
        parts.append(
            'RESPONSE INSTRUCTION: Generate valid SQL based on the normalized query. '
            'If the query contains a Kannada name like "ಮನೋಜ್", use LIKE queries '
            'with the Kannada script directly, or transliterate to English if obvious '
            '(e.g. ಮನೋಜ್ → Manoj). '
            'The database stores names in English/Latin script.'
        )

    return '\n'.join(parts) + '\n\n'
