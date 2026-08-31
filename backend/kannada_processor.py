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
    'ತೋರಿಸಿ': 'show',
    'ತೋರಿ': 'show',
    'ಪ್ರದರ್ಶಿಸಿ': 'display',
    'ನೀಡಿ': 'give',
    'ಪಡೆಯಿರಿ': 'get',
    'ಹುಡುಕಿ': 'search',
    'ಪಟ್ಟಿ': 'list',
    'ತೋರ್ಪಡಿಸಿ': 'display',

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
    'ಮಾಹಿತಿ': 'information',
    'ಮಾಹಿತಿಯನ್ನು': 'information',
    'ವಿವರ': 'details',
    'ವಿವರಗಳು': 'details',
    'ಡೇಟಾ': 'data',
    'ದಾಖಲೆ': 'record',

    # Subject words
    'ವಿದ್ಯಾರ್ಥಿ': 'student',
    'ವಿದ್ಯಾರ್ಥಿಗಳು': 'students',
    'ಅವರ': 'of',          # possessive: "Manoj ಅವರ" = "of Manoj"
    'ಅವನ': 'of',
    'ಅವಳ': 'of',
    'ನ': '',              # possessive suffix, usually dropped

    # Academic
    'ಅಂಕ': 'marks',
    'ಅಂಕಗಳು': 'marks',
    'ಶ್ರೇಣಿ': 'grade',
    'ಜಿಪಿಎ': 'gpa',
    'ಸೆಮಿಸ್ಟರ್': 'semester',
    'ಸೆಮ್': 'sem',
    'ಫಲಿತಾಂಶ': 'result',
    'ಫಲಿತಾಂಶಗಳು': 'results',
    'ಶ್ರೇಯಾಂಕ': 'rank',
    'ಟಾಪ್': 'top',
    'ಅತ್ಯುತ್ತಮ': 'best',
    'ಅಕಾಡೆಮಿಕ್': 'academic',
    'ಶೈಕ್ಷಣಿಕ': 'academic',
    'ಪ್ರದರ್ಶನ': 'performance',

    # Personal
    'ವೈಯಕ್ತಿಕ': 'personal',
    'ತಂದೆ': 'father',
    'ತಾಯಿ': 'mother',
    'ಹುಟ್ಟಿದ ದಿನಾಂಕ': 'date of birth',
    'ವಿಳಾಸ': 'address',
    'ಫೋನ್': 'phone',
    'ಮೊಬೈಲ್': 'mobile',
    'ಇಮೇಲ್': 'email',
    'ರಕ್ತದ ಗುಂಪು': 'blood group',
    'ಲಿಂಗ': 'gender',

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

    # Connectors / particles (often dropped)
    'ಮತ್ತು': 'and',
    'ಅಥವಾ': 'or',
    'ಇನ್': 'in',
    'ಗೆ': '',
    'ಯಲ್ಲಿ': 'in',
    'ರಲ್ಲಿ': 'in',
    'ನಲ್ಲಿ': 'in',
    'ಆದ': 'who',
    'ಆದ': 'who',
    'ನ': '',
}

# Compile sorted by length (longest first) to prevent partial replacements
_SORTED_KW = sorted(_KANNADA_KEYWORDS.items(), key=lambda x: -len(x[0]))

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
    if lang == 'english':
        return text, 'english'

    result = text

    # Replace ordinal suffixes: "3ನೇ" → "3rd", "5ನೇ" → "5th"
    def _ordinal_replace(m: re.Match) -> str:
        n = int(m.group(1))
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n, 'th')
        return f'{n}{suffix}'
    result = _KANNADA_ORDINAL_RE.sub(_ordinal_replace, result)

    # Replace Kannada keywords (longest match first to avoid partials)
    for kn_word, en_word in _SORTED_KW:
        if kn_word in result:
            result = result.replace(kn_word, f' {en_word} ' if en_word else ' ')

    # Clean up multiple spaces
    result = re.sub(r'\s{2,}', ' ', result).strip()

    # If pure Kannada names remain (Kannada script tokens with no keywords left),
    # note them but leave them — the LLM handles LIKE '%<kannada_name>%' gracefully.

    return result, lang


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
    'academic', 'personal', 'both', 'tell',
}

# Kannada stop words (after normalization these become English, but before
# normalization we may still see them if used alone)
_STOP_WORDS_KN = {
    'ತೋರಿಸಿ', 'ಪ್ರದರ್ಶಿಸಿ', 'ನೀಡಿ', 'ಹುಡುಕಿ',
    'ಮಾಹಿತಿ', 'ವಿವರ', 'ಅಂಕ', 'ಶ್ರೇಣಿ',
    'ಸಂಪೂರ್ಣ', 'ಎಲ್ಲಾ', 'ಎಲ್ಲ', 'ಪೂರ್ಣ',
    'ವಿದ್ಯಾರ್ಥಿ', 'ವಿದ್ಯಾರ್ಥಿಗಳು', 'ಅವರ', 'ಅವನ', 'ಅವಳ',
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
        tok_lower = tok.lower().rstrip("'s")
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

    # Return joined remaining tokens as the name
    # For Kannada names, the script characters will remain
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
