import unittest
from fastapi import HTTPException
from types import SimpleNamespace
from unittest.mock import Mock, patch

from query_security_validator import (
    create_confirmation_token,
    is_delete_all_request,
    is_delete_request,
    validate_sql_query,
    verify_confirmation_token,
)
from rag_sql_generator import _rule_based_fallback_sql, generate_sql_query
from routes_query import (
    ExecuteRequest,
    QueryRequest,
    _check_ambiguity,
    _classify_residence,
    _parse_update_assignments,
    _row_satisfies_filter_ast,
    _resolve_assignment,
    _validate_structured_update,
    build_deterministic_student_query,
    execute_confirmed,
    generate_query,
)
from kannada_processor import normalize_query
from auth import require_roles
from database import db_conn
from routes_files import _clear_cache, _latest_active_source, _write_provenance


class QuerySecurityValidatorTests(unittest.TestCase):
    def test_allows_select_for_staff_and_admin(self):
        query = {"operation": "select", "sql": "SELECT usn, name FROM students"}
        self.assertTrue(validate_sql_query(query, "Staff")["is_valid"])
        self.assertTrue(validate_sql_query(query, "Admin")["is_valid"])

    def test_rejects_stacked_statements_and_comments(self):
        stacked = "SELECT name FROM students; DELETE FROM students"
        commented = "SELECT name FROM students -- bypass"
        self.assertFalse(validate_sql_query(stacked, "Staff")["is_valid"])
        self.assertFalse(validate_sql_query(commented, "Staff")["is_valid"])

    def test_allows_exact_usn_update_with_comma_value(self):
        query = {
            "operation": "update",
            "sql": "UPDATE students SET address='Samudravalli, Vatehole, Alur, Hassan' "
            "WHERE usn='4HG23CS032'",
        }
        self.assertTrue(validate_sql_query(query, "Staff")["is_valid"])
        self.assertTrue(validate_sql_query(query, "Admin")["is_valid"])

    def test_rejects_updates_without_single_student_usn_filter(self):
        broad = "UPDATE students SET address='x' WHERE 1=1"
        injected = "UPDATE students SET address='x' WHERE usn='A' OR 1=1"
        self.assertFalse(validate_sql_query({"operation": "update", "sql": broad}, "Staff")["is_valid"])
        self.assertFalse(validate_sql_query({"operation": "update", "sql": injected}, "Staff")["is_valid"])

    def test_rejects_nonliteral_update_values_and_identity_mutation(self):
        injected_value = "UPDATE students SET name=CONCAT('a','b') WHERE usn='A'"
        identity = "UPDATE students SET usn='B' WHERE usn='A'"
        self.assertFalse(validate_sql_query({"operation": "update", "sql": injected_value}, "Staff")["is_valid"])
        self.assertFalse(validate_sql_query({"operation": "update", "sql": identity}, "Staff")["is_valid"])

    def test_rejects_mismatched_operation_role_escalation_and_unsafe_reads(self):
        mismatch = {"operation": "delete", "sql": "UPDATE students SET name='A' WHERE usn='A'"}
        staff_delete = {"operation": "delete", "sql": "DELETE FROM students WHERE usn='A'"}
        admin_delete = {"operation": "delete", "sql": "DELETE FROM students WHERE usn='A'"}
        outfile = {"operation": "select", "sql": "SELECT name FROM students INTO OUTFILE 'x'"}
        self.assertFalse(validate_sql_query(mismatch, "Staff")["is_valid"])
        self.assertFalse(validate_sql_query(staff_delete, "Staff")["is_valid"])
        self.assertTrue(validate_sql_query(admin_delete, "Admin")["is_valid"])
        self.assertFalse(validate_sql_query(outfile, "Staff")["is_valid"])

    def test_allows_student_insert_and_exact_usn_delete(self):
        insert = {
            "operation": "insert",
            "sql": "INSERT INTO students (usn, name) VALUES ('A', 'Student, Example')",
        }
        delete = {"operation": "delete", "sql": "DELETE FROM students WHERE usn='A'"}
        self.assertTrue(validate_sql_query(insert, "Staff")["is_valid"])
        self.assertTrue(validate_sql_query(insert, "Admin")["is_valid"])
        self.assertFalse(validate_sql_query(delete, "Staff")["is_valid"])
        self.assertIn("Admin", validate_sql_query(delete, "Staff")["reason"])
        self.assertTrue(validate_sql_query(delete, "Admin")["is_valid"])

    def test_rejects_unrestricted_and_database_wide_destructive_sql(self):
        statements = [
            "DELETE FROM students",
            "DELETE FROM students WHERE 1=1",
            "DELETE FROM students WHERE usn='A' OR 1=1",
            "DELETE s FROM students s JOIN marks m ON m.usn=s.usn WHERE s.usn='A'",
            "TRUNCATE TABLE students",
            "DROP TABLE students",
            "DROP DATABASE student_db",
        ]
        for statement in statements:
            with self.subTest(statement=statement):
                self.assertFalse(validate_sql_query(statement, "Admin")["is_valid"])
                self.assertFalse(validate_sql_query(statement, "Staff")["is_valid"])

    def test_detects_delete_all_requests_in_english_kannada_and_mixed_text(self):
        requests = [
            "Delete everything",
            "Remove all students",
            "Clear the database",
            "ಎಲ್ಲಾ ವಿದ್ಯಾರ್ಥಿಗಳನ್ನು ಅಳಿಸಿ",
            "ಎಲ್ಲಾ ಡೇಟಾವನ್ನು ಅಳಿಸಿ",
            "ಎಲ್ಲಾ ವಿದ್ಯಾರ್ಥಿಗಳನ್ನು ಡಿಲೀಟ್ ಮಾಡಿ",
            "database clean ಮಾಡಿ",
            "all students delete ಮಾಡಿ",
        ]
        for request in requests:
            with self.subTest(request=request):
                self.assertTrue(is_delete_all_request(request))
                self.assertTrue(is_delete_request(request))

    def test_distinguishes_selected_delete_from_delete_all(self):
        self.assertTrue(is_delete_request("Delete Manoj with USN 4HG23CS032"))
        self.assertFalse(is_delete_all_request("Delete Manoj with USN 4HG23CS032"))
        self.assertFalse(is_delete_request("Do not delete all students"))

    def test_confirmation_token_is_bound_to_user_query_and_expiry(self):
        query = {"operation": "delete", "sql": "DELETE FROM students WHERE usn='4HG23CS032'"}
        with patch(
            "query_security_validator.settings",
            SimpleNamespace(JWT_SECRET_KEY="test-signing-secret"),
        ):
            token = create_confirmation_token(query, "admin", issued_at=1000)
            self.assertTrue(verify_confirmation_token(token, query, "admin", now=1100))
            self.assertFalse(verify_confirmation_token(token, query, "staff", now=1100))
            self.assertFalse(verify_confirmation_token(
                token, {**query, "sql": "DELETE FROM students WHERE usn='OTHER'"}, "admin", now=1100
            ))
            self.assertFalse(verify_confirmation_token(token, query, "admin", now=1301))

    def test_staff_delete_is_blocked_before_sql_generation(self):
        user = {"username": "staff_user", "role": "Staff"}
        with patch("routes_query.write_audit_log"), patch(
            "routes_query.generate_sql_query", side_effect=AssertionError("SQL generation must not run")
        ):
            with self.assertRaises(HTTPException) as error:
                generate_query(QueryRequest(natural_query="Delete Manoj"), current_user=user)
        self.assertEqual(error.exception.status_code, 403)
        self.assertIn("Admin permission is required", error.exception.detail)

    def test_admin_delete_all_is_blocked_before_sql_generation(self):
        user = {"username": "admin_user", "role": "Admin"}
        with patch("routes_query.write_audit_log"), patch(
            "routes_query.generate_sql_query", side_effect=AssertionError("SQL generation must not run")
        ):
            with self.assertRaises(HTTPException) as error:
                generate_query(QueryRequest(natural_query="Delete all students"), current_user=user)
        self.assertEqual(error.exception.status_code, 403)
        self.assertIn("permanently blocked", error.exception.detail)

    def test_delete_execution_requires_confirmation_and_valid_token(self):
        query = {"operation": "delete", "sql": "DELETE FROM students WHERE usn='4HG23CS032'"}
        admin = {"username": "admin_user", "role": "Admin"}
        unconfirmed = ExecuteRequest(query_dict=query, original_query="Delete student")
        with self.assertRaises(HTTPException) as error:
            execute_confirmed(unconfirmed, current_user=admin)
        self.assertEqual(error.exception.status_code, 400)
        self.assertIn("confirm", error.exception.detail.lower())

        forged = ExecuteRequest(
            query_dict=query,
            original_query="Delete student",
            confirmed=True,
            confirmation_token="invalid",
        )
        with self.assertRaises(HTTPException) as error:
            execute_confirmed(forged, current_user=admin)
        self.assertEqual(error.exception.status_code, 403)

    def test_validates_client_submitted_structured_updates(self):
        update = {
            "operation": "update",
            "affected_usns": ["4HG23CS032"],
            "column_creations": [],
            "executions": [{
                "sql": "UPDATE students SET `address`=%s WHERE usn=%s",
                "params": ["Samudravalli, Vatehole, Alur, Hassan", "4HG23CS032"],
            }],
        }
        self.assertIsNone(_validate_structured_update(update))

        injected = {**update, "executions": [{
            "sql": "UPDATE students SET address='x'; DELETE FROM students WHERE 1=1",
            "params": ["x", "4HG23CS032"],
        }]}
        multiple_targets = {**update, "affected_usns": ["A", "B"]}
        injected_ddl = {**update, "column_creations": [{
            "table": "students", "column": "new_field", "data_type": "TEXT); DROP TABLE users;--",
        }]}
        self.assertIsNotNone(_validate_structured_update(injected))
        self.assertIsNotNone(_validate_structured_update(multiple_targets))
        self.assertIsNotNone(_validate_structured_update(injected_ddl))

    def test_location_and_rural_urban_fallbacks_use_address_only(self):
        location_query = _rule_based_fallback_sql("Search for students from Hassan")
        self.assertIsInstance(location_query, tuple)
        sql, params = location_query
        self.assertIn("s.address", sql)
        self.assertNotIn("s.region", sql)
        self.assertEqual(params, ["%hassan%"])

        rural_query = _rule_based_fallback_sql("Show rural students from Hassan")
        rural_sql, rural_params = rural_query
        self.assertIn("s.address", rural_sql)
        self.assertIn("s.area_type = 'RURAL'", rural_sql)
        self.assertEqual(rural_params, ["%hassan%"])

        urban_count = _rule_based_fallback_sql("How many urban students are there?")
        count_sql, count_params = urban_count
        self.assertIn("COUNT(*)", count_sql)
        self.assertIn("s.area_type = 'URBAN'", count_sql)
        self.assertEqual(count_params, [])

    def test_common_queries_use_local_fallback_without_gemini(self):
        with patch("rag_sql_generator._load_schema_context", return_value=""), patch(
            "rag_sql_generator.llm_service.generate_query", side_effect=AssertionError("Gemini called")
        ):
            result = generate_sql_query("Show all students", "Staff")
            self.assertTrue(result["success"])
            self.assertIn("FROM students", result["sql"])

        count_query = _rule_based_fallback_sql("How many students are there?")
        self.assertIn("COUNT(*)", count_query)

    def test_personal_detail_lookup_is_parameterized(self):
        query = _rule_based_fallback_sql("What is Karthik S L's father name?")
        sql, params = query
        self.assertEqual(sql.split(" FROM ", 1)[0], "SELECT s.`father_name`")
        self.assertEqual(params, ["Karthik S L"])

    def test_father_name_filter_supports_exact_list_and_count_queries(self):
        sql, params = _rule_based_fallback_sql("Show students whose father's name is Rajappa")
        self.assertIn("LOWER(TRIM(s.father_name))", sql)
        self.assertNotIn("s.name LIKE", sql)
        self.assertEqual(params, ["Rajappa"])

        count_sql, count_params = _rule_based_fallback_sql(
            "How many students have father name Ramesh?"
        )
        self.assertIn("COUNT(*)", count_sql)
        self.assertIn("s.father_name", count_sql)
        self.assertEqual(count_params, ["Ramesh"])

    def test_blood_group_filter_canonicalizes_positive_and_or_values(self):
        count_query = build_deterministic_student_query("How many students have blood group O positive?")
        self.assertIn("SELECT COUNT(*)", count_query["sql"])
        self.assertIn("REPLACE(UPPER(COALESCE(s.blood_group", count_query["sql"])
        self.assertEqual(count_query["params"], ["O+"])

        list_query = build_deterministic_student_query("Show O+ students")
        self.assertIn("s.blood_group", list_query["sql"])
        self.assertEqual(list_query["params"], ["O+"])

        or_query = build_deterministic_student_query("Show students with O+ or A+ blood group")
        self.assertIn(" IN (%s, %s)", or_query["sql"])
        self.assertEqual(or_query["params"], ["O+", "A+"])

    def test_blood_group_inequality_is_not_a_missing_value_query(self):
        not_o_positive = build_deterministic_student_query(
            "students who do not have O+ blood group"
        )
        condition = next(
            item for item in not_o_positive["ast"]["conditions"] if item["field"] == "blood_group"
        )
        self.assertEqual(condition["operator"], "NOT_IN")
        self.assertIn("IS NOT NULL", condition["sql"])
        self.assertNotIn("IS NULL", condition["sql"])

        missing = build_deterministic_student_query("students whose blood group is null")
        missing_condition = next(
            item for item in missing["ast"]["conditions"] if item["field"] == "blood_group"
        )
        self.assertEqual(missing_condition["operator"], "MISSING")

    def test_residence_classifier_uses_only_approved_markers(self):
        self.assertEqual(_classify_residence("XYZ Village (V)", "", ""), "RURAL")
        self.assertEqual(_classify_residence("XYZ (v)", "", ""), "RURAL")
        self.assertEqual(_classify_residence("Avenue V", "", ""), None)
        self.assertEqual(_classify_residence("Village Road", "URBAN", ""), "URBAN")

    def test_missing_and_present_filters_use_the_authoritative_table(self):
        for field, phrase in (
            ("phone", "without phone"),
            ("blood_group", "without blood group"),
            ("cgpa", "without CGPA"),
            ("sgpa", "without SGPA"),
            ("emergency_contact_number", "without emergency contact"),
        ):
            with self.subTest(field=field):
                result = build_deterministic_student_query(f"students {phrase}")
                condition = next(item for item in result["ast"]["conditions"] if item["field"] == field)
                self.assertEqual(condition["operator"], "MISSING")
                if field == "sgpa":
                    self.assertIn("FROM marks m", condition["sql"])
                    self.assertNotIn("s.`sgpa`", condition["sql"])

        present_sgpa = build_deterministic_student_query("students with SGPA present")
        sgpa_condition = next(item for item in present_sgpa["ast"]["conditions"] if item["field"] == "sgpa")
        self.assertEqual(sgpa_condition["operator"], "PRESENT")
        self.assertIn("FROM marks m", sgpa_condition["sql"])

    def test_filterless_count_is_not_poisoned_by_meta_filler(self):
        # "in the database/system/table" is meta-filler, not a location filter.
        # A staff user asking how many students exist must get a real COUNT(*),
        # never a spurious LIKE '%the database%' that answers 0.
        for phrase in (
            "show the total number of students in the database",
            "count the students in the system",
            "number of students in the database",
        ):
            with self.subTest(phrase=phrase):
                result = build_deterministic_student_query(phrase)
                self.assertIsNotNone(result, phrase)
                self.assertIn("SELECT COUNT(*) AS total_students FROM students s", result["sql"])
                self.assertNotIn("LIKE", result["sql"].upper())
                self.assertNotIn("location", [c["field"] for c in result["ast"]["conditions"]])
                self.assertEqual(result["params"], [])

    def test_ranking_without_other_filter_is_deterministic(self):
        # A filter-less "top/bottom N by CGPA" must be handled here, not fall to
        # the non-deterministic LLM (which mis-parses "top" as a student name).
        top = build_deterministic_student_query("show the top 5 students by CGPA")
        self.assertIsNotNone(top)
        self.assertIn("IS NOT NULL", top["sql"])
        self.assertRegex(top["sql"], r"ORDER BY.*DESC")
        self.assertTrue(top["sql"].rstrip().endswith("LIMIT 5"))

        bottom = build_deterministic_student_query("bottom 3 students by cgpa")
        self.assertIsNotNone(bottom)
        self.assertIn("IS NOT NULL", bottom["sql"])
        self.assertRegex(bottom["sql"], r"ORDER BY.*ASC")
        self.assertTrue(bottom["sql"].rstrip().endswith("LIMIT 3"))

    def test_projection_present_operator_does_not_reject_rows(self):
        # "with their blood group and current semester" is a projection request;
        # it compiles to PRESENT filters, and the row verifier must not crash on
        # the null-valued PRESENT condition nor reject valid projected rows.
        from routes_query import _row_satisfies_filter_ast
        result = build_deterministic_student_query(
            "list students with their blood group and current semester")
        self.assertIsNotNone(result)
        ops = {c["field"]: c["operator"] for c in result["ast"]["conditions"]}
        self.assertEqual(ops.get("blood_group"), "PRESENT")
        self.assertEqual(ops.get("current_sem"), "PRESENT")
        good = {"usn": "4HG23CS003", "name": "X", "blood_group": "B+", "current_sem": 7}
        self.assertTrue(_row_satisfies_filter_ast(good, result["ast"]))
        bad = {"usn": "4HG23CS004", "name": "Y", "blood_group": "", "current_sem": 7}
        self.assertFalse(_row_satisfies_filter_ast(bad, result["ast"]))

    def test_plural_name_list_uses_like_not_exact_match(self):
        # "students named Rahul" must list every Rahul* (LIKE), not exact-match
        # the lone word (the LLM path returns 0 for stored "Rahul Sharma").
        result = build_deterministic_student_query("find students named rahul")
        self.assertIsNotNone(result)
        cond = next(c for c in result["ast"]["conditions"] if c["field"] == "name")
        self.assertEqual(cond["operator"], "CONTAINS")
        self.assertEqual(cond["params"], ["%rahul%"])
        self.assertIn("LIKE", result["sql"])
        # A father-name query must NOT be mis-captured as a bare student-name filter.
        father = build_deterministic_student_query("students whose father name is ramesh")
        if father:
            self.assertNotIn("name", {c["field"] for c in father["ast"]["conditions"]})

    def test_spelled_semester_word_resolves_to_current_sem_filter(self):
        # Staff spell the semester out ("semester three"); it must resolve to the
        # authoritative current_sem filter, not fall through to a name search.
        result = build_deterministic_student_query(
            "list all students studying in semester three")
        self.assertIsNotNone(result)
        cond = next(
            (c for c in result["ast"]["conditions"] if c["field"] == "current_sem"), None)
        self.assertIsNotNone(cond)
        self.assertEqual(cond["value"], 3)

    def test_update_target_field_strip_descriptor_and_article(self):
        # "Update the address of student <USN>" must not glue the descriptor word
        # onto the USN, and must not keep the leading article in the field name.
        from routes_query import _extract_target_and_field, _clean_update_target
        target, field = _extract_target_and_field("the address of student 4HG23CS032")
        self.assertEqual(field, "address")
        self.assertEqual(_clean_update_target(target), "4HG23CS032")
        self.assertEqual(_clean_update_target("the student with USN 4HG23CS032"), "4HG23CS032")
        self.assertEqual(_clean_update_target("Rahul Sharma"), "Rahul Sharma")

    def test_spelled_number_ranking_applies_limit(self):
        # "five students with the highest CGPA" must apply LIMIT 5 (not fall
        # through to unbounded order-by). "top/first/last" spelled variants too.
        from routes_query import _detect_rank_limit
        self.assertEqual(_detect_rank_limit("who are the five students with the highest cgpa"), 5)
        self.assertEqual(_detect_rank_limit("show top ten students by cgpa"), 10)
        self.assertEqual(_detect_rank_limit("bottom three students by cgpa"), 3)
        self.assertIsNone(_detect_rank_limit("show students with cgpa minimum 7"))
        self.assertIsNone(_detect_rank_limit("show students from cse branch"))
        built = build_deterministic_student_query(
            "who are the five students with the highest cgpa")
        self.assertIsNotNone(built)
        self.assertIn("LIMIT 5", built["sql"])
        self.assertEqual(built["ast"]["intent"], "TOP")

    def test_father_name_projection_is_not_a_comma_or_of_filter(self):
        # "father name" appearing as a projection item (followed by a comma, or an
        # "of <subject>" lookup) must never become a father_name = ',' / 'of ravi'
        # equality filter — those produced spurious 0-row answers.
        comma = build_deterministic_student_query(
            "show the name, usn, father name, and cgpa of all students")
        if comma is not None:
            self.assertNotIn(",", comma["params"])
            for cond in comma["ast"]["conditions"]:
                self.assertNotEqual(cond.get("value"), ",")
        of_subject = build_deterministic_student_query("father name of ravi")
        if of_subject is not None:
            for cond in of_subject["ast"]["conditions"]:
                self.assertNotEqual(cond.get("field"), "father_name")

        # A real value with an explicit connector must still build the filter.
        genuine = build_deterministic_student_query("students whose father name is rudrappa")
        self.assertIsNotNone(genuine)
        fields = {c["field"] for c in genuine["ast"]["conditions"]}
        self.assertIn("father_name", fields)
        self.assertIn("rudrappa", genuine["params"])

    def test_occupation_typo_and_copula_route_to_occupation_data(self):
        # Simple mistakes must still resolve to the intent: "occcupation" (typo)
        # and "father is teacher" (no keyword) both mean father_occupation, and
        # the rows must equal hand-written DB truth — never a father_name filter.
        from routes_query import _fix_occupation_typos
        self.assertEqual(_fix_occupation_typos("father occcupation is teacher"),
                         "father occupation is teacher")
        # Same-suffix lookalikes must NOT be rewritten.
        self.assertEqual(_fix_occupation_typos("students from this location"),
                         "students from this location")

        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT usn FROM students "
                "WHERE REPLACE(LOWER(father_occupation),' ','') LIKE '%teacher%'")
            truth = sorted(str(r[0]) for r in cur.fetchall())
            cur.close()
        self.assertGreater(len(truth), 0, "fixture DB must contain teacher fathers")

        for q in ("students whose father occcupation is teacher",
                  "students whose father is teacher",
                  "students whose father works as a teacher"):
            built = build_deterministic_student_query(q)
            self.assertIsNotNone(built, q)
            self.assertIn("father_occupation", built["sql"], q)
            self.assertNotIn("father_name", built["sql"], q)
            with db_conn() as conn:
                cur = conn.cursor()
                cur.execute(built["sql"], tuple(built["params"]))
                got = sorted(str(r[0]) for r in cur.fetchall())
                cur.close()
            self.assertEqual(got, truth, q)

    def test_father_is_real_person_name_is_not_routed_to_occupation(self):
        # The copula route is data-gated: a value that exists as a parent NAME
        # must keep using father_name, never occupation.
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT father_name FROM students WHERE father_name IS NOT NULL "
                        "AND TRIM(father_name) <> '' LIMIT 1")
            row = cur.fetchone()
            cur.close()
        self.assertIsNotNone(row)
        name = str(row[0]).split()[0].lower()
        built = build_deterministic_student_query(f"students whose father is {name}")
        if built is not None:
            self.assertNotIn("father_occupation", built["sql"])

    def test_complex_filter_combines_all_requested_conditions(self):
        query = (
            "Show rural CS students with O+ blood group, aged 21 in 3rd semester "
            "with CGPA above 8 and father name Rajappa from Ajjampura"
        )
        result = build_deterministic_student_query(query)
        sql = result["sql"]
        self.assertIn("s.area_type", sql)
        self.assertIn("s.branch", sql)
        self.assertIn("s.blood_group", sql)
        self.assertIn("TIMESTAMPDIFF(YEAR, s.dob, CURDATE()) = %s", sql)
        self.assertIn("AS current_sem", sql)
        self.assertIn("s.father_name", sql)
        self.assertIn("s.address", sql)
        self.assertIn("AVG(m.sgpa)", sql)
        self.assertEqual(result["params"][-1], "%ajjampura%")
        expected_fields = {
            "rural_status", "branch", "blood_group", "age", "current_sem",
            "cgpa", "father_name", "location",
        }
        self.assertEqual({item["field"] for item in result["ast"]["conditions"]}, expected_fields)
        for condition in result["ast"]["conditions"]:
            self.assertIn(condition["sql"], sql)

        matching_row = {
            "usn": "4HG24CS401", "name": "Student", "branch": "CS",
            "blood_group": "O+", "area_type": "RURAL", "region": "",
            "address": "Ajjampura", "village": "Ajjampura Village",
            "district": "Hassan", "current_sem": 3, "age": 21,
            "cgpa": 8.5, "father_name": "Rajappa",
        }
        self.assertTrue(_row_satisfies_filter_ast(matching_row, result["ast"]))
        self.assertFalse(_row_satisfies_filter_ast({**matching_row, "cgpa": 7.5}, result["ast"]))

    def test_lateral_multi_filters_are_preserved_without_branch_or_broadening(self):
        lateral_only = build_deterministic_student_query("list lateral students")
        self.assertIsNotNone(lateral_only)
        self.assertIn("LATERAL ENTRY", lateral_only["params"])
        self.assertIn("NULLIF(UPPER(TRIM(s.student_type))", lateral_only["sql"])
        self.assertIn("RIGHT(s.usn, 3)", lateral_only["sql"])
        self.assertTrue(validate_sql_query(lateral_only, "Staff")["is_valid"])

        for alias in ("LE students", "direct second year students", "direct 2nd year students"):
            with self.subTest(alias=alias):
                alias_query = build_deterministic_student_query(f"list {alias}")
                self.assertIn("LATERAL ENTRY", alias_query["params"])

        lateral_semester = build_deterministic_student_query("list lateral students 7th sem")
        self.assertIn("LATERAL ENTRY", lateral_semester["params"])
        self.assertIn("AS current_sem", lateral_semester["sql"])
        self.assertEqual(lateral_semester["params"][-1], 7)

        lateral_semester_branch = build_deterministic_student_query(
            "list lateral students 7th sem CS branch"
        )
        self.assertIn("LATERAL ENTRY", lateral_semester_branch["params"])
        self.assertIn("AS current_sem", lateral_semester_branch["sql"])
        self.assertIn("s.branch", lateral_semester_branch["sql"])
        self.assertNotIn("year_and_branch LIKE", lateral_semester_branch["sql"])
        self.assertNotIn(" OR ", lateral_semester_branch["sql"])

        with self.assertRaisesRegex(HTTPException, "could not map: scholarship"):
            build_deterministic_student_query("lateral CS students with scholarship")

    def test_year_queries_are_translated_to_current_year_filter(self):
        year_query = build_deterministic_student_query("list the students from 3rd year")
        self.assertIsNotNone(year_query)
        self.assertIn("AS current_year", year_query["sql"])
        self.assertEqual(year_query["params"][-1], 3)
        self.assertEqual(year_query["ast"]["conditions"][-1]["field"], "current_year")

        sem_query = build_deterministic_student_query("students studying in 5th sem")
        self.assertIsNotNone(sem_query)
        self.assertIn("AS current_sem", sem_query["sql"])
        self.assertEqual(sem_query["params"][-1], 5)

    def test_rural_blood_semester_and_missing_contact_are_all_applied(self):
        rural = build_deterministic_student_query(
            "students from rural having blood group O+ in 4th sem"
        )
        self.assertIn("s.blood_group", rural["sql"])
        self.assertIn("s.area_type", rural["sql"])
        self.assertIn("RURAL", rural["params"])
        self.assertIn("AS current_sem", rural["sql"])
        self.assertNotIn("%rural having%", rural["params"])
        self.assertIn("O+", rural["params"])
        self.assertIn(4, rural["params"])

        long_query = build_deterministic_student_query(
            "lateral CS students in 7th semester having O+ blood group from rural areas "
            "without emergency contact"
        )
        for expected in ("LATERAL ENTRY", "O+", 7):
            self.assertIn(expected, long_query["params"])
        self.assertIn("emergency_contact_number", long_query["sql"])
        self.assertIn("s.area_type", long_query["sql"])
        self.assertIn("RURAL", long_query["params"])
        self.assertNotIn("%rural areas without emergency contact%", long_query["params"])
        self.assertIn("O+", long_query["params"])
        blood_condition = next(item for item in long_query["ast"]["conditions"] if item["field"] == "blood_group")
        self.assertEqual(blood_condition["operator"], "IN")

        five_filters = build_deterministic_student_query(
            "lateral CS students 7th semester with O+ blood group from rural area"
        )
        self.assertEqual(
            {item["field"] for item in five_filters["ast"]["conditions"]},
            {"student_type", "branch", "current_sem", "blood_group", "rural_status"},
        )

    def test_query_ast_and_result_validation_enforce_every_lateral_filter(self):
        query = build_deterministic_student_query(
            "lateral CS students in 7th semester having O+ blood group from rural areas "
            "without emergency contact"
        )
        expected = {
            "student_type", "branch", "current_sem", "blood_group",
            "rural_status", "emergency_contact_number",
        }
        self.assertEqual(
            {condition["field"] for condition in query["ast"]["conditions"]},
            expected,
        )
        for condition in query["ast"]["conditions"]:
            self.assertIn(condition["sql"], query["sql"])

        lateral = {
            "usn": "4HG24CS401", "student_type": "Lateral Entry", "branch": "CS",
            "current_sem": 7, "blood_group": "O+", "area_type": "",
            "region": "", "address": "XYZ Village (V)", "village": "XYZ",
            "emergency_contact_number": None,
        }
        self.assertTrue(_row_satisfies_filter_ast(lateral, query["ast"]))
        self.assertFalse(
            _row_satisfies_filter_ast(
                {**lateral, "usn": "4HG23CS001", "student_type": "Regular"}, query["ast"]
            )
        )
        self.assertFalse(_row_satisfies_filter_ast({**lateral, "current_sem": 6}, query["ast"]))
        self.assertFalse(
            _row_satisfies_filter_ast({**lateral, "student_type": "Regular"}, query["ast"])
        )

        missing_blood = build_deterministic_student_query(
            "rural students in 4th semester without blood group"
        )
        blood_condition = next(
            item for item in missing_blood["ast"]["conditions"] if item["field"] == "blood_group"
        )
        self.assertEqual(blood_condition["operator"], "MISSING")

    def test_count_and_top_retain_all_requested_ast_conditions(self):
        count = build_deterministic_student_query("how many lateral CS students are in 7th semester")
        top = build_deterministic_student_query("top 10 lateral CS students in 7th semester by CGPA")
        expected = {"student_type", "branch", "current_sem"}
        self.assertEqual(count["ast"]["intent"], "COUNT")
        self.assertEqual(top["ast"]["intent"], "TOP")
        self.assertIn("LIMIT 10", top["sql"])
        self.assertEqual({item["field"] for item in count["ast"]["conditions"]}, expected)
        self.assertEqual({item["field"] for item in top["ast"]["conditions"]}, expected)

        comparison = build_deterministic_student_query(
            "lateral CS students in 7th semester with CGPA above 8 and O+ blood group"
        )
        comparison_fields = {item["field"] for item in comparison["ast"]["conditions"]}
        self.assertEqual(comparison_fields, {"student_type", "branch", "current_sem", "cgpa", "blood_group"})
        self.assertIn("GREATER_THAN", {item["operator"] for item in comparison["ast"]["conditions"]})

        normalized, _ = normalize_query("7ನೇ ಸೆಮಿಸ್ಟರ್‌ನಲ್ಲಿ ಇರುವ ಲ್ಯಾಟರಲ್ CS ವಿದ್ಯಾರ್ಥಿಗಳನ್ನು ತೋರಿಸಿ")
        kannada = build_deterministic_student_query(normalized)
        self.assertEqual(
            {item["field"] for item in kannada["ast"]["conditions"]},
            {"student_type", "branch", "current_sem"},
        )

        mixed_normalized, _ = normalize_query(
            "7th sem CS ವಿದ್ಯಾರ್ಥಿಗಳಲ್ಲಿ lateral students ತೋರಿಸಿ"
        )
        mixed = build_deterministic_student_query(mixed_normalized)
        self.assertEqual(
            {item["field"] for item in mixed["ast"]["conditions"]},
            {"student_type", "branch", "current_sem"},
        )

        branch_semester = build_deterministic_student_query("CS students in 7th semester")
        self.assertEqual(
            {item["field"] for item in branch_semester["ast"]["conditions"]},
            {"branch", "current_sem"},
        )

        variants = [
            "lateral CS 7th semester students",
            "7th semester CS lateral students",
            "CS lateral students in 7th semester",
            "students who are lateral entry and belong to CS branch and are currently studying in 7th semester",
        ]
        for query in variants:
            with self.subTest(query=query):
                variant = build_deterministic_student_query(query)
                self.assertEqual(
                    {item["field"] for item in variant["ast"]["conditions"]},
                    {"student_type", "branch", "current_sem"},
                )

        long_query = build_deterministic_student_query(
            "lateral entry CS students in 7th semester with O+ blood group from rural areas "
            "without emergency contact, CGPA above 7, and whose father's name is available "
            "and female and without phone"
        )
        self.assertEqual(
            {item["field"] for item in long_query["ast"]["conditions"]},
            {
                "student_type", "branch", "current_sem", "blood_group", "rural_status",
                "emergency_contact_number", "cgpa", "father_name", "gender", "phone",
            },
        )
        father_condition = next(item for item in long_query["ast"]["conditions"] if item["field"] == "father_name")
        self.assertEqual(father_condition["operator"], "PRESENT")

    def test_age_ranges_are_inclusive_and_derived_from_dob(self):
        result = build_deterministic_student_query("How many students are aged between 20 and 22?")
        self.assertIn("TIMESTAMPDIFF(YEAR, s.dob, CURDATE()) BETWEEN %s AND %s", result["sql"])
        self.assertEqual(result["params"], [20, 22])

        inclusive = build_deterministic_student_query("Show students aged 21 or above")
        self.assertIn("TIMESTAMPDIFF(YEAR, s.dob, CURDATE()) >= %s", inclusive["sql"])
        self.assertEqual(inclusive["params"], [21])

    def test_count_and_list_and_missing_existence_queries(self):
        both = build_deterministic_student_query(
            "How many O+ students are there and show their names and USNs"
        )
        self.assertIn("COUNT(*) OVER() AS total_count", both["sql"])
        self.assertIn("s.name", both["sql"])
        self.assertIn("s.usn", both["sql"])

        missing = build_deterministic_student_query("Show students without emergency contact")
        self.assertIn("emergency_contact_number", missing["sql"])
        self.assertIn("IS NULL", missing["sql"])

        present = build_deterministic_student_query("Which students have phone numbers?")
        self.assertIn("phone", present["sql"])
        self.assertIn("IS NOT NULL", present["sql"])

    def test_filter_queries_pass_sql_validation(self):
        query = build_deterministic_student_query(
            "Show rural CS students with O+ blood group aged 21 in 3rd semester "
            "with CGPA above 8 and father name Rajappa"
        )
        validation = validate_sql_query(query, "Staff")
        self.assertTrue(validation["is_valid"], validation["reason"])

    def test_deterministic_filter_runs_through_existing_query_route(self):
        user = {"username": "staff_user", "role": "Staff"}
        row = {"usn": "4HG23CS032", "name": "Manoj", "blood_group": "O+"}
        with patch("routes_query._get_cache", return_value=(None, None)), \
             patch("routes_query._run_query", return_value=[row]) as run_query, \
             patch("routes_query._log_history"), \
             patch("routes_query.write_audit_log"), \
             patch("routes_query._apply_dynamic_student_fields", side_effect=lambda rows, intent=None, semester_filtered=False: rows), \
             patch("routes_query._check_ambiguity", return_value=None), \
             patch("routes_query._set_cache"), \
             patch("routes_query.generate_sql_query", side_effect=AssertionError("LLM should not run")):
            response = generate_query(QueryRequest(natural_query="Show O+ students", debug=True), current_user=user)
            normal_response = generate_query(QueryRequest(natural_query="Show O+ students"), current_user=user)

        self.assertIn("s.blood_group", response["query"])
        self.assertIn("query_debug", response)
        self.assertIsNone(normal_response["query"])
        self.assertNotIn("query_debug", normal_response)
        self.assertEqual(response["data"], [row])
        self.assertTrue(run_query.called)

    def test_count_and_list_route_returns_total_and_rows(self):
        user = {"username": "staff_user", "role": "Staff"}
        rows = [
            {"total_count": 2, "usn": "4HG23CS001", "name": "One", "blood_group": "O+"},
            {"total_count": 2, "usn": "4HG23CS002", "name": "Two", "blood_group": "O+"},
        ]
        with patch("routes_query._get_cache", return_value=(None, None)), \
             patch("routes_query._run_query", return_value=rows), \
             patch("routes_query._log_history"), \
             patch("routes_query.write_audit_log"), \
             patch("routes_query._apply_dynamic_student_fields", side_effect=lambda result, intent=None, semester_filtered=False: result), \
             patch("routes_query._check_ambiguity", return_value=None), \
             patch("routes_query._enrich_with_profile", side_effect=lambda result, nq, intent: result), \
             patch("routes_query._filter_by_intent", side_effect=lambda result, intent, nq: result), \
             patch("routes_query._set_cache"), \
             patch("routes_query.generate_sql_query", side_effect=AssertionError("LLM should not run")):
            response = generate_query(
                QueryRequest(natural_query="How many O+ students are there and show their names and USNs"),
                current_user=user,
            )

        self.assertEqual(response["total_count"], 2)
        self.assertFalse(response["is_scalar_number"])
        self.assertEqual([row["name"] for row in response["data"]], ["One", "Two"])
        self.assertNotIn("total_count", response["data"][0])

    def test_role_dependency_is_case_insensitive_and_denies_other_roles(self):
        admin_guard = require_roles("Admin")
        self.assertEqual(admin_guard({"username": "admin", "role": "admin"})["role"], "admin")
        with self.assertRaises(HTTPException) as error:
            admin_guard({"username": "staff", "role": "Staff"})
        self.assertEqual(error.exception.status_code, 403)

    def test_provenance_write_failures_propagate_to_import_transaction(self):
        cursor = Mock()
        cursor.execute.side_effect = RuntimeError("provenance table unavailable")
        with self.assertRaisesRegex(RuntimeError, "provenance table unavailable"):
            _write_provenance(cursor, "4HG23CS032", "address", "New Address", "new.csv", 12)

    def test_file_delete_selects_newest_remaining_provenance(self):
        cursor = Mock()
        cursor.fetchone.return_value = {"field_value": "Old Address"}
        result = _latest_active_source(cursor, "4HG23CS032", "address", "new.csv")
        query, params = cursor.execute.call_args.args
        self.assertEqual(result["field_value"], "Old Address")
        self.assertIn("ORDER BY uploaded_at DESC, id DESC", query)
        self.assertEqual(params, ("4HG23CS032", "address", "new.csv"))

    def test_cache_invalidation_failure_is_not_silently_ignored(self):
        cursor = Mock()
        cursor.execute.side_effect = RuntimeError("query cache unavailable")
        connection = Mock()
        connection.cursor.return_value = cursor
        with self.assertRaisesRegex(RuntimeError, "query cache unavailable"):
            _clear_cache(connection)
        cursor.close.assert_called_once_with()

    def test_kannada_blood_group_query_uses_the_same_filter(self):
        normalized, _ = normalize_query("O+ ರಕ್ತದ ಗುಂಪಿನ ವಿದ್ಯಾರ್ಥಿಗಳನ್ನು ತೋರಿಸಿ")
        result = build_deterministic_student_query(normalized)
        self.assertIsNotNone(result)
        self.assertIn("s.blood_group", result["sql"])
        self.assertEqual(result["params"], ["O+"])

        age_query, _ = normalize_query("21 ವರ್ಷದ ವಿದ್ಯಾರ್ಥಿಗಳನ್ನು ತೋರಿಸಿ")
        age_result = build_deterministic_student_query(age_query)
        self.assertIn("TIMESTAMPDIFF(YEAR, s.dob, CURDATE()) = %s", age_result["sql"])
        self.assertEqual(age_result["params"], [21])

        rural_query, _ = normalize_query("ಗ್ರಾಮೀಣ CS ವಿದ್ಯಾರ್ಥಿಗಳನ್ನು ತೋರಿಸಿ")
        rural_result = build_deterministic_student_query(rural_query)
        self.assertIn("s.area_type", rural_result["sql"])

        father_query, _ = normalize_query("ರಾಜಪ್ಪ ಅವರ ತಂದೆ ಹೆಸರಿರುವ ವಿದ್ಯಾರ್ಥಿಗಳನ್ನು ತೋರಿಸಿ")
        father_result = build_deterministic_student_query(father_query)
        self.assertIn("s.father_name", father_result["sql"])
        self.assertIn("ರಾಜಪ್ಪ", father_result["params"])

    def test_location_results_never_trigger_name_ambiguity(self):
        rows = [
            {"usn": "4HG23CS001", "name": "First Student"},
            {"usn": "4HG23CS002", "name": "Second Student"},
        ]
        self.assertIsNone(_check_ambiguity(rows, "Search for students from Hassan"))

    def test_quoted_comma_address_stays_one_update_value(self):
        query = (
            'Update Karthik S L address to '
            '"Samudravalli Village, Alur Taluk (T), Hassan District (D)"'
        )
        parsed = _parse_update_assignments(query)
        self.assertEqual(len(parsed["assignments"]), 1)
        self.assertEqual(
            parsed["assignments"][0]["value_text"],
            "Samudravalli Village, Alur Taluk (T), Hassan District (D)",
        )

    def test_multi_field_update_preserves_quoted_commas_and_values(self):
        query = (
            'Update Karthik S L father name to "Lokesh", mother name to "Radha", '
            'phone number to "9876543210", email to "karthik@example.com", and '
            'address to "Samudravalli Village, Alur Taluk (T), Hassan District (D)"'
        )
        parsed = _parse_update_assignments(query)
        self.assertEqual(len(parsed["assignments"]), 5)
        self.assertEqual(parsed["assignments"][-1]["value_text"], "Samudravalli Village, Alur Taluk (T), Hassan District (D)")

    def test_update_rejects_fields_missing_from_live_schema(self):
        student_columns = {"usn": "varchar(20)", "name": "varchar(150)"}
        marks_columns = {"usn": "varchar(20)", "semester": "int", "sgpa": "decimal(4,2)"}
        with patch("routes_query._load_table_columns", side_effect=[student_columns, marks_columns]):
            with self.assertRaises(Exception) as error:
                _resolve_assignment(
                    object(),
                    {"usn": "4HG23CS029", "current_sem": 1},
                    {"field_text": "age", "value_text": "21"},
                )
        self.assertIn("not available in the database", str(error.exception))

    def test_structured_update_cannot_create_columns(self):
        update = {
            "operation": "update",
            "affected_usns": ["4HG23CS029"],
            "column_creations": [{"table": "students", "column": "age", "data_type": "INT"}],
            "executions": [{
                "sql": "UPDATE students SET `father_name`=%s WHERE usn=%s",
                "params": ["Lokesh", "4HG23CS029"],
            }],
        }
        self.assertIsNotNone(_validate_structured_update(update))


if __name__ == "__main__":
    unittest.main()