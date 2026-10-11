"""
Phase 5 — intent-based smart search using ACTUAL file headings (spec §2/§3/§5/§6).

Covers, with no dependence on which individual students are present in the real
database (expected answers are computed from the schema/heading logic itself):

  * heading-variation mapping: many synthetic Excel/CSV column names resolve to
    the same canonical field, and Father's Name is never confused with Father's
    Occupation (canonical_fields.map_column — a pure function).
  * multilingual intent detection (English / Kannada script / Romanized Kannada).
  * the resolver's fallback chains, driven by a CONTROLLED live-schema snapshot
    so we can deterministically prove: mother-specific number preferred when it
    exists; general parent contact used only as an honestly-labeled fallback; a
    clear "unavailable" explanation when no field exists; and that adding a brand
    new heading automatically becomes searchable without breaking existing ones.
  * end-to-end routing of the 8 spec example queries, plus the guard that a
    "without emergency contact" / multi-condition query is NOT hijacked into a
    bare contact listing (it stays a missing-value / compound query).

These tests only READ the live schema and inspect generated SQL — they never
insert, update or delete any production record.
"""
import unittest

import canonical_fields
import intent_fields
import report_service
from routes_query import build_deterministic_student_query


def _sql_blob(result):
    return " ".join([result.get("sql", "")] + [str(p) for p in result.get("params", [])])


# ─────────────────────────────────────────────────────────────────────────────
# 1. Heading-variation → canonical field (spec §2, §3, §6 "different headings")
# ─────────────────────────────────────────────────────────────────────────────
class HeadingMappingTests(unittest.TestCase):
    def _canon(self, raw):
        return canonical_fields.map_column(raw)[0]

    def test_mother_phone_heading_variations_all_map_to_mother_phone(self):
        for raw in [
            "Mother Phone", "Mother's Phone", "Mothers Phone Number",
            "mother mobile", "Mother Contact Number", "Mothers Mobile",
            "Tayi Mahati", "mother number", "Mother_s_Phone",
        ]:
            self.assertEqual(self._canon(raw), "mother_phone", msg=raw)

    def test_father_phone_heading_variations_all_map_to_father_phone(self):
        for raw in [
            "Father Phone", "Father's Mobile Number", "Fathers Contact Number",
            "father number", "Tande Mahati", "Father_s_Phone",
        ]:
            self.assertEqual(self._canon(raw), "father_phone", msg=raw)

    def test_general_parent_and_guardian_headings_map_to_parents_phone(self):
        for raw in [
            "Parents Phone", "Parent's Contact Number", "Guardian Phone",
            "Guardian Contact Number", "Abhibhataka Mahati", "Family Phone",
            "Parents Mobile Number",
        ]:
            self.assertEqual(self._canon(raw), "parents_phone", msg=raw)

    def test_father_name_is_never_mapped_to_father_occupation(self):
        # spec §3: "Father's Name" must never be mistaken for "Father's Occupation".
        self.assertEqual(self._canon("Father's Name"), "father_name")
        self.assertEqual(self._canon("Father Name"), "father_name")
        self.assertEqual(self._canon("Father Occupation"), "father_occupation")
        self.assertEqual(self._canon("Occupation of Father"), "father_occupation")
        self.assertNotEqual(self._canon("Father's Name"), "father_occupation")
        self.assertNotEqual(self._canon("Father Occupation"), "father_name")

    def test_mother_name_and_mother_occupation_stay_distinct(self):
        self.assertEqual(self._canon("Mother's Name"), "mother_name")
        self.assertEqual(self._canon("Mother Occupation"), "mother_occupation")
        self.assertEqual(self._canon("Mother's Profession"), "mother_occupation")

    def test_mapping_never_invents_a_field_for_an_unknown_heading(self):
        canon, mtype, _conf, _sugg = canonical_fields.map_column(
            "Entirely Made Up Column XYZ")
        # Unknown headings pass through (never silently guessed into a real field).
        self.assertEqual(mtype, "passthrough")
        self.assertNotIn(canon, {"mother_phone", "father_phone", "parents_phone"})


