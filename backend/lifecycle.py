"""
lifecycle.py — shared, framework-free logic for Student Lifecycle Management.

Design constraints (from the project spec):
  * Lifecycle status HISTORY (student_lifecycle_events) is the authoritative,
    append-only record; student_lifecycle_status / students.lifecycle_status are
    derived caches. A status is never edited in place — every change appends an
    event, so the previous status/actor/date/reason are always preserved.
  * Changing lifecycle status NEVER deletes or alters a student's academic,
    personal, fee, semester or backlog records.
  * The eligibility engine applies ONLY rules that are explicitly marked
    'verified' in vtu_scheme_rules, each carrying source/clause/effective-date.
    It never invents a rule, never guarantees eligibility and never
    auto-approves readmission — its output is always advisory and academic
    review is always required.
"""
from __future__ import annotations

import difflib
import json
import re

# ── Canonical lifecycle statuses (kept <=30 chars for the DB column) ──────────
STATUS_ACTIVE = "Active"
STATUS_TEMP_DISCONTINUED = "Temporarily Discontinued"
STATUS_DISCONTINUED_REVIEW = "Discontinued-Review Req"
STATUS_DROPOUT = "Dropout-College Recorded"
STATUS_READMISSION_REQUESTED = "Readmission Requested"
STATUS_READMISSION_APPROVED = "Readmission Approved"
STATUS_REJOINED = "Rejoined-Active"
STATUS_GRADUATED = "Graduated"
STATUS_TRANSFERRED = "Transferred"
STATUS_ADMISSION_CANCELLED = "Admission Cancelled"
STATUS_OTHER = "Other"

LIFECYCLE_STATUSES = [
    STATUS_ACTIVE,
    STATUS_TEMP_DISCONTINUED,
    STATUS_DISCONTINUED_REVIEW,
    STATUS_DROPOUT,
    STATUS_READMISSION_REQUESTED,
    STATUS_READMISSION_APPROVED,
    STATUS_REJOINED,
    STATUS_GRADUATED,
    STATUS_TRANSFERRED,
    STATUS_ADMISSION_CANCELLED,
    STATUS_OTHER,
]
_STATUS_SET = set(LIFECYCLE_STATUSES)

# Statuses that mean the student is currently enrolled/attending.
ACTIVE_STATUSES = {STATUS_ACTIVE, STATUS_REJOINED, STATUS_READMISSION_APPROVED}
# Statuses that require an authorized readmission before returning to Active.
DISCONTINUED_STATUSES = {
    STATUS_TEMP_DISCONTINUED, STATUS_DISCONTINUED_REVIEW, STATUS_DROPOUT,
}

