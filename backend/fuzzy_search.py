"""
fuzzy_search.py — AI Fuzzy Search & NLP Matching (v3 — Live Search Edition)

7-Layer matching engine for intelligent live typing suggestions:
  1. Exact Match
  2. Prefix Match (any token)
  3. Substring Match
  4. Phonetic Match (Soundex + Double Metaphone)
  5. Trigram Similarity
  6. Levenshtein / Jaro-Winkler
  7. Token-level fuzzy (handles "sundrsh" → "sudarsh")

Live search rules:
  - NEVER return empty for partial inputs ≥ 2 chars
  - Always return top-N closest matches sorted by confidence
  - Only show "no match" when user explicitly submits AND score < 0.30
"""
from database import db_conn
import re
from difflib import SequenceMatcher
import unicodedata


# ── Optional libraries ────────────────────────────────────────────────────────
try:
    import jellyfish
    _HAS_JELLYFISH = True
except ImportError:
    jellyfish = None
    _HAS_JELLYFISH = False


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 1 — Levenshtein distance
# ─────────────────────────────────────────────────────────────────────────────

def _levenshtein(a: str, b: str) -> int:
    a, b = a.lower().strip(), b.lower().strip()
    if a == b: return 0
    if not a: return len(b)
    if not b: return len(a)
    if len(a) < len(b): a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(prev[j] + (ca != cb), prev[j+1] + 1, curr[j] + 1))
        prev = curr
    return prev[-1]


def _lev_sim(a: str, b: str) -> float:
    """Levenshtein similarity 0.0–1.0."""
    ml = max(len(a), len(b))
    if ml == 0: return 1.0
    return 1.0 - _levenshtein(a, b) / ml


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 2 — Soundex phonetic encoder
# ─────────────────────────────────────────────────────────────────────────────

_SOUNDEX_MAP = {
    'B': '1', 'F': '1', 'P': '1', 'V': '1',
    'C': '2', 'G': '2', 'J': '2', 'K': '2', 'Q': '2', 'S': '2', 'X': '2', 'Z': '2',
    'D': '3', 'T': '3',
    'L': '4',
    'M': '5', 'N': '5',
    'R': '6',
}

def _soundex(s: str) -> str:
    s = re.sub(r'[^A-Za-z]', '', s).upper()
    if not s: return '0000'
    first = s[0]
    coded = first
    prev_code = _SOUNDEX_MAP.get(first, '0')
    for ch in s[1:]:
        code = _SOUNDEX_MAP.get(ch, '0')
        if code != '0' and code != prev_code:
            coded += code
        prev_code = code
        if len(coded) == 4:
            break
    return coded.ljust(4, '0')


def _double_metaphone(s: str) -> str:
    if _HAS_JELLYFISH:
        try:
            return jellyfish.metaphone(s)
        except Exception:
            pass
    return ''


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 3 — Trigram similarity
# ─────────────────────────────────────────────────────────────────────────────

def _trigrams(s: str) -> set:
    s = f'  {s}  '
    return {s[i:i+3] for i in range(len(s) - 2)}


def _trigram_sim(a: str, b: str) -> float:
    ta, tb = _trigrams(a), _trigrams(b)
    if not ta or not tb: return 0.0
    return 2.0 * len(ta & tb) / (len(ta) + len(tb))


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 4 — Jaro-Winkler
# ─────────────────────────────────────────────────────────────────────────────

def _jaro_winkler(a: str, b: str) -> float:
    if _HAS_JELLYFISH:
        try:
            return jellyfish.jaro_winkler_similarity(a, b)
        except Exception:
            pass
    # Fallback: SequenceMatcher ratio
    return SequenceMatcher(None, a, b).ratio()


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 5 — Phonetic score (full + token-level)
# ─────────────────────────────────────────────────────────────────────────────

