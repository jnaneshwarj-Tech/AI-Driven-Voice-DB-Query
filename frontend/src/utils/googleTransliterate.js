/**
 * Google Transliterate Integration
 * 
 * Uses Google's official Input Tools API for reliable Kannada transliteration.
 */

/**
 * Transliterate text using Google's Input Tools API
 * 
 * @param {string} text - English text to convert to Kannada
 * @param {string} language - Target language code (default: 'kn' for Kannada)
 * @returns {Promise<string>} - Transliterated Kannada text
 */
export async function googleTransliterate(text, language = 'kn') {
  if (!text || !text.trim()) {
    return text;
  }

  try {
    console.log('[GoogleTransliterate] Calling API for:', text);
    
    // Use GET request with query parameters (more reliable)
    const params = new URLSearchParams({
      text: text,
      itc: `${language}-t-i0-und`,
      num: '5',
      cp: '0',
      cs: '1',
      ie: 'utf-8',
      oe: 'utf-8',
    });

    const response = await fetch(`https://inputtools.google.com/request?${params}`, {
      method: 'GET',
    });

    if (!response.ok) {
      console.error('[GoogleTransliterate] API returned', response.status);
      return text;
    }

    const data = await response.json();
    console.log('[GoogleTransliterate] API response:', data);
    
    // Response format: ["SUCCESS", [["original", ["suggestion1", "suggestion2", ...]]]]
    if (data && Array.isArray(data) && data[0] === 'SUCCESS' && data[1] && data[1].length > 0) {
      const result = data[1][0];
      if (result && result[1] && result[1].length > 0) {
        const transliterated = result[1][0];
        console.log('[GoogleTransliterate] Converted:', text, '→', transliterated);
        return transliterated;
      }
    }

    console.log('[GoogleTransliterate] No suggestions, returning original');
    return text;

  } catch (error) {
    console.error('[GoogleTransliterate] Error:', error);
    return text;
  }
}

/**
 * Transliterate multiple segments (space-separated words)
 * Calls Google API for each word individually for better accuracy
 * 
 * @param {string} text - Full text with multiple words
 * @param {string} language - Target language code
 * @returns {Promise<string>} - Transliterated text
 */
export async function googleTransliterateSegmented(text, language = 'kn') {
  console.log('[GoogleTransliterate] Segmented called with:', text);
  
  if (!text || !text.trim()) {
    return text;
  }

  // Split into words
  const words = text.split(/\s+/);
  console.log('[GoogleTransliterate] Processing words:', words);
  const transliteratedWords = [];

  for (const word of words) {
    if (!word.trim()) {
      transliteratedWords.push('');
      continue;
    }

    // Skip if already contains Kannada characters
    if (hasKannadaScript(word)) {
      console.log('[GoogleTransliterate] Already Kannada:', word);
      transliteratedWords.push(word);
      continue;
    }

    // Skip technical terms (CSE, CGPA, etc.)
    if (shouldPreserveTechnical(word)) {
      console.log('[GoogleTransliterate] Preserving technical term:', word);
      transliteratedWords.push(word);
      continue;
    }

    // Transliterate this word
    try {
      const transliterated = await googleTransliterate(word, language);
      transliteratedWords.push(transliterated);
    } catch (error) {
      // On error, keep original word
      console.error('[GoogleTransliterate] Error for word', word, ':', error);
      transliteratedWords.push(word);
    }
  }

  const result = transliteratedWords.join(' ');
  console.log('[GoogleTransliterate] Final result:', result);
  return result;
}

/**
 * Check if text contains Kannada script
 */
function hasKannadaScript(text) {
  return /[\u0C80-\u0CFF]/.test(text);
}

/**
 * Check if word should be preserved as-is (technical terms)
 */
function shouldPreserveTechnical(word) {
  const technicalTerms = new Set([
    'CSE', 'ISE', 'ECE', 'ME', 'CE', 'EE', 'CGPA', 'SGPA', 'GPA',
    'semester', 'sem', 'student', 'students', 'marks', 'list',
    'email', 'phone', 'USN', 'ID', 'CS', 'IS', 'EC',
  ]);

  // Preserve if uppercase (likely acronym)
  if (word === word.toUpperCase() && word.length <= 4) {
    return true;
  }

  // Preserve if in technical terms set (case-insensitive)
  if (technicalTerms.has(word.toUpperCase())) {
    return true;
  }

  // Preserve if looks like USN (starts with digit)
  if (/^[0-9]/.test(word) && /[A-Z0-9]{4,}/i.test(word)) {
    return true;
  }

  return false;
}

/**
 * Batch transliterate - sends entire phrase to Google API at once
 * This is faster than word-by-word but may be less accurate
 * 
 * @param {string} text - Full text to transliterate
 * @param {string} language - Target language code
 * @returns {Promise<string>} - Transliterated text
 */
export async function googleTransliterateBatch(text, language = 'kn') {
  if (!text || !text.trim()) {
    return text;
  }

  // If text already has Kannada, do word-by-word processing
  if (hasKannadaScript(text)) {
    return googleTransliterateSegmented(text, language);
  }

  // Otherwise, send entire phrase at once
  return googleTransliterate(text, language);
}

export default {
  googleTransliterate,
  googleTransliterateSegmented,
  googleTransliterateBatch,
};