# ── Lifecycle transition matrix (drives one-click actions + validation) ───────
# Every action here is reversible: any non-active status can always be reversed
# back to Active, and Active can be re-discontinued, so operators can undo a
# mistaken discontinue/dropout with a single click. Terminal states (Graduated /
# Transferred / Admission Cancelled) only expose a "correct back to Active"
# escape so genuine data-entry mistakes are still fixable.
_STATUS_ACTIONS = {
    STATUS_ACTIVE: [
        {"label": "Discontinue", "to_status": STATUS_TEMP_DISCONTINUED, "event_type": "DISCONTINUE"},
        {"label": "Mark Dropout", "to_status": STATUS_DROPOUT, "event_type": "DISCONTINUE"},
        {"label": "Graduate", "to_status": STATUS_GRADUATED, "event_type": "STATUS_CHANGE"},
        {"label": "Transfer", "to_status": STATUS_TRANSFERRED, "event_type": "STATUS_CHANGE"},
    ],
    STATUS_TEMP_DISCONTINUED: [
        {"label": "Reverse (back to Active)", "to_status": STATUS_ACTIVE, "event_type": "CORRECTION"},
        {"label": "Mark Dropout", "to_status": STATUS_DROPOUT, "event_type": "DISCONTINUE"},
        {"label": "Request Readmission", "to_status": STATUS_READMISSION_REQUESTED, "event_type": "READMISSION_REQUEST"},
        {"label": "Rejoin", "to_status": STATUS_REJOINED, "event_type": "REJOIN"},
    ],
    STATUS_DISCONTINUED_REVIEW: [
        {"label": "Reverse (back to Active)", "to_status": STATUS_ACTIVE, "event_type": "CORRECTION"},
        {"label": "Discontinue", "to_status": STATUS_TEMP_DISCONTINUED, "event_type": "DISCONTINUE"},
        {"label": "Mark Dropout", "to_status": STATUS_DROPOUT, "event_type": "DISCONTINUE"},
        {"label": "Request Readmission", "to_status": STATUS_READMISSION_REQUESTED, "event_type": "READMISSION_REQUEST"},
    ],
    STATUS_DROPOUT: [
        {"label": "Reverse (back to Active)", "to_status": STATUS_ACTIVE, "event_type": "CORRECTION"},
        {"label": "Request Readmission", "to_status": STATUS_READMISSION_REQUESTED, "event_type": "READMISSION_REQUEST"},
    ],
    STATUS_READMISSION_REQUESTED: [
        {"label": "Mark Readmission Approved", "to_status": STATUS_READMISSION_APPROVED, "event_type": "READMISSION_DECISION"},
        {"label": "Cancel (back to Discontinued)", "to_status": STATUS_TEMP_DISCONTINUED, "event_type": "CORRECTION"},
    ],
    STATUS_READMISSION_APPROVED: [
        {"label": "Rejoin (back to Active)", "to_status": STATUS_ACTIVE, "event_type": "REJOIN"},
        {"label": "Reverse (back to Discontinued)", "to_status": STATUS_TEMP_DISCONTINUED, "event_type": "CORRECTION"},
    ],
    STATUS_REJOINED: [
        {"label": "Discontinue", "to_status": STATUS_TEMP_DISCONTINUED, "event_type": "DISCONTINUE"},
        {"label": "Graduate", "to_status": STATUS_GRADUATED, "event_type": "STATUS_CHANGE"},
    ],
    STATUS_GRADUATED: [
        {"label": "Correct (back to Active)", "to_status": STATUS_ACTIVE, "event_type": "CORRECTION"},
    ],
    STATUS_TRANSFERRED: [
        {"label": "Correct (back to Active)", "to_status": STATUS_ACTIVE, "event_type": "CORRECTION"},
    ],
    STATUS_ADMISSION_CANCELLED: [
        {"label": "Reactivate", "to_status": STATUS_ACTIVE, "event_type": "CORRECTION"},
    ],
    STATUS_OTHER: [
        {"label": "Set Active", "to_status": STATUS_ACTIVE, "event_type": "CORRECTION"},
        {"label": "Discontinue", "to_status": STATUS_TEMP_DISCONTINUED, "event_type": "DISCONTINUE"},
        {"label": "Mark Dropout", "to_status": STATUS_DROPOUT, "event_type": "DISCONTINUE"},
    ],
}


def next_actions(from_status: str) -> list[dict]:
    """One-click actions offered for a student's current lifecycle status."""
    canonical = normalize_status(from_status)
    if canonical is None:
        # A stored value the register does not recognise (legacy import, manual
        # edit): the student must still have a one-click way back to Active.
        return _STATUS_ACTIONS[STATUS_OTHER]
    return _STATUS_ACTIONS.get(canonical, _STATUS_ACTIONS[STATUS_OTHER])


def is_transition_allowed(from_status: str, to_status: str) -> bool:
    """Advisory transition check. Unknown origin is treated as Active; a same-
    status move is always allowed (idempotent). Not used to hard-block Admins,
    who may always correct a mistaken status."""
    src = normalize_status(from_status) or STATUS_ACTIVE
    dst = normalize_status(to_status)
    if not dst:
        return False
    if src == dst:
        return True
    return any(a["to_status"] == dst for a in _STATUS_ACTIONS.get(src, []))

