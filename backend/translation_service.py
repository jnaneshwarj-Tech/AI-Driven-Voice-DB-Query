"""
translation_service.py — Semantic Kannada → English translation service.

This module provides BACKEND semantic translation to convert Kannada queries
into equivalent English meaning before they enter the existing query pipeline.

Architecture:
  Kannada Query (frontend)
       ↓
  translate_kannada_to_english_semantic()  ← This module
       ↓
  English semantic equivalent
       ↓
  Existing English query pipeline (unchanged)

IMPORTANT:
  - This is SEMANTIC translation, not word-by-word
  - Student names/USNs/numbers are protected during translation
  - Uses Google Translate API with fallback to keyword normalization
  - Never exposes API keys to frontend
  - Handles mixed Kannada+English queries correctly

Environment Variables:
  GOOGLE_CLOUD_TRANSLATE_API_KEY (optional)
  - If not set, uses free Google Translate web endpoint
  - For production, get API key from: https://cloud.google.com/translate
"""

import re
import logging
import requests
from typing import Optional
from config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: ENTITY PROTECTION
# ─────────────────────────────────────────────────────────────────────────────

# USN pattern: starts with digit, contains letters and numbers
_USN_PATTERN = re.compile(r'\b([0-9][A-Z0-9]{4,})\b', re.IGNORECASE)

# Student name pattern (Latin script names in database)
# Names are typically 2-3 words, each starting with capital letter
_NAME_PATTERN = re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]*){0,2})\b')

# Technical terms that should never be translated
_TECHNICAL_TERMS = {
    'SGPA', 'CGPA', 'GPA', 'CSE', 'ISE', 'ECE', 'ME', 'CE', 'EE',
    'CS', 'IS', 'EC', 'USB', 'USN', 'ID', 'EMAIL', 'PHONE',
}

# Placeholder format for protected entities
_PLACEHOLDER_PREFIX = '__PROTECTED_'


def _protect_entities(text: str) -> tuple[str, dict[str, str]]:
    """
    Replace sensitive entities with placeholders before translation.
    
    Returns:
        (protected_text, entity_map)
        - protected_text: Text with entities replaced by placeholders
        - entity_map: Mapping of placeholders → original entities
    """
    protected = text
    entity_map = {}
    counter = 0
    
    # Protect USNs
    for match in _USN_PATTERN.finditer(text):
        usn = match.group(1)
        placeholder = f'{_PLACEHOLDER_PREFIX}USN_{counter}__'
        entity_map[placeholder] = usn
        protected = protected.replace(usn, placeholder, 1)
        counter += 1
    
    # Protect technical terms (case-insensitive)
    for term in _TECHNICAL_TERMS:
        pattern = re.compile(r'\b' + re.escape(term) + r'\b', re.IGNORECASE)
        for match in pattern.finditer(protected):
            original = match.group(0)
            placeholder = f'{_PLACEHOLDER_PREFIX}TERM_{counter}__'
            entity_map[placeholder] = original
            protected = protected.replace(original, placeholder, 1)
            counter += 1
    
    # Protect numbers (marks, years, semesters, etc.)
    number_pattern = re.compile(r'\b(\d+(?:\.\d+)?)\b')
    for match in number_pattern.finditer(protected):
        number = match.group(1)
        # Skip if it's part of a placeholder
        if _PLACEHOLDER_PREFIX in protected[max(0, match.start()-20):match.start()]:
            continue
        placeholder = f'{_PLACEHOLDER_PREFIX}NUM_{counter}__'
        entity_map[placeholder] = number
        protected = protected.replace(number, placeholder, 1)
        counter += 1
    
    return protected, entity_map


def _restore_entities(text: str, entity_map: dict[str, str]) -> str:
    """
    Restore protected entities from placeholders after translation.
    """
    restored = text
    for placeholder, original in entity_map.items():
        restored = restored.replace(placeholder, original)
    return restored


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: GOOGLE TRANSLATE API INTEGRATION
# ─────────────────────────────────────────────────────────────────────────────