def _phonetic_score(query: str, candidate: str) -> float:
    q_words = query.lower().split()
    c_words = candidate.lower().split()
    if not q_words or not c_words: return 0.0

    # Full phrase soundex
    if _soundex(query) == _soundex(candidate):
        return 0.88

    # Full phrase metaphone
    qm = _double_metaphone(query)
    cm = _double_metaphone(candidate)
    if qm and qm == cm:
        return 0.86

    # Token-level phonetic matching
    matched = 0
    for qw in q_words:
        qsdx = _soundex(qw)
        qmeta = _double_metaphone(qw)
        for cw in c_words:
            csdx = _soundex(cw)
            cmeta = _double_metaphone(cw)
            if qsdx == csdx or (qmeta and qmeta == cmeta):
                matched += 1
                break

    if matched == len(q_words):
        return 0.84
    elif matched > 0:
        return round(0.55 + 0.25 * (matched / len(q_words)), 4)

    # Partial phonetic: query soundex prefix matches candidate token soundex
    for cw in c_words:
        csdx = _soundex(cw)
        qsdx = _soundex(query)
        # If first 2 chars of soundex match, it's a phonetic prefix
        if len(qsdx) >= 2 and len(csdx) >= 2 and qsdx[:2] == csdx[:2]:
            return 0.52

    return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Normalization helpers
# ─────────────────────────────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    """Lowercase, strip accents, remove non-alphanumeric."""
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]', '', s.lower())


def _tokens(s: str) -> list[str]:
    """Split name into lowercase tokens, filter single chars."""
    return [t for t in re.split(r'[\s\.\-_]+', s.lower()) if len(t) >= 1]


# ─────────────────────────────────────────────────────────────────────────────
# MASTER SCORING FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def _score(query: str, candidate: str) -> float:
    """
    7-layer intelligent scoring. Returns 0.0–1.0.

    Designed for LIVE TYPING — short partial inputs like "rut", "man", "sundrsh"
    must always produce meaningful scores against matching names.
    """
    q = query.lower().strip()
    c = candidate.lower().strip()

    if not q or not c: return 0.0

    # ── Layer 1: Exact match ──────────────────────────────────────────────────
    if q == c: return 1.0

    # ── Layer 2: Normalized exact ─────────────────────────────────────────────
    nq, nc = _normalize(q), _normalize(c)
    if nq == nc and len(nq) > 1: return 0.97

    q_toks = _tokens(q)
    c_toks = _tokens(c)

    # ── Layer 3: Prefix matching (highest priority for live search) ───────────
    # Full string prefix: "rut" matches "ruthik", "rutvika"
    if nc.startswith(nq) and len(nq) >= 2:
        # Score based on how much of the candidate is covered
        coverage = len(nq) / len(nc)
        return round(0.72 + coverage * 0.25, 4)

    # Any token prefix: "man" matches "manjunath", "manoj", "manasa"
    for ct in c_toks:
        nct = _normalize(ct)
        if nct.startswith(nq) and len(nq) >= 2:
            coverage = len(nq) / len(nct) if nct else 0
            return round(0.68 + coverage * 0.22, 4)

    # Query token prefix: "manj" in "manjunath j r" — check each query token
    for qt in q_toks:
        nqt = _normalize(qt)
        if len(nqt) < 2: continue
        for ct in c_toks:
            nct = _normalize(ct)
            if nct.startswith(nqt):
                coverage = len(nqt) / len(nct) if nct else 0
                return round(0.65 + coverage * 0.20, 4)

    # ── Layer 4: Substring match ──────────────────────────────────────────────
    if nq in nc and len(nq) >= 3:
        return round(0.60 + (len(nq) / len(nc)) * 0.15, 4)

    # Any token contains query
    for ct in c_toks:
        nct = _normalize(ct)
        if nq in nct and len(nq) >= 3:
            return round(0.55 + (len(nq) / len(nct)) * 0.12, 4)

    # ── Layer 5: Phonetic matching ────────────────────────────────────────────
    p_score = _phonetic_score(q, c)
    if p_score >= 0.80:
        return p_score

    # Token-level phonetic: check each query token against each candidate token
    best_phonetic = 0.0
    for qt in q_toks:
        if len(qt) < 3: continue
        for ct in c_toks:
            if len(ct) < 3: continue
            if _soundex(qt) == _soundex(ct):
                best_phonetic = max(best_phonetic, 0.72)
            qm = _double_metaphone(qt)
            cm = _double_metaphone(ct)
            if qm and qm == cm:
                best_phonetic = max(best_phonetic, 0.74)
    if best_phonetic > 0:
        return best_phonetic

    # ── Layer 6: Trigram + Levenshtein + Jaro-Winkler (fuzzy) ────────────────
    # Compare query against full candidate and each token
    best_fuzzy = 0.0

    def _combined_fuzzy(a: str, b: str) -> float:
        if not a or not b: return 0.0
        lev = _lev_sim(a, b)
        tri = _trigram_sim(a, b)
        jw  = _jaro_winkler(a, b)
        return lev * 0.30 + tri * 0.35 + jw * 0.35

    # Full query vs full candidate
    best_fuzzy = max(best_fuzzy, _combined_fuzzy(nq, nc))

    # Query vs each candidate token (handles "sundrsh" → "sudarsh")
    for ct in c_toks:
        nct = _normalize(ct)
        if len(nct) < 3: continue
        best_fuzzy = max(best_fuzzy, _combined_fuzzy(nq, nct))

    # Each query token vs each candidate token
    for qt in q_toks:
        nqt = _normalize(qt)
        if len(nqt) < 3: continue
        for ct in c_toks:
            nct = _normalize(ct)
            if len(nct) < 3: continue
            best_fuzzy = max(best_fuzzy, _combined_fuzzy(nqt, nct))

    if best_fuzzy >= 0.45:
        return round(best_fuzzy, 4)

    # ── Layer 7: Initials matching ────────────────────────────────────────────
    # "mjr" → "Manoj J R"
    initials = ''.join(t[0] for t in c_toks if t)
    if nq == initials and len(nq) >= 2:
        return 0.80

    # Partial initials: "mj" matches "Manoj J R"
    if len(nq) >= 2 and initials.startswith(nq):
        return 0.65

    # ── Phonetic partial (last resort) ───────────────────────────────────────
    if p_score >= 0.45:
        return p_score

    return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Stop words