# ── Event types (audit categories) ───────────────────────────────────────────
EV_STATUS_CHANGE = "STATUS_CHANGE"
EV_DISCONTINUE = "DISCONTINUE"
EV_READMISSION_REQUEST = "READMISSION_REQUEST"
EV_READMISSION_DECISION = "READMISSION_DECISION"
EV_REJOIN = "REJOIN"
EV_CORRECTION = "CORRECTION"


# ── Reason categories (controlled classification for filters/counts, spec §2) ──
REASON_CATEGORIES = [
    "financial", "medical", "personal", "relocation",
    "academic", "disciplinary", "family", "other",
]
_REASON_CATEGORY_SET = set(REASON_CATEGORIES)

_REASON_CATEGORY_KEYWORDS = {
    "financial": ["financ", "money", "fee", "fees", "tuition", "economic",
                   "poverty", "unable to pay", "baki", "hone", "ಹಣ", "ಶುಲ್ಕ"],
    "medical": ["medic", "health", "illness", "sick", "hospital", "injury",
                "disease", "ಆರೋಗ್ಯ", "ಅನಾರೋಗ್ಯ"],
    "relocation": ["relocat", "shifted", "moved", "shift", "ಸ್ಥಳಾಂತರ"],
    "academic": ["academ", "failed", "backlog", "study", "studies", "result",
                 "ಓದು", "ಪರೀಕ್ಷೆ"],
    "disciplinary": ["disciplin", "ragging", "misconduct", "attendance"],
    "family": ["family", "father", "mother", "marriage", "wedding", "ಕುಟುಂಬ"],
    "personal": ["personal", "private", "ವೈಯಕ್ತಿಕ", "ಕಾರಣ"],
}


def classify_reason_category(reason_text: str) -> str | None:
    """Deterministically map a free-text reason to a controlled category.
    Blank → None (never guess a category with no evidence)."""
    text = (reason_text or "").strip().lower()
    if not text:
        return None
    for cat in ("financial", "medical", "relocation", "disciplinary",
                "academic", "family", "personal"):
        for kw in _REASON_CATEGORY_KEYWORDS[cat]:
            if kw in text:
                return cat
    return "other"


def normalize_reason_category(value) -> str | None:
    """Canonical form of a category, or None when it is not one the register
    knows. Comparison is spacing/case tolerant because staff type both."""
    v = (value or "").strip().lower()
    return v if v in _REASON_CATEGORY_SET else None


def resolve_reason_category(value, reason_text=None) -> str | None:
    """The category that gets STORED. An explicit one is validated (anything
    outside the vocabulary is refused, because an unfilterable value is dead
    data the dropdown and the NL questions can never return). With no explicit
    category, derive one from the free-text reason so a reason typed into the
    status dialog becomes filterable data instead of a loose sentence.
    Raises ValueError for a rejected value so callers can answer 400."""
    text = (value or "").strip()
    if not text:
        return classify_reason_category(reason_text)
    canon = normalize_reason_category(text)
    if canon is None:
        raise ValueError(
            f"Unknown reason category '{text}'. "
            f"Use one of: {', '.join(REASON_CATEGORIES)}.")
    return canon


# ── Natural-language lifecycle RECORD command parsing (spec §1) ───────────────
# A "record" command asks the system to SAVE a status change; it is distinct
# from a read/list/count query (handled by _build_lifecycle_query).
_USN_RE = re.compile(r'\b[0-9][A-Za-z]{2}[0-9]{2}[A-Za-z]{2,3}[0-9]{3}\b')

_READ_MARKER_RE = re.compile(
    r'\b(list|show|display|find|get|how\s+many|count|number\s+of|export|'
    r'history|which|who|all|total|print)\b', re.I)
_RECORD_IMPERATIVE_RE = re.compile(r'\b(record|mark|add|note|log|enter)\b', re.I)