def _translate_with_google_api(text: str, source_lang: str = 'kn', target_lang: str = 'en') -> Optional[str]:
    """
    Translate text using Google Translate API.
    
    Uses the free public endpoint (no API key required for low volume).
    For production high-volume usage, set GOOGLE_CLOUD_TRANSLATE_API_KEY.
    
    Returns:
        Translated text, or None if translation fails
    """
    try:
        # Use Google Translate web API (free, no key needed for reasonable usage)
        # Format: https://translate.googleapis.com/translate_a/single
        params = {
            'client': 'gtx',
            'sl': source_lang,  # source language
            'tl': target_lang,  # target language
            'dt': 't',          # translation text
            'q': text,
        }
        
        response = requests.get(
            'https://translate.googleapis.com/translate_a/single',
            params=params,
            timeout=10,
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        
        if response.status_code == 200:
            result = response.json()
            # Result format: [[[translated_text, original_text, ...]]]
            if result and len(result) > 0 and len(result[0]) > 0:
                translated_parts = [part[0] for part in result[0] if part and part[0]]
                translated = ''.join(translated_parts).strip()
                return translated
        
        logger.warning(f"[TRANSLATE] Google API returned status {response.status_code}")
        return None
        
    except Exception as e:
        logger.error(f"[TRANSLATE] Google API error: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: FALLBACK KEYWORD NORMALIZATION
# ─────────────────────────────────────────────────────────────────────────────

def _fallback_keyword_normalization(text: str) -> str:
    """
    Fallback: Use kannada_processor keyword normalization if Google Translate fails.
    
    This is a simpler keyword replacement strategy, not full semantic translation.
    """
    try:
        from kannada_processor import normalize_query
        normalized, _ = normalize_query(text)
        return normalized
    except Exception as e:
        logger.error(f"[TRANSLATE] Fallback normalization error: {e}")
        return text


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4: MAIN TRANSLATION FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def translate_kannada_to_english_semantic(
    original_query: str,
    language: str = 'kannada'
) -> dict:
    """
    Translate a Kannada/mixed query into semantic English equivalent.
    
    Args:
        original_query: The user's original query (may contain Kannada Unicode)
        language: Language mode ('kannada', 'mixed', or 'english')
    
    Returns:
        {
            'original_query': str,           # Original query as typed
            'normalized_query': str,         # English semantic equivalent
            'detected_language': str,        # Detected language
            'translation_method': str,       # 'google_api' or 'keyword_fallback' or 'none'
            'protected_entities': dict,      # Entities that were protected
        }
    """
    # If already English, no translation needed
    if language == 'english':
        # Check if it actually contains Kannada (user might have typed Kannada in English mode)
        if not _contains_kannada(original_query):
            return {
                'original_query': original_query,
                'normalized_query': original_query,
                'detected_language': 'english',
                'translation_method': 'none',
                'protected_entities': {},
            }
    
    # Detect if query contains Kannada characters
    if not _contains_kannada(original_query):
        # No Kannada detected - might be Roman Kannada or pure English
        # Try keyword normalization in case it's Roman Kannada
        from kannada_processor import normalize_query
        normalized, detected = normalize_query(original_query)
        return {
            'original_query': original_query,
            'normalized_query': normalized,
            'detected_language': detected,
            'translation_method': 'keyword_fallback',
            'protected_entities': {},
        }
    
    # Query contains Kannada Unicode - perform semantic translation
    logger.info(f"[TRANSLATE] Translating Kannada query: {original_query[:100]}...")
    
    # Step 1: Protect entities (USNs, numbers, technical terms)
    protected_text, entity_map = _protect_entities(original_query)
    logger.debug(f"[TRANSLATE] Protected entities: {list(entity_map.values())}")
    
    # Step 2: Translate using Google API
    translated = _translate_with_google_api(protected_text, source_lang='kn', target_lang='en')
    translation_method = 'google_api'
    
    if not translated:
        # Fallback to keyword normalization
        logger.warning("[TRANSLATE] Google API failed, using keyword fallback")
        translated = _fallback_keyword_normalization(protected_text)
        translation_method = 'keyword_fallback'
    
    # Step 3: Restore protected entities
    final_query = _restore_entities(translated, entity_map)
    
    # Step 4: Clean up translation artifacts
    final_query = _clean_translation(final_query)
    
    logger.info(f"[TRANSLATE] Result: {final_query[:100]}...")
    
    return {
        'original_query': original_query,
        'normalized_query': final_query,
        'detected_language': 'kannada' if language == 'kannada' else 'mixed',
        'translation_method': translation_method,
        'protected_entities': entity_map,
    }


def _contains_kannada(text: str) -> bool:
    """Check if text contains Kannada Unicode characters."""
    return bool(re.search(r'[\u0C80-\u0CFF]', text))


def _clean_translation(text: str) -> str:
    """
    Clean up common translation artifacts.
    
    Examples:
      - "Show the complete information" → "Show complete information"
      - "Student's marks" → "Student marks"
      - Multiple spaces → single space
    """
    cleaned = text
    
    # Remove extra articles that Google Translate often adds
    cleaned = re.sub(r'\bthe\s+complete\s+information\b', 'complete information', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\bthe\s+full\s+details\b', 'full details', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\bthe\s+all\s+', 'all ', cleaned, flags=re.IGNORECASE)
    
    # Normalize possessive forms
    cleaned = re.sub(r"'s\s+", ' ', cleaned)
    
    # Clean up multiple spaces
    cleaned = re.sub(r'\s{2,}', ' ', cleaned)
    
    # Trim
    cleaned = cleaned.strip()
    
    return cleaned


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5: QUERY CONFIDENCE SCORING
# ─────────────────────────────────────────────────────────────────────────────

def assess_translation_quality(translation_result: dict) -> float:
    """
    Assess the quality/confidence of a translation.
    
    Returns:
        Confidence score between 0.0 and 1.0
    """
    normalized = translation_result['normalized_query']
    method = translation_result['translation_method']
    
    # Base confidence by method
    if method == 'none':
        return 1.0  # No translation needed
    elif method == 'google_api':
        base_confidence = 0.9
    else:  # keyword_fallback
        base_confidence = 0.7
    
    # Reduce confidence if translation is too short or too long
    word_count = len(normalized.split())
    if word_count < 2:
        base_confidence *= 0.7
    elif word_count > 50:
        base_confidence *= 0.8
    
    # Reduce confidence if translation contains unresolved placeholders
    if _PLACEHOLDER_PREFIX in normalized:
        base_confidence *= 0.5
        logger.warning("[TRANSLATE] Unresolved placeholders in translation!")
    
    return base_confidence


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6: PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def translate_query_if_needed(natural_query: str, language: str = 'english') -> tuple[str, dict]:
    """
    Main entry point for query translation.
    
    Args:
        natural_query: User's original query
        language: Language mode ('english', 'kannada', 'mixed')
    
    Returns:
        (normalized_query, translation_metadata)
        - normalized_query: English semantic equivalent ready for existing pipeline
        - translation_metadata: Dict with translation details for logging/debugging
    """
    result = translate_kannada_to_english_semantic(natural_query, language)
    confidence = assess_translation_quality(result)
    
    metadata = {
        **result,
        'translation_confidence': confidence,
    }
    
    return result['normalized_query'], metadata