# ─────────────────────────────────────────────────────────────────────────────

_STOP_WORDS = {
    'show', 'give', 'me', 'display', 'list', 'get', 'find', 'fetch', 'search',
    'all', 'the', 'a', 'an', 'of', 'for', 'in', 'from', 'with', 'and', 'or', 'by',
    'students', 'student', 'marks', 'mark', 'gpa', 'cgpa', 'sgpa', 'details',
    'detail', 'data', 'record', 'records', 'semester', 'sem', 'result', 'results',
    'top', 'best', 'highest', 'lowest', 'first', 'last', 'rank', 'ranked',
    'wise', 'order', 'sort', 'sorted', 'based', 'on', 'their', 'his', 'her',
    'what', 'who', 'which', 'where', 'when', 'how', 'is', 'are', 'was', 'were',
    'please', 'can', 'could', 'would', 'should', 'will', 'do', 'does', 'did',
    'information', 'info', 'about', 'regarding', 'related', 'to',
    '1', '2', '3', '4', '5', '6', '7', '8', '9', '10',
}


# ─────────────────────────────────────────────────────────────────────────────
# Term extraction
# ─────────────────────────────────────────────────────────────────────────────

def extract_search_term(natural_query: str) -> str | None:
    """Pull the name/USN being searched from a natural language query."""
    q = natural_query.strip()

    prep_patterns = [
        r'\bof\s+([A-Za-z0-9][A-Za-z0-9 ]{1,40}?)(?:\s*$|\s+(?:in|from|with|and|cgpa|sgpa|marks|gpa|semester|sem\b|details|data|record))',
        r'\bfor\s+([A-Za-z0-9][A-Za-z0-9 ]{1,40}?)(?:\s*$|\s+(?:in|from|with|and|cgpa|sgpa|marks|gpa|semester|sem\b))',
        r'\bnamed?\s+([A-Za-z0-9][A-Za-z0-9 ]{1,40}?)(?:\s*$|\s+(?:in|from|with|and))',
        r'\bcalled\s+([A-Za-z0-9][A-Za-z0-9 ]{1,40}?)(?:\s*$|\s+(?:in|from|with|and))',
        r'\bstudent\s+([A-Za-z0-9][A-Za-z0-9 ]{1,40}?)(?:\s*$|\s+(?:in|from|with|and|cgpa|sgpa|marks))',
        r'\bshow\s+(?:me\s+)?(?:details?\s+of\s+|marks?\s+of\s+|gpa\s+of\s+|cgpa\s+of\s+|data\s+of\s+)?([A-Za-z0-9][A-Za-z0-9 ]{1,40}?)(?:\s*$|\s+(?:in|from|with|and|cgpa|sgpa|marks|gpa|semester|sem\b))',
        r'\bgive\s+(?:me\s+)?(?:details?\s+of\s+|marks?\s+of\s+|gpa\s+of\s+)?([A-Za-z0-9][A-Za-z0-9 ]{1,40}?)(?:\s*$|\s+(?:in|from|with|and))',
        r'\bdisplay\s+(?:details?\s+of\s+|marks?\s+of\s+)?([A-Za-z0-9][A-Za-z0-9 ]{1,40}?)(?:\s*$|\s+(?:in|from|with|and))',
    ]

    for pat in prep_patterns:
        m = re.search(pat, q, re.IGNORECASE)
        if m:
            term = m.group(1).strip()
            term_words = term.lower().split()
            if all(w in _STOP_WORDS or w.isdigit() for w in term_words):
                continue
            if term.lower() not in _STOP_WORDS and len(term) >= 2:
                return term

    # USN pattern
    usn_match = re.search(r'\b([A-Z0-9]{4,20})\b', q, re.IGNORECASE)
    if usn_match:
        candidate = usn_match.group(1)
        if candidate.upper() not in _STOP_WORDS:
            return candidate

    # Last meaningful word(s)
    words = [w for w in q.split() if w.lower() not in _STOP_WORDS and len(w) >= 2]
    if not words: return None
    if len(words) == 1:
        return words[0] if len(words[0]) >= 2 else None
    last_two = words[-2:]
    if all(w.isalpha() and w.lower() not in _STOP_WORDS for w in last_two):
        combined = ' '.join(last_two)
        if len(combined) <= 30:
            return combined
    last = words[-1]
    return last if len(last) >= 2 else None