# Verb → target lifecycle status. Order matters (first match wins).
_STATUS_VERBS = [
    (re.compile(r'\bdrop\s*out\b|\bdropped\s*out\b|\bleft\s+(?:the\s+)?college\b|\bleft\s+college\b|\bpermanently\b.*\bleft\b', re.I),
     STATUS_DROPOUT),
    (re.compile(r'\bdiscontinu\w*\b|\bstopped\s+(?:studies|college|course)\b|\bniyarpi\s+bes\w*\b', re.I),
     STATUS_TEMP_DISCONTINUED),
    (re.compile(r'\brea-?dmissi\w*\b|\brea-?dmit\w*\b|\bmaru\s*pravesha?\b', re.I),
     STATUS_READMISSION_REQUESTED),
    (re.compile(r'\bre-?join(?:ed|ing)?\b|\bresum\w*\b|\bcame?\s+back\b|\bback\s+to\s+college\b|\bmatte\s+(?:sere|join)\w*\b', re.I),
     STATUS_REJOINED),
    (re.compile(r'\bgraduat\w*\b|\bpassed\s+out\b', re.I), STATUS_GRADUATED),
    (re.compile(r'\btransferred?\b|\btransfer\b', re.I), STATUS_TRANSFERRED),
]


def is_lifecycle_record_command(nq: str) -> bool:
    """True when the query is an imperative to RECORD a lifecycle change rather
    than read/list/count one."""
    text = (nq or "").strip()
    if not text:
        return False
    if not _extract_status(text):
        return False
    # A read query that merely mentions the words ("list all dropouts") is not a
    # record command, unless it also carries an explicit record imperative.
    if _READ_MARKER_RE.search(text) and not _RECORD_IMPERATIVE_RE.search(text):
        return False
    # Must point at a target: a USN, or an explicit "student/mark ...".
    has_usn = bool(_USN_RE.search(text))
    has_target_word = bool(re.search(r'\busn\b|student|\bthis\s+student\b|\bmark\b|\brecord\b', text, re.I))
    return has_usn or has_target_word


def _extract_status(text: str) -> str | None:
    for rx, status in _STATUS_VERBS:
        if rx.search(text):
            return status
    return _fuzzy_status(text)


# Mistyped status words. Staff type fast on a shared keyboard and 'discontious',
# 'droput' or 'rejonied' are the same instruction — the parser has to meet them
# halfway instead of refusing the record.
_STATUS_KEYWORD_FORMS = {
    STATUS_DROPOUT: ("dropout", "dropped", "dropouts"),
    STATUS_TEMP_DISCONTINUED: ("discontinue", "discontinued", "discontinuation"),
    STATUS_READMISSION_REQUESTED: ("readmission", "readmit", "readmitted"),
    STATUS_REJOINED: ("rejoin", "rejoined", "rejoining"),
    STATUS_GRADUATED: ("graduate", "graduated", "graduation"),
    STATUS_TRANSFERRED: ("transfer", "transferred", "transfered"),
}


def _fuzzy_status(text: str) -> str | None:
    """Closest canonical status keyword across the words of a command, or None.
    A word only counts as a near-miss when it shares the keyword's first letter
    and is at least 80% similar, so unrelated words are never read as a status."""
    best_status, best_score = None, 0.0
    for tok in re.findall(r"[a-zA-Z]{6,}", (text or "").lower()):
        for status, forms in _STATUS_KEYWORD_FORMS.items():
            for form in forms:
                if tok[0] != form[0]:
                    continue
                score = difflib.SequenceMatcher(None, tok, form).ratio()
                if score > best_score:
                    best_status, best_score = status, score
    return best_status if best_score >= 0.8 else None


_DATE_ISO_RE = re.compile(r'\b(\d{4}-\d{2}-\d{2})\b')
_DATE_DMY_RE = re.compile(r'\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b')
_MONTH_RE = re.compile(r'\b(?:on|in|dated?|effective)\s+'
                       r'(january|february|march|april|may|june|july|august|'
                       r'september|october|november|december)\s+(\d{4})\b', re.I)
