import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

import requests

from canonical_fields import map_column
from llm_service import LLMService


class LLMServiceFallbackTests(unittest.TestCase):
    def setUp(self):
        self.service = LLMService()
        self.service.api_key = "test-key"
        self.service._config_model = "gemini-3.6-flash"
        self.service.fallback_models = ["gemini-3.5-flash", "gemini-3.5-flash-lite"]

    @patch("llm_service.requests.post")
    def test_retries_with_fallback_model_on_service_unavailable(self, mock_post):
        first_response = unittest.mock.Mock()
        first_response.status_code = 503
        first_response.raise_for_status.side_effect = requests.exceptions.HTTPError("503 Service Unavailable")
        first_response.text = '{"error": {"message": "service unavailable"}}'

        second_response = unittest.mock.Mock()
        second_response.status_code = 200
        second_response.raise_for_status.return_value = None
        second_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "SELECT 1"}]}}]
        }

        mock_post.side_effect = [first_response, second_response]

        result = self.service.generate_query("show students")

        self.assertEqual(result, "SELECT 1")
        self.assertEqual(mock_post.call_count, 2)
        first_url = mock_post.call_args_list[0].args[0]
        second_url = mock_post.call_args_list[1].args[0]
        self.assertIn("gemini-3.6-flash", first_url)
        self.assertIn("gemini-3.5-flash", second_url)

    def test_maps_address_personal_fields(self):
        self.assertEqual(map_column("address")[0], "address")
        self.assertEqual(map_column("student_address")[0], "address")
        self.assertEqual(map_column("residential_address")[0], "address")

    @patch("llm_service.requests.post", side_effect=requests.exceptions.Timeout("private request URL"))
    def test_timeout_error_does_not_expose_request_details(self, _mock_post):
        self.service._model_priority_list = lambda: ["gemini-test"]
        output = StringIO()
        with redirect_stdout(output):
            result = self.service.generate_query("show students")
        self.assertIn("Timeout on gemini-test", result)
        self.assertNotIn("private request URL", result)
        self.assertNotIn("private request URL", output.getvalue())


if __name__ == "__main__":
    unittest.main()
