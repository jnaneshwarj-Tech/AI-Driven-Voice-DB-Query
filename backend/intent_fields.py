"""
intent_fields.py — Reusable intent → field mapping layer for smart search.

This is the ONE place that turns a *meaning* a staff member asks for
("mother's phone number", "father is a farmer", "discontinued for financial
reasons") into the actual MySQL column (or dynamic_data JSON key) that holds
it — using the LIVE schema, not a hardcoded column list.

Design goals (spec §2 / §3 / §5):
  * Never assume a field exists. Only resolve against columns/keys that are
    really present in `students` (real columns) or `dynamic_data` (uploaded
    headings that had no fixed column). This means a brand-new file that adds a
    heading automatically makes that heading searchable — no code change.
  * Understand synonyms, typos and Kannada / Romanized Kannada aliases by
    matching on normalized *tokens* (word sets), not exact phrases.
  * Provide ordered fallback chains and LABEL the chosen column honestly, so a
    general parent contact is shown as "Parent Contact Number", never passed off
    as the mother's number. When nothing suitable exists, the caller explains
    the value is unavailable instead of inventing rows.

Everything here is read-only and returns SQL *fragments* the query engine
embeds with parameterized values. Column/key identifiers are always validated
against the live schema before use, never taken raw from user text.
"""
from __future__ import annotations

import json
import re

from database import db_conn

# ─────────────────────────────────────────────────────────────────────────────
# Live schema discovery (cached per process; refreshed by invalidate_cache)
# ─────────────────────────────────────────────────────────────────────────────

_COLS_CACHE: list[str] | None = None
_DYN_CACHE: list[str] | None = None


def _real_columns() -> set[str]:
    """Actual column names on `students`, read live from MySQL."""
    global _COLS_CACHE
    if _COLS_CACHE is None:
        cols: set[str] = set()
        try:
            with db_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'students'"
                )
                cols = {str(r[0]).lower() for r in cur.fetchall()}
                cur.close()
        except Exception:
            cols = set()
        _COLS_CACHE = cols
    return _COLS_CACHE


def _dynamic_keys() -> set[str]:
    """Uploaded headings stored inside the dynamic_data JSON (field_registry)."""
    global _DYN_CACHE
    if _DYN_CACHE is None:
        keys: set[str] = set()
        try:
            with db_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT canonical_name FROM field_registry WHERE is_dynamic = 1"
                )
                keys = {str(r[0]).lower() for r in cur.fetchall()}
                cur.close()
        except Exception:
            keys = set()
        # Also fold in keys seen in stored JSON so a field is searchable even
        # if it predates the registry (best-effort, bounded sample).
        try:
            with db_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT dynamic_data FROM students WHERE dynamic_data IS NOT NULL "
                    "AND JSON_TYPE(dynamic_data) = 'OBJECT' LIMIT 500"
                )
                for (raw,) in cur.fetchall():
                    try:
                        parsed = json.loads(raw) if isinstance(raw, str) else raw
                        if isinstance(parsed, dict):
                            keys |= {str(k).lower() for k in parsed}
                    except Exception:
                        pass
                cur.close()
        except Exception:
            pass
        _DYN_CACHE = keys
    return _DYN_CACHE


def invalidate_cache() -> None:
    """Force a re-read after a new upload adds headings/columns."""
    global _COLS_CACHE, _DYN_CACHE
    _COLS_CACHE = None
    _DYN_CACHE = None


# ─────────────────────────────────────────────────────────────────────────────
# Token helpers — synonym / typo / multilingual tolerant matching
# ─────────────────────────────────────────────────────────────────────────────

def _tokens(name: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9\u0c00-\u0cff]+", str(name).lower()) if t}


# Alias groups: any member is treated as equivalent for token matching.
_GROUPS = {
    "mother": {"mother", "mothers", "mother_s", "maternal", "tayi", "thaye",
               "ತಾಯಿ", "ತಾಯಿಯ", "amma"},
    "father": {"father", "fathers", "father_s", "paternal", "tande", "thande",
               "nane", "ಅಪ್ಪ", "ತಂದೆ", "ನಾನೆ"},
    "parent": {"parent", "parents", "parent_s", "parents_s", "guardian",
               "guardians", "abhibhataka", "ಅಭಿವರ್ಧಕ", "parental"},
    "phone": {"phone", "mobile", "contact", "number", "no", "cell", "mahati",
              "mohathi", "ದೂರವಾಣಿ", "ಸಂಖ್ಯೆ", "fone"},
    "name": {"name", "nama", "ಹೆಸರು"},
    "occupation": {"occupation", "job", "work", "profession", "designation",
                   "vedike", "ವೃತ್ತಿ", "ಕೆಲಸ"},
}


def _group_of(token: str) -> str | None:
    """Return the canonical group ('mother'/'phone'/...) a token belongs to."""
    for canon, members in _GROUPS.items():
        if token in members or token.replace("_", "") in {m.replace("_", "") for m in members}:
            return canon
    return None