# Both word orders are spoken: '5th semester' and 'semester 5', and staff add
# filler ('last enrolled semester was 6'). Neither may lose the column.
_SEM_RE = re.compile(
    r'\b(?:sem(?:ester)?\s*(?:was|is|of|in|:)?\s*(\d{1,2})(?:st|nd|rd|th)?'
    r'|(\d{1,2})(?:st|nd|rd|th)?\s*sem(?:ester)?)\b', re.I)
# The last group must not be the day of a full date: 'discontinued on
# 2026-10-01' carries an effective date, not the academic year '2026-10'.
_AY_RE = re.compile(r'\b(\d{4})\s*[-–/]\s*(\d{2,4})(?!\s*[-/.]\s*\d{1,2}\b)')
_YEAR_RE = re.compile(r'\b(?:in|during|since|year)\s+(\d{4})\b', re.I)
_REASON_RE = re.compile(r'(?:due to|because of|reason(?:\s*[:\-]?\s*)?|owing to|on account of)\s+'
                        r'(.+?)(?:[.,;]|$)', re.I | re.S)
_DOC_RE = re.compile(r'(?:doc(?:ument)?|ref(?:erence)?|challan|certificate)\s*(?:no\.?|number|id)?\s*[:\-]?\s*([A-Za-z0-9\-/]+)', re.I)

# Words that belong to the instruction, never to the student's name. Matched with
# \b so a name keeps its letters: 'mark Ashoka as discontinued' must search for
# 'Ashoka', not 'hoka'.
_NAME_STOPWORDS = (
    "please", "kindly", "the", "a", "an", "student", "students", "of", "named",
    "called", "for", "record", "mark", "note", "log", "enter", "set", "as",
    "usn", "on", "in", "from", "to", "is", "was", "has", "have", "who", "that",
    "his", "her", "him", "he", "she", "due to", "because of", "owing to",
    "reason", "given", "status", "discontinue", "discontinued", "discontinuation",
    "dropout", "dropouts", "drop", "out", "dropped", "left", "college",
    "readmission", "readmit", "readmitted", "rejoin", "rejoined", "rejoining",
    "graduate", "graduated", "graduation", "transfer", "transferred", "transfered",
    "studies", "study", "back", "active", "came", "come")
_NAME_STOP_RE = re.compile(
    r"\b(?:%s)\b" % "|".join(sorted(set(_NAME_STOPWORDS), key=len, reverse=True)), re.I)


def _to_iso_date(text: str) -> tuple[str | None, str | None]:
    """Return (effective_date, discontinue_year) parsed from a command."""
    m = _DATE_ISO_RE.search(text)
    if m:
        return m.group(1), m.group(1)[:4]
    m = _DATE_DMY_RE.search(text)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}", y
    m = _MONTH_RE.search(text)
    if m:
        months = {mm: i + 1 for i, mm in enumerate(
            ["january", "february", "march", "april", "may", "june", "july",
             "august", "september", "october", "november", "december"])}
        mm = months.get(m.group(1).lower())
        y = m.group(2)
        return (f"{y}-{mm:02d}-01" if mm else None), y
    m = _YEAR_RE.search(text)
    if m:
        return None, m.group(1)
    return None, None


# The spans _to_iso_date understands, in the same order it tries them.
_DATE_SPANS = (_DATE_ISO_RE, _DATE_DMY_RE, _MONTH_RE, _YEAR_RE)
# Function words a removed date leaves behind at the end of the reason.
_TRAILING_DATE_JUNK_RE = re.compile(
    r"(?:\s+\b(?:for|on|in|of|the|a|dated|effective|last|during|since|year|and|by|to)\b)+\s*$",
    re.I)


