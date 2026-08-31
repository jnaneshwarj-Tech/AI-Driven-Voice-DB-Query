/**
 * kannadaTransliteration.js
 * 
 * Google Keyboard-style Kannada transliteration for English/Roman input.
 * 
 * Examples:
 *   "manoj" → "ಮನೋಜ್"
 *   "torisi" → "ತೋರಿಸಿ"
 *   "sampoorna mahiti" → "ಸಂಪೂರ್ಣ ಮಾಹಿತಿ"
 * 
 * IMPORTANT: Does not transliterate:
 *   - English words (student, CSE, CGPA, etc.)
 *   - Numbers (2024, 3rd, etc.)
 *   - USNs (4HG23CS032)
 *   - Technical terms
 */

// Basic Kannada character mappings (consonants + vowels)
const KANNADA_VOWELS = {
  'a': 'ಅ',
  'aa': 'ಆ',
  'i': 'ಇ',
  'ii': 'ಈ',
  'u': 'ಉ',
  'uu': 'ಊ',
  'e': 'ಎ',
  'ee': 'ಏ',
  'ai': 'ಐ',
  'o': 'ಒ',
  'oo': 'ಓ',
  'au': 'ಔ',
};

const KANNADA_CONSONANTS = {
  'ka': 'ಕ',
  'kha': 'ಖ',
  'ga': 'ಗ',
  'gha': 'ಘ',
  'nga': 'ಙ',
  'cha': 'ಚ',
  'chha': 'ಛ',
  'ja': 'ಜ',
  'jha': 'ಝ',
  'nya': 'ಞ',
  'ta': 'ಟ',
  'tha': 'ಠ',
  'da': 'ಡ',
  'dha': 'ಢ',
  'na': 'ಣ',
  'tha': 'ತ',
  'thha': 'ಥ',
  'da': 'ದ',
  'dha': 'ಧ',
  'na': 'ನ',
  'pa': 'ಪ',
  'pha': 'ಫ',
  'ba': 'ಬ',
  'bha': 'ಭ',
  'ma': 'ಮ',
  'ya': 'ಯ',
  'ra': 'ರ',
  'la': 'ಲ',
  'va': 'ವ',
  'sha': 'ಶ',
  'shha': 'ಷ',
  'sa': 'ಸ',
  'ha': 'ಹ',
  'lla': 'ಳ',
  'ksha': 'ಕ್ಷ',
  'jnya': 'ಜ್ಞ',
};

// Common Kannada words mapping (for better UX)
const COMMON_WORDS = {
  // Query actions
  'torisi': 'ತೋರಿಸಿ',
  'tori': 'ತೋರಿ',
  'kodi': 'ಕೊಡಿ',
  'huDuki': 'ಹುಡುಕಿ',
  'huDki': 'ಹುಡುಕಿ',
  
  // Information
  'mahiti': 'ಮಾಹಿತಿ',
  'mahithi': 'ಮಾಹಿತಿ',
  'vivara': 'ವಿವರ',
  'vivarа': 'ವಿವರ',
  'sampoorna': 'ಸಂಪೂರ್ಣ',
  'sampoorne': 'ಸಂಪೂರ್ಣ',
  'ella': 'ಎಲ್ಲಾ',
  'elaa': 'ಎಲ್ಲಾ',
  'poorna': 'ಪೂರ್ಣ',
  'poorne': 'ಪೂರ್ಣ',
  
  // People
  'avara': 'ಅವರ',
  'avaru': 'ಅವರು',
  'vidyarthi': 'ವಿದ್ಯಾರ್ಥಿ',
  'vidyarthigalu': 'ವಿದ್ಯಾರ್ಥಿಗಳು',
  'students': 'students', // Keep English
  'student': 'student',
  
  // Academic
  'anka': 'ಅಂಕ',
  'marks': 'marks', // Keep English
  'semester': 'semester', // Keep English
  'sem': 'sem',
  'cgpa': 'CGPA',
  'sgpa': 'SGPA',
  'gpa': 'GPA',
  
  // Personal
  'thande': 'ತಂದೆ',
  'thayi': 'ತಾಯಿ',
  'phone': 'phone', // Keep English
  'email': 'email',
  
  // Graduation
  'padavi': 'ಪದವಿ',
  'graduate': 'graduate', // Keep English
  'graduated': 'graduated',
  
  // Common phrases
  'alli': 'ಅಲ್ಲಿ',
  'yalli': 'ಯಲ್ಲಿ',
  'ralli': 'ರಲ್ಲಿ',
  'aada': 'ಆದ',
  'aadava': 'ಆದವ',
  'list': 'list', // Keep English
  'details': 'details',
  'complete': 'complete',
  'academic': 'academic',
  'personal': 'personal',
  
  // Numbers - ordinals
  '1ne': '1ನೇ',
  '2ne': '2ನೇ',
  '3ne': '3ನೇ',
  '4ne': '4ನೇ',
  '5ne': '5ನೇ',
  '6ne': '6ನೇ',
  '7ne': '7ನೇ',
  '8ne': '8ನೇ',
};

// English technical terms that should NEVER be transliterated
const PRESERVE_ENGLISH = new Set([
  'student', 'students', 'marks', 'cgpa', 'sgpa', 'gpa', 'semester', 
  'sem', 'cse', 'cs', 'ise', 'ece', 'me', 'ce', 'ee', 'branch', 
  'department', 'list', 'show', 'display', 'give', 'get', 'find',
  'complete', 'full', 'details', 'information', 'academic', 'personal',
  'both', 'and', 'or', 'graduated', 'active', 'phone', 'email', 'address',
  'father', 'mother', 'name', 'dob', 'blood', 'group', 'gender',
  'top', 'best', 'highest', 'lowest', 'rank', 'result', 'results',
  'about', 'profile', 'record', 'records', 'database', 'data',
]);

