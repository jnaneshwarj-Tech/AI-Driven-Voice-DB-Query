import unittest
from unittest.mock import patch

from query_security_validator import validate_sql_query
from rag_sql_generator import _rule_based_fallback_sql, generate_sql_query
from routes_query import _check_ambiguity, _parse_update_assignments, _resolve_assignment, _validate_structured_update


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
        admin_write = {"operation": "delete", "sql": "DELETE FROM students WHERE usn='A'"}
        outfile = {"operation": "select", "sql": "SELECT name FROM students INTO OUTFILE 'x'"}
        self.assertFalse(validate_sql_query(mismatch, "Staff")["is_valid"])
        self.assertFalse(validate_sql_query(admin_write, "Admin")["is_valid"])
        self.assertFalse(validate_sql_query(outfile, "Staff")["is_valid"])

    def test_allows_student_insert_and_exact_usn_delete(self):
        insert = {
            "operation": "insert",
            "sql": "INSERT INTO students (usn, name) VALUES ('A', 'Student, Example')",
        }
        delete = {"operation": "delete", "sql": "DELETE FROM students WHERE usn='A'"}
        self.assertTrue(validate_sql_query(insert, "Staff")["is_valid"])
        self.assertTrue(validate_sql_query(delete, "Staff")["is_valid"])

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
        self.assertEqual(rural_params[1], "%hassan%")
        self.assertIn("village", rural_params[0])

        urban_count = _rule_based_fallback_sql("How many urban students are there?")
        count_sql, count_params = urban_count
        self.assertIn("COUNT(*)", count_sql)
        self.assertIn("s.address", count_sql)
        self.assertIn("city", count_params[0])

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
        self.assertIn("father_name", sql)
        self.assertEqual(params, ["Karthik S L"])

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