# ─────────────────────────────────────────────────────────────────────────────
# Core fuzzy search
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_all_students() -> list[dict]:
    """Fetch all active students from DB."""
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT usn, name FROM students ORDER BY name")
        rows = cur.fetchall()
        cur.close()
    return rows


def fuzzy_search_students(
    search_term: str,
    limit: int = 8,
    min_score: float = 0.70
) -> list[dict]:
    """
    Fuzzy-match students using 7-layer NLP scoring.
    Returns up to `limit` results with score >= min_score.
    """
    if not search_term:
        return []

    term = search_term.strip().lower()
    all_students = _fetch_all_students()
    if not all_students:
        return []

    scored = []
    for s in all_students:
        name_score = _score(term, s['name'] or '')
        usn_score  = _score(term, s['usn']  or '')
        best = max(name_score, usn_score)
        if best >= min_score:
            scored.append({**s, 'score': round(best, 4)})

    scored.sort(key=lambda x: (-x['score'], x['name'] or ''))
    return scored[:limit]


def get_live_suggestions(q: str, limit: int = 5) -> list[dict]:
    """
    Live typing suggestions — very lenient threshold so partial inputs
    like "rut", "man", "sundrsh" always return nearest matches.

    Threshold strategy:
      - len(q) == 2 → 0.20 (almost anything that starts with those 2 chars)
      - len(q) == 3 → 0.25
      - len(q) >= 4 → 0.30
    Never returns empty if there are ANY plausible matches.
    """
    q = q.strip()
    if not q or len(q) < 2:
        return []

    # Dynamic threshold: shorter input = more lenient
    if len(q) <= 2:
        threshold = 0.20
    elif len(q) == 3:
        threshold = 0.25
    elif len(q) == 4:
        threshold = 0.28
    else:
        threshold = 0.30

    results = fuzzy_search_students(q, limit=limit, min_score=threshold)

    # If still empty, try even lower threshold as last resort
    if not results and len(q) >= 2:
        results = fuzzy_search_students(q, limit=limit, min_score=0.15)

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Student data helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_student_data(usn: str) -> list[dict]:
    """Full semester-wise data for a student with cumulative CGPA per semester."""
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT s.usn, s.name, m.semester, m.sgpa, "
            "ROUND(AVG(m.sgpa) OVER (PARTITION BY m.usn ORDER BY m.semester "
            "ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),2) AS cgpa "
            "FROM students s JOIN marks m ON s.usn=m.usn "
            "WHERE s.usn=%s ORDER BY m.semester",
            (usn,)
        )
        rows = cur.fetchall()
        cur.close()

    result = []
    for r in rows:
        clean = {}
        for k, v in r.items():
            clean[k] = float(v) if hasattr(v, '__float__') and not isinstance(v, (int, float, str, bool, type(None))) else v
        result.append(clean)
    return result


