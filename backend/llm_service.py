"""
llm_service.py — Gemini LLM integration with auto-fallback model selection.

Tries models in order of preference. If a model returns 404 or is restricted,
automatically moves to the next one. Uses the newest available models first.
"""
import re
import requests
from config import settings


# Ordered list of models to try — newest/best first, stable aliases last
# The -latest aliases are managed by Google and always point to the current stable version.
# Specific versioned models are listed as additional fallbacks.
GEMINI_MODEL_PRIORITY = [
    # Stable aliases (always up-to-date)
    "gemini-2.0-flash",          # Fast, capable, widely available
    "gemini-2.0-flash-lite",     # Lighter/faster variant
    "gemini-flash-latest",       # Rolling alias → current flash
    "gemini-flash-lite-latest",  # Rolling alias → current lite
    "gemini-pro-latest",         # Rolling alias → current pro
    # Pinned versions as last resort
    "gemini-2.0-flash-001",
    "gemini-2.0-flash-lite-001",
]


class LLMService:
    def __init__(self):
        self.api_key = getattr(settings, "GEMINI_API_KEY", "")
        # User-configured primary model (from .env), will be tried first
        self._config_model = getattr(settings, "GEMINI_MODEL", "gemini-2.0-flash")
        # Runtime-cached working model — once found, reuse it to avoid repeated probing
        self._working_model: str | None = None

    def _build_url(self, model: str) -> str:
        return (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={self.api_key}"
        )

    def _model_priority_list(self) -> list[str]:
        """Build deduped priority list: configured model first, then defaults."""
        seen = set()
        result = []
        for m in [self._config_model] + GEMINI_MODEL_PRIORITY:
            if m and m not in seen:
                seen.add(m)
                result.append(m)
        return result

    def _try_model(self, model: str, payload: dict, headers: dict):
        """
        Try a single model. Returns (text, None) on success, (None, error_str) on failure.
        """
        url = self._build_url(model)
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                text = candidates[0]["content"]["parts"][0]["text"]
                return self._clean_output(text), None
            return None, f"Empty candidates from {model}"
        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response is not None else "?"
            body = e.response.text if e.response is not None else ""
            # 404 = model not found/restricted, 429 = quota exceeded — both are skippable
            return None, f"HTTP {code} on {model}: {body[:200]}"
        except requests.exceptions.RequestException as e:
            return None, f"Request error on {model}: {str(e)[:200]}"

    def generate_query(self, prompt: str) -> str:
        if not self.api_key:
            return "ERROR: GEMINI_API_KEY is not set in .env"

        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 2048,
                "topP": 1,
            },
        }

        # If we already found a working model this session, try it first
        if self._working_model:
            text, err = self._try_model(self._working_model, payload, headers)
            if text is not None:
                return text
            # Cached model failed (e.g. quota) — reset and do full scan
            print(f"[LLM] Cached model {self._working_model} failed: {err}. Re-scanning.")
            self._working_model = None

        # Full scan through priority list
        errors = []
        for model in self._model_priority_list():
            text, err = self._try_model(model, payload, headers)
            if text is not None:
                print(f"[LLM] Using model: {model}")
                self._working_model = model  # Cache for next call
                return text
            errors.append(err)
            print(f"[LLM] {err}")

        # All models failed
        error_summary = " | ".join(errors[-3:])  # Show last 3 errors
        return f"ERROR: All Gemini models failed. Last errors: {error_summary}"

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
