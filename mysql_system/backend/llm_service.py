"""
llm_service.py — NVIDIA LLM API integration.
"""
import requests
from config import settings

class LLMService:
    def __init__(self):
        self.api_key = settings.NVIDIA_API_KEY
        self.url = "https://integrate.api.nvidia.com/v1/chat/completions"
        self.model = "meta/llama3-70b-instruct"

    def generate(self, prompt: str) -> str:
        if not self.api_key:
            return "ERROR: NVIDIA_API_KEY not set."
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 1024,
        }
        try:
            r = requests.post(self.url, headers=headers, json=payload, timeout=30)
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
            return self._clean(text)
        except Exception as e:
            return f"ERROR: {e}"

    def _clean(self, raw: str) -> str:
        for fence in ["```sql", "```python", "```"]:
            if fence in raw:
                parts = raw.split(fence)
                if len(parts) > 1:
                    return parts[1].split("```")[0].strip()
        return raw.strip()

llm_service = LLMService()