# ─────────────────────────────────────────────────────────────────────────────
# 2. Multilingual + possessive/plural intent detection (spec §1, §3, §6)
# ─────────────────────────────────────────────────────────────────────────────
class ContactSubjectDetectionTests(unittest.TestCase):
    def test_english_possessive_and_plural(self):
        self.assertEqual(intent_fields.detect_contact_subject(
            "give me the list of students' mother phone numbers"), "mother")
        self.assertEqual(intent_fields.detect_contact_subject(
            "show parents' contact numbers"), "parent")
        self.assertEqual(intent_fields.detect_contact_subject(
            "fathers mobile numbers"), "father")
        # "guardian" is a synonym of the parent group → resolved as a parent contact.
        self.assertEqual(intent_fields.detect_contact_subject(
            "guardian contact number"), "parent")
        self.assertEqual(intent_fields.detect_contact_subject(
            "emergency contact"), "emergency")

    def test_kannada_script_and_romanized(self):
        self.assertEqual(intent_fields.detect_contact_subject("ತಾಯಿ ದೂರವಾಣಿ"), "mother")
        self.assertEqual(intent_fields.detect_contact_subject("ತಂದೆ ದೂರವಾಣಿ"), "father")
        self.assertEqual(intent_fields.detect_contact_subject("ಅಭಿವರ್ಧಕ ಸಂಖ್ಯೆ"), "parent")
        self.assertEqual(intent_fields.detect_contact_subject("tayi mahati number"), "mother")
        self.assertEqual(intent_fields.detect_contact_subject("thande phone"), "father")

    def test_non_contact_questions_return_none(self):
        self.assertIsNone(intent_fields.detect_contact_subject("students from ajjampura"))
        self.assertIsNone(intent_fields.detect_contact_subject("O positive blood group"))
        self.assertIsNone(intent_fields.detect_contact_subject("highest cgpa 3rd semester"))


class OccupationIntentDetectionTests(unittest.TestCase):
    def test_copula_and_keyword_forms_plural_and_possessive(self):
        self.assertEqual(intent_fields.detect_occupation_parent(
            "list students whose father is a farmer"), "father")
        self.assertEqual(intent_fields.detect_occupation_parent(
            "find students whose mothers are teachers"), "mother")
        self.assertEqual(intent_fields.detect_occupation_parent(
            "father occupation"), "father")
        self.assertEqual(intent_fields.detect_occupation_parent(
            "mother's job"), "mother")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Resolver fallback chains — driven by a controlled live-schema snapshot.