def _strip_date_phrase(reason: str | None, academic_year: str | None = None) -> str | None:
    """Drop from a spoken reason the date that was read as the effective date.

    Staff type 'discontinued due to medical reasons on 01-10-2026': the date
    belongs to the event's EFFECTIVE DATE column, and leaving it inside the
    reason puts the same number in two columns and makes the register's reason
    text unreadable when staff filter or export it. Only spans the parser
    actually understood are removed (the caller strips just when it found one),
    so a reason carrying an unrecognised date keeps the person's own words
    rather than losing information.
    """
    if not reason:
        return reason
    out = reason
    for rx in _DATE_SPANS:
        out = rx.sub(" ", out)
    if academic_year:
        out = _AY_RE.sub(" ", out)
    out = re.sub(r"\s+", " ", out.strip())
    out = _TRAILING_DATE_JUNK_RE.sub("", out)
    return out.strip(" ,;.-:") or None


def parse_lifecycle_command(nq: str) -> dict:
    """Extract a structured lifecycle-record intent from natural language
    (already normalized toward English by the caller). Returns a dict with:
    action, target_status, usn, target_text, reason_text, reason_category,
    effective_date, discontinue_year, last_enrolled_semester, academic_year,
    document_ref. Never touches the database; identity resolution is done by
    the caller against MySQL."""
    text = (nq or "").strip()
    usn_m = _USN_RE.search(text)
    usn = usn_m.group(0) if usn_m else None

    reason_m = _REASON_RE.search(text)
    reason_text = re.sub(r"\s+", " ", reason_m.group(1)).strip() if reason_m else None

    effective_date, discontinue_year = _to_iso_date(text)
    ay_m = _AY_RE.search(text)
    academic_year = f"{ay_m.group(1)}-{ay_m.group(2)}" if ay_m else None
    # The date belongs in EFFECTIVE DATE / ACADEMIC YEAR, not inside the reason
    # text a reader scans in the register. Strip only when it really was
    # understood, so an unrecognised date is never silently discarded.
    if effective_date or discontinue_year or academic_year:
        reason_text = _strip_date_phrase(reason_text, academic_year)
    reason_category = classify_reason_category(reason_text)
    sem_m = _SEM_RE.search(text)
    sem_num = (sem_m.group(1) or sem_m.group(2)) if sem_m else None
    semester = int(sem_num) if sem_num and 0 < int(sem_num) <= 12 else None
    doc_m = _DOC_RE.search(text)
    document_ref = doc_m.group(1) if doc_m else None

    # target_text = the name to resolve when no USN is present. The instruction
    # words are removed on WORD boundaries only (a bare 'a' or 'as' inside a name
    # must survive: 'Ashoka' is not 'hoka'), and the reason clause is dropped
    # first because 'due to illness' describes the status, not the student.
    target_text = ""
    if not usn:
        t = text.replace(reason_m.group(0), " ") if reason_m else text
        t = _NAME_STOP_RE.sub(" ", t)
        t = re.sub(r'\s+', ' ', t).strip(" .,;:!?-")
        target_text = t

    return {
        "action": "record_lifecycle",
        "target_status": _extract_status(text),
        "usn": usn,
        "target_text": target_text,
        "reason_text": reason_text,
        "reason_category": reason_category,
        "effective_date": effective_date,
        "discontinue_year": discontinue_year,
        "last_enrolled_semester": semester,
        "academic_year": academic_year,
        "document_ref": document_ref,
        "original_query": text,
    }


def latest_event(cur, usn: str) -> dict | None:
    cur.execute("SELECT * FROM student_lifecycle_events WHERE usn=%s "
                "ORDER BY created_at DESC, id DESC LIMIT 1", (usn,))
    return cur.fetchone()


def is_duplicate_lifecycle_event(cur, usn, to_status, effective_date=None,
                                 reason_category=None) -> bool:
    """Repeated-submission guard: the student's most recent event already
    records the same target status (and, when supplied, the same effective date
    / reason category)."""
    last = latest_event(cur, usn)
    if not last or last.get("to_status") != to_status:
        return False
    if effective_date and str(last.get("effective_date") or "") != str(effective_date):
        return False
    # Comparison is spacing/case tolerant: 'Medical' and 'medical' are the same
    # record to a human, and a letter-case difference must not be a second event.
    last_cat = (last.get("reason_category") or "").strip().lower() or None
    new_cat = (reason_category or "").strip().lower() or None
    if new_cat is not None and last_cat != new_cat:
        return False
    return True


