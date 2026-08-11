import unittest
from unittest.mock import patch

import requests

from llm_service import LLMService


class LLMServiceFallbackTests(unittest.TestCase):
    def setUp(self):
        self.service = LLMService()
        self.service.api_key = "test-key"
        self.service.model = "gemini-2.0-flash"
        self.service.fallback_models = ["gemini-1.5-flash", "gemini-1.5-pro"]

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
        self.assertIn("gemini-2.0-flash", first_url)
        self.assertIn("gemini-1.5-flash", second_url)


if __name__ == "__main__":
    unittest.main()