#    We overwrite intent_fields' in-memory schema caches (restored in tearDown)
#    so the mother-preferred / parent-fallback / unavailable outcomes are
#    provable WITHOUT depending on the current production columns or rows.
# ─────────────────────────────────────────────────────────────────────────────
class ResolverFallbackTests(unittest.TestCase):
    def setUp(self):
        self._orig_cols = intent_fields._COLS_CACHE
        self._orig_dyn = intent_fields._DYN_CACHE

    def tearDown(self):
        intent_fields._COLS_CACHE = self._orig_cols
        intent_fields._DYN_CACHE = self._orig_dyn

    def _schema(self, real_cols=(), dynamic_keys=()):
        # Force everything through the dynamic-key path (real cols empty) so the
        # result depends only on the headings we declare present.
        intent_fields._COLS_CACHE = set(real_cols)
        intent_fields._DYN_CACHE = set(dynamic_keys)

    def test_mother_specific_number_is_preferred_when_available(self):
        self._schema(dynamic_keys={"mother_phone", "parents_phone"})
        res = intent_fields.resolve_contact("mother")
        self.assertTrue(res.available)
        self.assertEqual(res.ref, "mother_phone")
        self.assertEqual(res.label, "Mother's Phone Number")
        # A mother-specific number needs no fallback disclaimer.
        self.assertEqual(res.note, "")

    def test_general_parent_contact_used_only_as_labeled_fallback(self):
        self._schema(dynamic_keys={"parents_phone"})
        res = intent_fields.resolve_contact("mother")
        self.assertTrue(res.available)
        self.assertEqual(res.ref, "parents_phone")
        self.assertEqual(res.label, "Parent Contact Number")
        # Honest labeling: never passed off as the mother's own number.
        self.assertIn("No mother-specific", res.note)
        self.assertIn("Parent Contact Number", res.note)

    def test_father_falls_back_to_parent_contact_when_only_general_exists(self):
        self._schema(dynamic_keys={"parents_phone"})
        res = intent_fields.resolve_contact("father")
        self.assertTrue(res.available)
        self.assertEqual(res.label, "Parent Contact Number")
        self.assertIn("No father-specific", res.note)

    def test_emergency_contact_preferred_for_emergency_request(self):
        self._schema(dynamic_keys={"emergency_contact_number", "parents_phone"})
        res = intent_fields.resolve_contact("emergency")
        self.assertTrue(res.available)
        self.assertEqual(res.ref, "emergency_contact_number")

    def test_no_suitable_field_produces_clear_explanation(self):
        self._schema(dynamic_keys={"cgpa", "village"})  # no phone-ish heading
        res = intent_fields.resolve_contact("mother")
        self.assertFalse(res.available)
        self.assertIsNone(res.sql)
        self.assertIn("contact", res.note.lower())
        self.assertTrue(res.note)  # never an empty/invented answer

    def test_adding_a_new_heading_makes_it_searchable_without_breaking_others(self):
        # Before: only a general parent number exists → mother uses the fallback.
        self._schema(dynamic_keys={"parents_phone", "father_occupation"})
        before = intent_fields.resolve_contact("mother")
        self.assertEqual(before.ref, "parents_phone")

        # After a new upload adds a dedicated mother column, it wins automatically.
        intent_fields._DYN_CACHE = {"parents_phone", "mother_phone", "father_occupation"}
        after = intent_fields.resolve_contact("mother")
        self.assertEqual(after.ref, "mother_phone")
        # An unrelated field's resolution is unaffected by the new heading.
        self.assertEqual(intent_fields.resolve_contact("father").ref, "parents_phone")

    def test_invalidate_cache_clears_the_live_schema_snapshot(self):
        self._schema(dynamic_keys={"parents_phone"})
        intent_fields.invalidate_cache()
        self.assertIsNone(intent_fields._COLS_CACHE)
        self.assertIsNone(intent_fields._DYN_CACHE)

    def test_field_sql_never_interpolates_an_unsafe_identifier(self):
        self._schema(dynamic_keys={"parents_phone"})
        self.assertIsNone(intent_fields.field_sql("bad; DROP TABLE students--"))
        self.assertIsNone(intent_fields.field_sql("not_a_real_field"))
        self.assertIsNotNone(intent_fields.field_sql("parents_phone"))