def _key_has(name: str, *canon_groups: str) -> bool:
    """True when every requested concept appears (as a synonym) in `name`."""
    toks = _tokens(name)
    grp = {g for g in (_group_of(t) for t in toks) if g}
    # direct-token allowance for things not in a group
    for c in canon_groups:
        if c not in grp and c not in toks:
            return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Field reference → SQL expression (validated against the live schema)
# ─────────────────────────────────────────────────────────────────────────────

_SAFE_ID = re.compile(r"^[a-z0-9_]+$")


def field_sql(ref: str) -> str | None:
    """SQL expression reading `ref` from the current row, or None if it is not a
    real column and not a registered dynamic key. `ref` must be a lowercase
    identifier; anything unsafe is rejected (never interpolated raw)."""
    if not _SAFE_ID.match(ref or ""):
        return None
    if ref in _real_columns():
        return f"s.`{ref}`"
    if ref in _dynamic_keys():
        return f"JSON_UNQUOTE(JSON_EXTRACT(s.dynamic_data, '$.\"{ref}\"'))"
    return None


def _candidates(prefer_real: list[str], semantic: tuple[str, ...]) -> list[tuple[str, str]]:
    """Ordered [(ref, label)] of fields that are PRESENT and satisfy `semantic`
    groups. `prefer_real` are fixed columns to try first; then any dynamic key
    whose tokens contain all semantic groups."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for ref, label in prefer_real:
        if ref in seen:
            continue
        if field_sql(ref):
            out.append((ref, label))
            seen.add(ref)
    for key in sorted(_dynamic_keys()):
        if key in seen or not _SAFE_ID.match(key):
            continue
        if semantic and _key_has(key, *semantic):
            out.append((key, None))  # label resolved by caller from the key
            seen.add(key)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Public resolvers for the spec's information needs
# ─────────────────────────────────────────────────────────────────────────────

class Resolution(dict):
    """dict that also reads like a small result object."""

    @property
    def available(self) -> bool:
        return bool(self.get("available"))

    @property
    def sql(self) -> str | None:
        return self.get("sql")

    @property
    def ref(self) -> str | None:
        return self.get("ref")

    @property
    def label(self) -> str | None:
        return self.get("label")

    @property
    def note(self) -> str:
        return self.get("note") or ""


def _unavailable(reason: str) -> Resolution:
    return Resolution(available=False, ref=None, sql=None, label=None,
                      note=reason, reason="unavailable")


def resolve_contact(subject: str) -> Resolution:
    """Resolve a contact-number need to the best PRESENT field, with the spec §2
    fallback rule:

      mother   → mother-specific field, else general parent/guardian contact
                 (labeled "Parent Contact Number"), else unavailable.
      father   → same, father-specific first.
      parent   → general parent/guardian contact, else either specific number.
      emergency→ emergency contact, else general parent contact.
      student  → the student's own phone.

    A general parent contact is only used as a fallback for mother/father and is
    always honestly labeled — never presented as the mother's/father's own
    number.
    """
    subject = (subject or "parent").strip().lower()

    # Preferred real columns + the general/fallback columns, per subject.
    chains: dict[str, list[tuple[str, str]]] = {
        "mother": [
            (["mother_phone", "mother_mobile", "mothers_phone", "mother_contact",
              "mother_number"], "Mother's Phone Number", ("mother", "phone")),
            (["parents_phone", "guardian_phone", "parent_phone"],
             "Parent Contact Number", ("parent", "phone")),
            (["emergency_contact_number"], "Emergency Contact", ("emergency",)),
        ],
        "father": [
            (["father_phone", "father_mobile", "fathers_phone", "father_contact",
              "father_number"], "Father's Phone Number", ("father", "phone")),
            (["parents_phone", "guardian_phone", "parent_phone"],
             "Parent Contact Number", ("parent", "phone")),
            (["emergency_contact_number"], "Emergency Contact", ("emergency",)),
        ],
        "parent": [
            (["parents_phone", "parent_phone", "guardian_phone", "family_phone"],
             "Parent Contact Number", ("parent", "phone")),
            (["mother_phone", "father_phone"], "Parent Contact Number", ("phone",)),
            (["emergency_contact_number"], "Emergency Contact", ("emergency",)),
        ],
        "guardian": [
            (["guardian_phone", "parents_phone", "parent_phone"],
             "Guardian Contact Number", ("parent", "phone")),
            (["emergency_contact_number"], "Emergency Contact", ("emergency",)),
        ],
        "emergency": [
            (["emergency_contact_number"], "Emergency Contact", ("emergency",)),
            (["parents_phone"], "Parent Contact Number", ("parent", "phone")),
        ],
        "student": [
            (["phone"], "Student Phone Number", ("phone",)),
            (["parents_phone"], "Parent Contact Number", ("parent", "phone")),
        ],
    }
    if subject not in chains:
        subject = "parent"

    for cols, fixed_label, semantic in chains[subject]:
        # 1) a real, present column from the ordered list
        for ref in cols:
            expr = field_sql(ref)
            if expr:
                return Resolution(available=True, ref=ref, sql=expr,
                                  label=fixed_label, note=_subject_note(subject, fixed_label))
        # 2) a dynamic heading (uploaded file) whose tokens carry the meaning
        for key in sorted(_dynamic_keys()):
            if not _SAFE_ID.match(key):
                continue
            if _matches_subject_phone(key, subject, semantic):
                expr = field_sql(key)
                if expr:
                    label = _dynamic_phone_label(key, subject, fixed_label)
                    return Resolution(available=True, ref=key, sql=expr,
                                      label=label, note=_subject_note(subject, label))
    return _unavailable(_missing_subject_message(subject))


def _subject_note(subject: str, label: str) -> str:
    general = label.startswith(("Parent", "Guardian", "Emergency"))
    if subject in ("mother", "father") and general:
        return (f"No {subject}-specific number is recorded; showing the general "
                f"{label}.")
    return ""


def _missing_subject_message(subject: str) -> str:
    if subject == "student":
        return "No student phone number field is available in the database."
    if subject in ("mother", "father"):
        return (f"No {subject} contact number and no general parent contact "
                "field are recorded for these students.")
    return "No parent/guardian contact number field is available in the database."


def _matches_subject_phone(key: str, subject: str, semantic: tuple[str, ...]) -> bool:
    """A dynamic heading qualifies when it is a phone field and its subject is
    compatible. Mother-specific keys count for 'mother'/'parent'; general parent
    keys count for everyone except a strictly-subject need that already failed."""
    toks = _tokens(key)
    grp = {g for g in (_group_of(t) for t in toks) if g}
    if "phone" not in grp:
        return False
    subject_groups = {"mother", "father", "parent"} & grp
    if subject in ("mother", "father"):
        # first chain pass only: subject-specific key
        return subject in grp
    if subject in ("parent", "guardian"):
        # general parent contact OR any parent-ish number
        return bool(subject_groups) or "parent" in grp
    if subject == "emergency":
        return "emergency" in toks or "emergency" in grp
    if subject == "student":
        # student's own number: a phone key not tied to a parent
        return not subject_groups
    return False


def _dynamic_phone_label(key: str, subject: str, chain_label: str) -> str:
    toks = _tokens(key)
    grp = {g for g in (_group_of(t) for t in toks) if g}
    if "mother" in grp:
        return "Mother's Phone Number"
    if "father" in grp:
        return "Father's Phone Number"
    if "emergency" in toks or "emergency" in grp:
        return "Emergency Contact"
    return chain_label  # e.g. Parent Contact Number / Guardian Contact Number


def detect_contact_subject(nq: str) -> str | None:
    """Return 'mother'/'father'/'parent'/'guardian'/'emergency'/'student' when
    the question asks for a contact number, else None. Possessive-aware,
    plural-aware, and Kannada/Romanized aware (operates on normalized tokens)."""
    text = (nq or "").lower()
    toks = _tokens(text)
    grp = {g for g in (_group_of(t) for t in toks) if g}
    phone_like = "phone" in grp or any(t in toks for t in
                 ("phone", "mobile", "contact", "number", "mahati", "ದೂರವಾಣಿ"))
    if not phone_like:
        return None
    if "emergency" in toks:
        return "emergency"
    # A specific-parent mention near the phone word decides the subject.
    has_mother = "mother" in grp
    has_father = "father" in grp
    has_parent = "parent" in grp or "guardian" in grp
    if has_mother and not has_father:
        return "mother"
    if has_father and not has_mother:
        return "father"
    if has_parent:
        return "parent"
    if has_mother and has_father:
        return "parent"
    # Bare "phone numbers"/"contact numbers" of students → student's own phone.
    if not (has_mother or has_father or has_parent):
        return "student"
    return "parent"


def detect_occupation_parent(nq: str) -> str | None:
    """Return 'mother'/'father'/'mother_occupation' column intent. Recognizes the
    keyword form ("father occupation", "mother's job is …") and the copula form
    ("mother is a teacher", "fathers are farmers"). Plural + possessive safe."""
    text = (nq or "").lower()
    # keyword form (singular, possessive or plural)
    if re.search(r"\b(?:mother(?:s|['’]s)?)\s*(?:'s)?\s*(?:occupation|job|work|profession|designation)\b", text):
        return "mother"
    if re.search(r"\bfather(?:s|['’]s)?\s*(?:'s)?\s*(?:occupation|job|work|profession|designation)\b", text):
        return "father"
    # copula form — "mother(s) is/are/work(s) as <value>"
    if re.search(r"\bmothers?\b[^.]*?\b(?:is|are|was|were|works?\s+as|working\s+as|do(?:es)?\s+as)\b", text):
        return "mother"
    if re.search(r"\bfathers?\b[^.]*?\b(?:is|are|was|were|works?\s+as|working\s+as|do(?:es)?\s+as)\b", text):
        return "father"
    return None


def known_query_terms() -> set[str]:
    """Extra words these resolvers can handle, so the 'could not map' guard must
    not reject a question merely because it contains them."""
    terms: set[str] = set()
    for members in _GROUPS.values():
        for m in members:
            terms |= {t for t in re.split(r"[^a-z]+", m) if t}
    terms |= {"teachers", "farmer", "farmers", "nurse", "doctors", "businessman"}
    return terms
