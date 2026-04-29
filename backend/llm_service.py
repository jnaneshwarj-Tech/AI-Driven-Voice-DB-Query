import requests
import json
from config import settings

class LLMService:
    def __init__(self):
        self.api_key = settings.NVIDIA_API_KEY
        self.url = "https://integrate.api.nvidia.com/v1/chat/completions"
        self.model = "meta/llama-3.3-70b-instruct"

    def generate_query(self, prompt: str) -> str:
        if not self.api_key:
            return "ERROR: NVIDIA_API_KEY is not set."

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 1024,
            "top_p": 1
        }

        try:
            response = requests.post(self.url, headers=headers, json=payload)
            response.raise_for_status()
            generated_text = response.json()["choices"][0]["message"]["content"]
            return self._clean_output(generated_text)
        except requests.exceptions.RequestException as e:
            return f"ERROR: Failed to reach LLM API: {e}"

    def _clean_output(self, raw: str) -> str:
        """Strip markdown code fences if present."""
        for fence in ["```python", "```json", "```"]:
            if fence in raw:
                parts = raw.split(fence)
                if len(parts) > 1:
                    return parts[1].split("```")[0].strip()
        return raw.strip()

llm_service = LLMService()