# ─────────────────────────────────────────────────────────────────────────────
# 4. End-to-end routing of the 8 spec example queries + the no-hijack guard.
# ─────────────────────────────────────────────────────────────────────────────
class SpecExampleRoutingTests(unittest.TestCase):
    def test_mother_phone_listing_resolves_to_a_real_contact_column(self):
        r = build_deterministic_student_query(
            "Give me the list of students' mother phone numbers.")
        self.assertEqual(r["operation"], "select")
        blob = _sql_blob(r)
        self.assertTrue(
            any(tok in blob for tok in
                ("mother_phone", "parents_phone", "father_phone", "emergency_contact_number")),
            blob)
        self.assertNotIn("WHERE s.name", r["sql"])  # never guesses by student name

    def test_parents_contact_listing_is_a_contact_projection(self):
        r = build_deterministic_student_query("Show parents' contact numbers.")
        self.assertEqual(r["operation"], "select")
        self.assertTrue(
            any(tok in _sql_blob(r) for tok in
                ("parents_phone", "guardian_phone", "mother_phone", "father_phone")),
            _sql_blob(r))

    def test_father_farmer_uses_occupation_column_not_father_name(self):
        r = build_deterministic_student_query("List students whose father is a farmer.")
        self.assertIn("father_occupation", r["sql"])
        self.assertNotIn("father_name", r["sql"])
        self.assertIn("farmer", _sql_blob(r).lower())

    def test_mothers_teachers_uses_mother_occupation(self):
        r = build_deterministic_student_query("Find students whose mothers are teachers.")
        self.assertIn("mother_occupation", r["sql"])
        self.assertNotIn("mother_name", r["sql"])

    def test_blood_group_and_location_route_to_their_fields(self):
        blood = build_deterministic_student_query("List students with O positive blood group.")
        self.assertIn("blood_group", blood["sql"])

        location = build_deterministic_student_query("Show students from Ajjampura.")
        self.assertEqual(location["operation"], "select")
        # Taluk is one of the place columns searched and projected.
        self.assertTrue(any(tok in location["sql"] for tok in ("taluk", "village", "district", "address")))

    def test_highest_cgpa_semester_uses_academic_marks_table(self):
        r = build_deterministic_student_query(
            "Show students with the highest CGPA in the 3rd semester.")
        self.assertEqual(r["operation"], "select")
        # Academic value comes from the marks table, joined on the stable id.
        self.assertIn("marks", r["sql"])
        self.assertIn("s.usn", r["sql"])

    def test_discontinued_financial_routes_to_lifecycle(self):
        r = build_deterministic_student_query(
            "Find students who discontinued because of financial problems.")
        self.assertEqual(r["operation"], "select")
        self.assertIn("lifecycle_status", r["sql"])


class ContactColumnMaskingTests(unittest.TestCase):
    # The intent resolver labels a general parent contact as parent_contact_number;
    # a Staff user must not receive that number unmasked in an exported report.
    def test_parent_contact_alias_is_masked_for_staff(self):
        row = {"usn": "4HG23CS044", "name": "X Y", "parent_contact_number": "9620159179"}
        staff = report_service.mask_for_role(row, "Staff")
        self.assertNotEqual(staff["parent_contact_number"], "9620159179")
        self.assertTrue(staff["parent_contact_number"])  # masked, not deleted

    def test_admin_sees_full_contact_value(self):
        row = {"usn": "4HG23CS044", "name": "X Y", "parent_contact_number": "9620159179"}
        admin = report_service.mask_for_role(row, "Admin")
        self.assertEqual(admin["parent_contact_number"], "9620159179")


class NoHijackGuardTests(unittest.TestCase):
    def test_without_emergency_contact_stays_a_missing_value_query(self):
        r = build_deterministic_student_query("Show students without emergency contact")
        blob = r["sql"]
        self.assertIn("emergency_contact_number", blob)
        self.assertIn("IS NULL", blob)  # absence, not a contact listing
        # A bare contact listing would have empty params and an IS NOT NULL WHERE.
        self.assertNotIn("AS `emergency_contact`", blob)

    def test_compound_multi_filter_query_is_not_reduced_to_a_contact(self):
        r = build_deterministic_student_query(
            "lateral CS students in 7th semester having O+ blood group "
            "from rural areas without emergency contact"
        )
        params = [str(p) for p in r.get("params", [])]
        blob = " ".join(params)
        for expected in ("LATERAL ENTRY", "O+", "RURAL"):
            self.assertIn(expected, blob)
        self.assertIn("7", blob)
        self.assertIn("emergency_contact_number", r["sql"])
        self.assertIn("IS NULL", r["sql"])


if __name__ == "__main__":
    unittest.main()