def is_valid_status(value: str) -> bool:
    return isinstance(value, str) and value.strip() in _STATUS_SET


def _build_status_aliases() -> dict:
    """Loose forms of each canonical status (the staff-facing labels are the
    hyphenated canonicals, but people type 'dropout' or 'rejoined'). Only forms
    that identify exactly ONE status are kept, so an ambiguous word is still
    rejected rather than guessed at."""
    candidates: dict = {}
    for status in LIFECYCLE_STATUSES:
        forms = {
            status,
            status.split("-")[0].strip(),
            status.replace("-", " ").strip(),
            status.replace("-", "").strip(),
        }
        for form in forms:
            key = form.casefold()
            if key:
                candidates.setdefault(key, set()).add(status)
    return {k: next(iter(v)) for k, v in candidates.items() if len(v) == 1}


_STATUS_ALIASES = _build_status_aliases()


def normalize_status(value: str) -> str | None:
    """Case-tolerant match to a canonical status, else None."""
    if not value:
        return None
    v = value.strip()
    if v in _STATUS_SET:
        return v
    folded = {s.casefold(): s for s in LIFECYCLE_STATUSES}
    return folded.get(v.casefold()) or _STATUS_ALIASES.get(v.casefold())


def _clean_date(value):
    """Accept 'YYYY-MM-DD' strings or date-like; return None when unusable."""
    if not value:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    m = re.search(r"\d{4}-\d{2}-\d{2}", str(value))
    return m.group(0) if m else None


def _int_or_none(value):
    try:
        n = int(re.search(r"\d+", str(value)).group(0))
        return n if 0 < n <= 12 else None
    except (TypeError, ValueError, AttributeError, IndexError):
        return None


# ── Eligibility engine (conservative, review-flagged) ────────────────────────
OUTCOME_NO_ISSUE_REVIEW = "no_configured_issue_review_required"
OUTCOME_MANUAL_REVIEW = "manual_review_required"
OUTCOME_RULE_CONFLICT = "potential_rule_conflict"
OUTCOME_DOCS_REQUIRED = "documents_or_confirmation_required"

_OUTCOME_TEXT = {
    OUTCOME_NO_ISSUE_REVIEW: "No configured issue detected — academic review still required.",
    OUTCOME_MANUAL_REVIEW: "Eligibility requires manual academic review.",
    OUTCOME_RULE_CONFLICT: "Potential rule conflict detected — academic review required.",
    OUTCOME_DOCS_REQUIRED: "Supporting documents or official confirmation required.",
}


def _load_verified_rules(cur, scheme: str | None, category: str | None, batch: int | None):
    """Return only rules explicitly marked verified and applicable to this
    scheme / admission category / batch range. Unverified rules are ignored."""
    sql = ("SELECT scheme_code, admission_category, rule_key, rule_value, "
           "source_url, clause_ref, effective_date, verification_status, notes, "
           "applies_from_batch, applies_to_batch "
           "FROM vtu_scheme_rules WHERE verification_status='verified'")
    params: list = []
    if scheme:
        sql += " AND (scheme_code=%s OR scheme_code='')"
        params.append(scheme)
    cur.execute(sql, params)
    rows = cur.fetchall()
    applicable = []
    for r in rows:
        cat = (r.get("admission_category") or "").strip()
        if category and cat and cat.casefold() != category.casefold():
            continue
        lo, hi = r.get("applies_from_batch"), r.get("applies_to_batch")
        if batch is not None and (lo is not None or hi is not None):
            if lo is not None and batch < int(lo):
                continue
            if hi is not None and batch > int(hi):
                continue
        applicable.append(r)
    return applicable