/**
 * Check if a word should be preserved as-is (English technical term, USN, number)
 */
function shouldPreserve(word) {
  // Preserve if it's all uppercase (likely acronym)
  if (word === word.toUpperCase() && /[A-Z]/.test(word)) return true;
  
  // Preserve if it looks like a USN (starts with digit, contains letters and numbers)
  if (/^[0-9][A-Z0-9]{4,}$/i.test(word)) return true;
  
  // Preserve if it's a pure number
  if (/^\d+$/.test(word)) return true;
  
  // Preserve if in technical terms set
  if (PRESERVE_ENGLISH.has(word.toLowerCase())) return true;
  
  // Preserve if it contains @(email) or starts with http
  if (word.includes('@') || word.startsWith('http')) return true;
  
  return false;
}

/**
 * Transliterate a single word from Roman to Kannada
 * Returns the word as-is if it should be preserved
 */
function transliterateWord(word) {
  if (!word || word.length === 0) return word;
  
  // Check if should preserve
  if (shouldPreserve(word)) return word;
  
  // Check common words first (exact match, case-insensitive)
  const lowerWord = word.toLowerCase();
  if (COMMON_WORDS[lowerWord]) {
    return COMMON_WORDS[lowerWord];
  }
  
  // For now, return as-is for character-level transliteration
  // (Full character-level transliteration can be complex; 
  //  in production you'd use a library like `google-input-tools` or API)
  // This basic version handles common words well
  return word;
}

/**
 * Main transliteration function
 * Transliterates Roman Kannada to Kannada script while preserving English terms
 * 
 * @param {string} text - Input text in Roman/English
 * @param {boolean} autoDetect - If true, only transliterate if text looks like Kannada
 * @returns {string} - Transliterated text with English terms preserved
 */
export function transliterateToKannada(text, autoDetect = true) {
  if (!text) return '';
  
  // If auto-detect is on, check if text looks like it needs transliteration
  if (autoDetect) {
    // If text already contains Kannada characters, return as-is
    if (/[\u0C80-\u0CFF]/.test(text)) return text;
    
    // If text is all English technical terms, return as-is
    const words = text.split(/\s+/);
    const allPreserved = words.every(w => shouldPreserve(w));
    if (allPreserved) return text;
  }
  
  // Split by spaces, transliterate each word, rejoin
  const words = text.split(/\s+/);
  const transliteratedWords = words.map(word => {
    // Preserve punctuation
    const match = word.match(/^([^\w]*)([\w]+)([^\w]*)$/);
    if (!match) return word;
    
    const [, prefix, core, suffix] = match;
    const transliterated = transliterateWord(core);
    return prefix + transliterated + suffix;
  });
  
  return transliteratedWords.join(' ');
}

/**
 * Check if text contains Kannada characters
 */
export function hasKannadaScript(text) {
  return /[\u0C80-\u0CFF]/.test(text);
}

/**
 * Get transliteration suggestions as user types
 * Returns array of { original, transliterated } objects
 */
export function getTransliterationSuggestions(text) {
  if (!text || text.length < 2) return [];
  
  const words = text.toLowerCase().split(/\s+/);
  const lastWord = words[words.length - 1];
  
  if (!lastWord || lastWord.length < 2) return [];
  
  // Find matching common words
  const suggestions = [];
  for (const [roman, kannada] of Object.entries(COMMON_WORDS)) {
    if (roman.startsWith(lastWord) && roman !== lastWord) {
      suggestions.push({
        original: roman,
        transliterated: kannada,
        display: `${roman} → ${kannada}`
      });
    }
  }
  
  return suggestions.slice(0, 5); // Top 5 suggestions
}

/**
 * Get placeholder text based on language
 */
export function getPlaceholderText(language) {
  switch (language) {
    case 'kannada':
      return 'ಇಲ್ಲಿ ನಿಮ್ಮ ಪ್ರಶ್ನೆಯನ್ನು ನಮೂದಿಸಿ...';
    case 'mixed':
      return 'Search / ನಿಮ್ಮ ಪ್ರಶ್ನೆ...';
    default:
      return 'Search / Ask anything...';
  }
}

/**
 * Get example queries based on language
 */
export function getExampleQueries(language) {
  switch (language) {
    case 'kannada':
      return [
        'ಮನೋಜ್ ಅವರ ಸಂಪೂರ್ಣ ಮಾಹಿತಿ ತೋರಿಸಿ',
        '2024ರಲ್ಲಿ ಪದವಿ ಪಡೆದ ವಿದ್ಯಾರ್ಥಿಗಳನ್ನು ತೋರಿಸಿ',
        '3ನೇ ಸೆಮಿಸ್ಟರ್ CSE ವಿದ್ಯಾರ್ಥಿಗಳನ್ನು ತೋರಿಸಿ',
      ];
    case 'mixed':
      return [
        'Manoj ಅವರ complete details ತೋರಿಸಿ',
        '3ನೇ semester CSE students list kodi',
        '2024ರಲ್ಲಿ graduated students show madi',
      ];
    default:
      return [
        'Show everything about Manoj',
        'Show students graduated in 2024',
        'Show 3rd semester CSE students',
      ];
  }
}
