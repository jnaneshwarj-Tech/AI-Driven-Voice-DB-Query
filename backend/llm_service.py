"""
llm_service.py — LLM integration supporting both Gemini and NVIDIA NIM API.

Automatically detects API provider based on the key (`nvapi-` for NVIDIA).
Provides automatic fallback model selection.
"""
import re
import requests
from config import settings

GEMINI_MODEL_PRIORITY = [
    # Newest models (2026-era) — current working models
    "gemini-3.6-flash",              # Latest stable 3.6 series (fast)
    "gemini-3.5-flash",              # Latest stable 3.5 series
    "gemini-3.5-flash-lite",         # Lighter 3.5 variant
    # Rolling aliases (always up-to-date)
    "gemini-flash-latest",           # Rolling alias → current flash
    "gemini-flash-lite-latest",      # Rolling alias → current lite
    "gemini-pro-latest",             # Rolling alias → current pro
]

# Updated 2026-08 — removed EOL models (llama-3.1-70b, 8b, mixtral-8x22b all EOL'd 2026-08-26)
NVIDIA_MODEL_PRIORITY = [
    "meta/llama-3.3-70b-instruct",
    "meta/llama-3.2-3b-instruct",
    "nvidia/llama-3.3-nemotron-super-49b-v1",
    "mistralai/mistral-7b-instruct-v0.3",
    "mistralai/mistral-small-3.1-24b-instruct",
    "microsoft/phi-4-mini-instruct",
    "google/gemma-3-27b-it",
]

class LLMService:
    def __init__(self):
        self.api_key = getattr(settings, "GEMINI_API_KEY", "")
        self._config_model = getattr(settings, "GEMINI_MODEL", "")
        self._working_model: str | None = None

        self.is_nvidia = self.api_key.startswith("nvapi-")

        # Validate Gemini key format early
        if not self.is_nvidia and self.api_key and not self.api_key.startswith("AIza"):
            print(
                f"[LLM] WARNING: GEMINI_API_KEY does not look like a valid Gemini key "
                f"(expected prefix 'AIza', got '{self.api_key[:8]}...'). "
                "Get your key at: https://aistudio.google.com/apikey"
            )

    def _model_priority_list(self) -> list[str]:
        """Build deduped priority list for the active provider."""
        seen = set()
        result = []
        
        # If it's NVIDIA but the user configured a gemini model, ignore it
        config_model = self._config_model
        if self.is_nvidia and "gemini" in config_model.lower():
            config_model = None
            
        defaults = NVIDIA_MODEL_PRIORITY if self.is_nvidia else GEMINI_MODEL_PRIORITY
        
        for m in [config_model] + defaults:
            if m and m not in seen:
                seen.add(m)
                result.append(m)
        return result

    def _try_model(self, model: str, prompt: str):
        """
        Try a single model. Returns (text, None) on success, (None, error_str) on failure.
        """
        if self.is_nvidia:
            url = "https://integrate.api.nvidia.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 2048,
                "top_p": 1
            }
        else:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.1,
                    "maxOutputTokens": 2048,
                    "topP": 1,
                },
            }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            
            if self.is_nvidia:
                choices = data.get("choices", [])
                if choices and choices[0].get("message", {}).get("content"):
                    text = choices[0]["message"]["content"]
                    return self._clean_output(text), None
                return None, f"Empty choices from {model}"
            else:
                candidates = data.get("candidates", [])
                if candidates:
                    text = candidates[0]["content"]["parts"][0]["text"]
                    return self._clean_output(text), None
                return None, f"Empty candidates from {model}"

        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response is not None else "?"
            body = e.response.text if e.response is not None else ""
            return None, f"HTTP {code} on {model}: {body[:200]}"
        except requests.exceptions.RequestException as e:
            return None, f"Request error on {model}: {str(e)[:200]}"

    def generate_query(self, prompt: str) -> str:
        if not self.api_key:
            return "ERROR: API KEY is not set in .env"

        # If we already found a working model this session, try it first
        if self._working_model:
            text, err = self._try_model(self._working_model, prompt)
            if text is not None:
                return text
            print(f"[LLM] Cached model {self._working_model} failed: {err}. Re-scanning.")
            self._working_model = None

        # Full scan through priority list
        errors = []
        for model in self._model_priority_list():
            text, err = self._try_model(model, prompt)
            if text is not None:
                print(f"[LLM] Using model: {model}")
                self._working_model = model  # Cache for next call
                return text
            errors.append(err)
            print(f"[LLM] {err}")

        # All models failed
        provider = "NVIDIA" if self.is_nvidia else "Gemini"
        error_summary = " | ".join(errors[-3:])  # Show last 3 errors
        return f"ERROR: All {provider} models failed. Last errors: {error_summary}"

    def _clean_output(self, raw: str) -> str:
        """Strip markdown code fences if present."""
        raw = raw.strip()
        for fence in ["```sql", "```python", "```json", "```"]:
            lower = raw.lower()
            if fence in lower:
                idx = lower.find(fence)
                after = raw[idx + len(fence):]
                end = after.find("```")
                if end != -1:
                    return after[:end].strip()
                return after.strip()
        return raw


llm_service = LLMService()