def evaluate_eligibility(cur, usn: str, requested_sem=None, scheme=None) -> dict:
    """
    Advisory, non-binding eligibility assessment for a readmission/progression
    request. Reads the student's actual academic record and applies only the
    verified scheme rules configured for it. Never approves and never blocks
    permanently — the caller records an authorized human decision.
    """
    requested_sem = _int_or_none(requested_sem)
    cur.execute(
        "SELECT usn, name, admission_year, student_type, branch, lifecycle_status "
        "FROM students WHERE usn=%s", (usn,))
    student = cur.fetchone()
    if not student:
        return {"usn": usn, "found": False, "outcome": OUTCOME_MANUAL_REVIEW,
                "outcome_text": _OUTCOME_TEXT[OUTCOME_MANUAL_REVIEW],
                "concerns": ["Student record not found — verify identity before any decision."],
                "rules_applied": [], "review_required": True}

    cur.execute(
        "SELECT MAX(semester) last_sem, COUNT(*) attempts FROM marks WHERE usn=%s",
        (usn,))
    marks = cur.fetchone() or {}
    cur.execute(
        "SELECT COUNT(*) n FROM student_backlogs WHERE usn=%s AND cleared=0", (usn,))
    open_backlogs = (cur.fetchone() or {}).get("n", 0)
    cur.execute(
        "SELECT current_status, scheme, last_enrolled_semester, effective_date "
        "FROM student_lifecycle_status WHERE usn=%s", (usn,))
    ls = cur.fetchone() or {}

    scheme = scheme or ls.get("scheme")
    category = student.get("student_type")
    batch = None
    try:
        batch = int(student.get("admission_year")) if student.get("admission_year") else None
    except (TypeError, ValueError):
        batch = None

    concerns: list[str] = []
    applied: list[dict] = []
    conflict = False
    docs_required = False

    rules = _load_verified_rules(cur, scheme, category, batch)
    for r in rules:
        key = (r.get("rule_key") or "").strip()
        applied.append({
            "rule_key": key, "scheme_code": r.get("scheme_code"),
            "source_url": r.get("source_url"), "clause_ref": r.get("clause_ref"),
            "effective_date": str(r.get("effective_date") or ""),
        })
        if key == "max_completion_years":
            try:
                limit = float(r.get("rule_value"))
                if batch:
                    elapsed = (2026 - batch)
                    if elapsed > limit:
                        concerns.append(
                            f"Elapsed years since admission ({elapsed}) exceeds "
                            f"configured maximum ({limit}) — verify under {r.get('clause_ref') or 'rule'}.")
            except (TypeError, ValueError):
                conflict = True
                concerns.append("A configured maximum-duration rule is malformed — review required.")
        elif key == "requires_documents":
            docs_required = True

    # Structural, non-rule observations (facts, not invented rules):
    last_known = requested_sem or ls.get("last_enrolled_semester") or marks.get("last_sem")
    if open_backlogs:
        concerns.append(
            f"Student has {open_backlogs} open backlog(s); do not assume next-semester "
            "eligibility from backlog status alone — recalculate under verified scheme rules.")
    if not rules:
        concerns.append(
            "No verified scheme rule is configured for this student's scheme/category/batch; "
            "the case must be assessed manually against official VTU regulations.")

    if conflict:
        outcome = OUTCOME_RULE_CONFLICT
    elif docs_required:
        outcome = OUTCOME_DOCS_REQUIRED
    elif concerns:
        outcome = OUTCOME_MANUAL_REVIEW
    else:
        outcome = OUTCOME_NO_ISSUE_REVIEW

    return {
        "usn": usn, "found": True,
        "name": student.get("name"),
        "scheme": scheme, "admission_category": category, "batch": batch,
        "requested_semester": requested_sem,
        "last_enrolled_semester": ls.get("last_enrolled_semester") or marks.get("last_sem"),
        "open_backlogs": open_backlogs,
        "current_status": (ls.get("current_status") or student.get("lifecycle_status") or STATUS_ACTIVE),
        "outcome": outcome, "outcome_text": _OUTCOME_TEXT[outcome],
        "concerns": concerns, "rules_applied": applied,
        "review_required": True,   # always — the app never self-approves
        "auto_approved": False,    # explicit: this engine never approves
    }
