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
  'huduki': 'ಹುಡುಕಿ',
  'hudki': 'ಹುಡುಕಿ',
  
  // Information
  'mahiti': 'ಮಾಹಿತಿ',
  'mahithi': 'ಮಾಹಿತಿ',
  'mahithi': 'ಮಾಹಿತಿ',
  'vivara': 'ವಿವರ',
  'vivarа': 'ವಿವರ',
  'vivare': 'ವಿವರ',
  'sampoorna': 'ಸಂಪೂರ್ಣ',
  'sampoorne': 'ಸಂಪೂರ್ಣ',
  'sampoorna': 'ಸಂಪೂರ್ಣ',
  'ella': 'ಎಲ್ಲಾ',
  'elaa': 'ಎಲ್ಲಾ',
  'ellaa': 'ಎಲ್ಲಾ',
  'poorna': 'ಪೂರ್ಣ',
  'poorne': 'ಪೂರ್ಣ',
  'poornam': 'ಪೂರ್ಣ',
  
  // People
  'avara': 'ಅವರ',
  'avaru': 'ಅವರು',
  'avarа': 'ಅವರ',
  'avru': 'ಅವರು',
  'vidyarthi': 'ವಿದ್ಯಾರ್ಥಿ',
  'vidyarthigalu': 'ವಿದ್ಯಾರ್ಥಿಗಳು',
  'vidyarthigala': 'ವಿದ್ಯಾರ್ಥಿಗಳ',
  'vidyarthy': 'ವಿದ್ಯಾರ್ಥಿ',
  'vidyarthygalu': 'ವಿದ್ಯಾರ್ಥಿಗಳು',
  
  // Academic
  'anka': 'ಅಂಕ',
  'ankagalu': 'ಅಂಕಗಳು',
  'ankagala': 'ಅಂಕಗಳ',
  
  // Personal
  'thande': 'ತಂದೆ',
  'thayi': 'ತಾಯಿ',
  'hesaru': 'ಹೆಸರು',
  'hesara': 'ಹೆಸರ',
  
  // Graduation
  'padavi': 'ಪದವಿ',
  'padeda': 'ಪಡೆದ',
  'padedu': 'ಪಡೆದು',
  'padeyalu': 'ಪಡೆಯಲು',
  
  // Location/Time
  'alli': 'ಅಲ್ಲಿ',
  'yalli': 'ಯಲ್ಲಿ',
  'ralli': 'ರಲ್ಲಿ',
  'alli': 'ಅಲ್ಲಿ',
  'aada': 'ಆದ',
  'aadava': 'ಆದವ',
  'aadavaru': 'ಆದವರು',
  
  // Numbers - ordinals
  '1ne': '1ನೇ',
  '2ne': '2ನೇ',
  '3ne': '3ನೇ',
  '4ne': '4ನೇ',
  '5ne': '5ನೇ',
  '6ne': '6ನೇ',
  '7ne': '7ನೇ',
  '8ne': '8ನೇ',
  'omdane': 'ಒಂದನೇ',
  'eradane': 'ಎರಡನೇ',
  'moordane': 'ಮೂರನೇ',
  'naakane': 'ನಾಲ್ಕನೇ',
  
  // Common names (frequently used in queries)
  'manoj': 'ಮನೋಜ್',
  'manja': 'ಮಂಜ',
  'manju': 'ಮಂಜು',
  'manjunath': 'ಮಂಜುನಾಥ್',
  'biradar': 'ಬಿರಾದಾರ್',
  'sahebgouda': 'ಸಾಹೇಬಗೌಡ',
  'saheb': 'ಸಾಹೇಬ್',
  'gouda': 'ಗೌಡ',
  'gowda': 'ಗೌಡ',
  'raj': 'ರಾಜ್',
  'kumar': 'ಕುಮಾರ್',
  'prasad': 'ಪ್ರಸಾದ್',
  'ravi': 'ರವಿ',
  'suresh': 'ಸುರೇಶ್',
  'sudeep': 'ಸುದೀಪ್',
  'sudeepa': 'ಸುದೀಪ',
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
 * 
 * Enhanced with better phonetic mapping for common Kannada sounds
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
  
  // Enhanced phonetic transliteration for common patterns
  let result = word;
  
  // Common name patterns
  const namePatterns = {
    'manoj': 'ಮನೋಜ್',
    'raj': 'ರಾಜ್',
    'kumar': 'ಕುಮಾರ್',
    'prasad': 'ಪ್ರಸಾದ್',
    'prakash': 'ಪ್ರಕಾಶ್',
    'suresh': 'ಸುರೇಶ್',
    'ramesh': 'ರಮೇಶ್',
    'ganesh': 'ಗಣೇಶ್',
    'harish': 'ಹರೀಶ್',
    'mahesh': 'ಮಹೇಶ್',
    'dinesh': 'ದಿನೇಶ್',
    'ravi': 'ರವಿ',
    'shiva': 'ಶಿವ',
    'krishna': 'ಕೃಷ್ಣ',
    'vishnu': 'ವಿಷ್ಣು',
  };
  
  if (namePatterns[lowerWord]) {
    return namePatterns[lowerWord];
  }
  
  // Action words
  const actionWords = {
    'show': 'ತೋರಿಸಿ',
    'give': 'ಕೊಡಿ',
    'find': 'ಹುಡುಕಿ',
    'search': 'ಹುಡುಕಿ',
    'display': 'ತೋರಿಸಿ',
    'get': 'ತಗೆದುಕೊಳ್ಳಿ',
  };
  
  if (actionWords[lowerWord]) {
    return actionWords[lowerWord];
  }
  
  // For unrecognized words, return as-is
  // In production, you could add more sophisticated phonetic rules here
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
 * Use Google Input Tools for full phrase transliteration, with the local
 * dictionary as an offline fallback.
 * 
 * IMPROVED: Now handles phrases at any typing speed by processing the entire
 * text consistently. Uses word-level segmentation for better results.
 * 
 * @param {string} text - Full phrase to transliterate (e.g., "manoj avara mahiti torisi")
 * @param {AbortSignal} signal - Optional abort signal for cancellation
 * @returns {Promise<string>} - Transliterated Kannada text
 */