def get_student_profile(usn: str) -> dict | None:
    """Get full student personal profile."""
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM students WHERE usn=%s", (usn,))
        row = cur.fetchone()
        cur.close()
    if not row:
        return None
    clean = {}
    for k, v in row.items():
        if hasattr(v, 'isoformat'):
            clean[k] = v.isoformat()
        else:
            clean[k] = v
    return clean


# ─────────────────────────────────────────────────────────────────────────────
# Confidence thresholds
# ─────────────────────────────────────────────────────────────────────────────

THRESHOLD_AUTO_CORRECT = 0.95   # ≥95% → auto-correct silently
THRESHOLD_PRIMARY      = 0.80   # 80–94% → "Did you mean?"
THRESHOLD_POSSIBLE     = 0.55   # 55–79% → possible matches list
THRESHOLD_MINIMUM      = 0.55   # <55% → no suggestion (only on explicit submit)


# ─────────────────────────────────────────────────────────────────────────────
# Smart fallback (called on 0 SQL results)
# ─────────────────────────────────────────────────────────────────────────────

def smart_fallback(natural_query: str) -> dict:
    """
    Called when SQL returns 0 results.
    Returns structured suggestion for the multi-choice interaction.
    """
    term = extract_search_term(natural_query)

    _empty = {
        'type': 'no_match',
        'search_term': term or '',
        'confidence': 0.0,
        'auto_corrected': False,
        'message': 'No matching records available.',
        'top_match': None,
        'suggestions': [],
    }

    if not term:
        return _empty

    matches = fuzzy_search_students(term, limit=8, min_score=THRESHOLD_MINIMUM)

    if not matches:
        return _empty

    top_score = matches[0]['score']

    if top_score < THRESHOLD_MINIMUM:
        return {**_empty, 'search_term': term, 'confidence': top_score}

    # Detect duplicate names
    same_name_groups: dict[str, list] = {}
    for m in matches:
        key = (m['name'] or '').upper().strip()
        same_name_groups.setdefault(key, []).append(m)

    top_name = (matches[0]['name'] or '').upper().strip()
    has_duplicates = len(same_name_groups.get(top_name, [])) > 1

    # Fetch data for top candidates
    suggestions = []
    for m in matches[:5]:
        data    = get_student_data(m['usn'])
        profile = get_student_profile(m['usn'])
        suggestions.append({
            **m,
            'pct':     round(m['score'] * 100),
            'data':    data,
            'profile': profile,
        })

    top = suggestions[0]

    # Multiple students with same name
    if has_duplicates:
        duplicate_list = [
            s for s in suggestions
            if (s['name'] or '').upper().strip() == top_name
        ]
        return {
            'type':           'multiple_match',
            'search_term':    term,
            'confidence':     round(top_score, 4),
            'auto_corrected': False,
            'message':        f'Multiple students found with similar name "{top["name"]}".\nPlease select the specific student by USN.',
            'top_match':      top,
            'suggestions':    duplicate_list,
        }

    # Auto-correct (very high confidence)
    if top_score >= THRESHOLD_AUTO_CORRECT:
        return {
            'type':           'suggestion',
            'search_term':    term,
            'confidence':     round(top_score, 4),
            'auto_corrected': True,
            'message':        f'Showing results for "{top["name"]}" — closest match to "{term}"',
            'top_match':      top,
            'suggestions':    suggestions,
        }

    # High confidence — "Did you mean?"
    if top_score >= THRESHOLD_PRIMARY:
        return {
            'type':           'suggestion',
            'search_term':    term,
            'confidence':     round(top_score, 4),
            'auto_corrected': False,
            'message':        f'Did you mean {top["name"]} ?',
            'top_match':      top,
            'suggestions':    suggestions[:1],
        }

    # Lower confidence — possible matches
    return {
        'type':           'possible_matches',
        'search_term':    term,
        'confidence':     round(top_score, 4),
        'auto_corrected': False,
        'message':        'No exact record found.\nClosest matches:',
        'top_match':      top,
        'suggestions':    suggestions[:5],
    }