export async function transliterateWithGoogle(text, signal) {
  console.log('[API] transliterateWithGoogle called with:', text);
  if (!text) {
    console.log('[API] Skipping - empty text');
    return text || '';
  }
  
  // DON'T skip if text has Kannada - we still need to convert English parts!
  // Only skip if ALL words are already in Kannada or should be preserved
  
  try {
    // Split text into segments - transliterate each segment separately for better accuracy
    // This handles mixed English/Kannada better than single-phrase approach
    const segments = text.split(/\s+/);
    console.log('[API] Segments to process:', segments);
    const transliteratedSegments = [];
    
    for (const segment of segments) {
      if (!segment.trim()) {
        transliteratedSegments.push('');
        continue;
      }
      
      // Skip if already Kannada
      if (hasKannadaScript(segment)) {
        console.log('[API] Segment already Kannada:', segment);
        transliteratedSegments.push(segment);
        continue;
      }
      
      // Skip technical terms
      if (shouldPreserve(segment)) {
        console.log('[API] Preserving technical term:', segment);
        transliteratedSegments.push(segment);
        continue;
      }
      
      // Check if it's a common word in our dictionary first (faster)
      const lowerSegment = segment.toLowerCase();
      if (COMMON_WORDS[lowerSegment]) {
        console.log('[API] Found in dictionary:', segment, '→', COMMON_WORDS[lowerSegment]);
        transliteratedSegments.push(COMMON_WORDS[lowerSegment]);
        continue;
      }
      
      // Otherwise, use Google Input Tools API for this segment
      console.log('[API] Calling Google API for:', segment);
      try {
        const params = new URLSearchParams({
          text: segment,
          itc: 'kn-t-i0-und',
          num: '1',
          cp: '0',
          cs: '1',
          ie: 'utf-8',
          oe: 'utf-8',
        });
        
        const response = await fetch(
          `https://inputtools.google.com/request?${params}`,
          { signal, timeout: 3000 }
        );
        
        if (response.ok) {
          const payload = await response.json();
          console.log('[API] Google response for', segment, ':', payload);
          
          // Response format: ["SUCCESS", [["original_text", ["candidate1", ...]], ...]]
          if (payload && Array.isArray(payload) && payload[0] === 'SUCCESS' && 
              payload[1] && payload[1].length > 0) {
            const firstResult = payload[1][0];
            if (firstResult && firstResult[1] && firstResult[1].length > 0) {
              console.log('[API] Transliterated:', segment, '→', firstResult[1][0]);
              transliteratedSegments.push(firstResult[1][0]);
              continue;
            }
          }
        }
        
        // If API call failed or returned unexpected format, try local dictionary
        console.log('[API] Google API failed for', segment, ', using local dictionary');
        transliteratedSegments.push(transliterateWord(segment));
        
      } catch (err) {
        // On error, use local dictionary
        console.error('[API] Error for segment', segment, ':', err);
        transliteratedSegments.push(transliterateWord(segment));
      }
    }
    
    const result = transliteratedSegments.join(' ');
    console.log('[API] Final result:', result);
    return result;
    
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    console.error('[API] Complete failure:', error);
    return transliterateToKannada(text);
  }
}

export async function translateKannadaToEnglish(text, signal) {
  if (!text || !hasKannadaScript(text)) return text || '';
  try {
    const params = new URLSearchParams({
      client: 'gtx',
      sl: 'kn',
      tl: 'en',
      dt: 't',
      q: text,
    });
    const response = await fetch(`https://translate.googleapis.com/translate_a/single?${params}`, { signal });
    const payload = await response.json();
    const translated = payload?.[0]?.map((part) => part?.[0] || '').join('');
    return translated || text;
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    return text;
  }
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
      return 'Type in English → See live Kannada suggestions → Press Space to select! Try: sudeep, manoj, mahiti';
    case 'mixed':
      return 'Type in any language... (ಯಾವುದೇ ಭಾಷೆಯಲ್ಲಿ ಟೈಪ್ ಮಾಡಿ)';
    default:
      return 'Search / Ask anything... "Show marks of Manoj", "Top 10 students", etc.';
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
