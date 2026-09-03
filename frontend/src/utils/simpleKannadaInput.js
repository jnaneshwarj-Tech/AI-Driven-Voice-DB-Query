/**
 * Desh Kannada-style Kannada input
 * Tracks current word and shows live transliteration
 */

// Cache for API results
const cache = new Map();

/**
 * Get transliteration suggestions for current word
 */
export async function getTransliterationSuggestions(word) {
  if (!word || !word.trim()) return [];
  
  // Check cache
  if (cache.has(word)) {
    return cache.get(word);
  }
  
  try {
    const url = `https://inputtools.google.com/request?text=${encodeURIComponent(word)}&itc=kn-t-i0-und&num=5&cp=0&cs=1&ie=utf-8&oe=utf-8`;
    const response = await fetch(url);
    const data = await response.json();
    
    if (data && data[0] === 'SUCCESS' && data[1]?.[0]?.[1]) {
      const suggestions = data[1][0][1];
      cache.set(word, suggestions);
      return suggestions;
    }
    
    return [];
  } catch (error) {
    console.error('Transliteration error:', error);
    return [];
  }
}

/**
 * Desh Kannada-style input processor
 * Tracks current word and provides live suggestions
 */
export class DeshKannadaProcessor {
  constructor(textareaRef, onUpdate, onSuggestions) {
    this.textareaRef = textareaRef;
    this.onUpdate = onUpdate;
    this.onSuggestions = onSuggestions;
    this.timer = null;
    this.currentSuggestions = [];
    this.requestId = 0;
    this.pendingBoundary = null;
    this.onSuggestions([]);
  }
  
  /**
   * Get the current word being typed (from last space to cursor)
   */
  getCurrentWord(text, cursorPos) {
    const beforeCursor = text.substring(0, cursorPos);
    const lastSpaceIndex = beforeCursor.lastIndexOf(' ');
    const wordStart = lastSpaceIndex + 1;
    
    // Find end of current word (next space or end of text)
    const afterCursor = text.substring(cursorPos);
    const nextSpaceIndex = afterCursor.indexOf(' ');
    const wordEnd = nextSpaceIndex === -1 ? text.length : cursorPos + nextSpaceIndex;
    
    return {
      word: text.substring(wordStart, wordEnd),
      start: wordStart,
      end: wordEnd,
      cursorInWord: cursorPos >= wordStart && cursorPos <= wordEnd
    };
  }
  
  /**
   * Check if text contains Kannada script
   */
  hasKannada(text) {
    return /[\u0C80-\u0CFF]/.test(text);
  }
  
  /**
   * Handle input with Desh Kannada-style behavior
   */
  async handleInput(text, cursorPos) {
    // Clear existing timer
    if (this.timer) {
      clearTimeout(this.timer);
    }

    // Never let suggestions for the previous word appear for a new word.
    this.requestId += 1;
    this.currentSuggestions = [];
    this.onSuggestions([]);
    
    // Get current word info
    const wordInfo = this.getCurrentWord(text, cursorPos);

    this.pendingBoundary = null;
    
    // If not in a word or word is already Kannada, clear suggestions
    if (!wordInfo.cursorInWord || this.hasKannada(wordInfo.word)) {
      this.onSuggestions([]);
      return;
    }
    
    // If word is too short or technical, clear suggestions
    if (!wordInfo.word.length || /^[A-Z]+$/.test(wordInfo.word) || /^\d/.test(wordInfo.word)) {
      return;
    }
    
    // Get suggestions after short delay
    const requestId = ++this.requestId;
    this.timer = setTimeout(async () => {
      const suggestions = await getTransliterationSuggestions(wordInfo.word);
      if (requestId !== this.requestId) return;

      this.currentSuggestions = suggestions;
      this.onSuggestions(suggestions);
    }, 100); // Fast response like Desh Kannada
  }
  
  /**
   * Apply selected suggestion
   */
  applySuggestion(text, cursorPos, suggestion) {
    const wordInfo = this.getCurrentWord(text, cursorPos);
    
    // Replace current word with suggestion
    const before = text.substring(0, wordInfo.start);
    const after = text.substring(wordInfo.end);
    const newText = before + suggestion + after;
    const newCursorPos = wordInfo.start + suggestion.length;
    
    // Invalidate pending responses and clear suggestions after applying.
    this.requestId += 1;
    this.currentSuggestions = [];
    this.onSuggestions([]);
    
    return { text: newText, cursorPos: newCursorPos };
  }
  
  /**
   * Handle space key - auto-apply first suggestion
   */
  handleSpace(text, cursorPos) {
    const wordInfo = this.getCurrentWord(text, cursorPos);
    
    // If we have suggestions and cursor is in current word
    if (this.currentSuggestions.length > 0 && wordInfo.cursorInWord && !this.hasKannada(wordInfo.word)) {
      // Apply first suggestion
      const result = this.applySuggestion(text, cursorPos, this.currentSuggestions[0]);
      // Add space after
      return {
        text: result.text.substring(0, result.cursorPos) + ' ' + result.text.substring(result.cursorPos),
        cursorPos: result.cursorPos + 1
      };
    }

    // Keep the boundary immediately, then replace the word when the API result arrives.
    // This avoids losing transliteration when the user types faster than the network.
    if (wordInfo.cursorInWord && wordInfo.word.length >= 1 && !this.hasKannada(wordInfo.word) &&
        !/^[A-Z]+$/.test(wordInfo.word) && !/^\d/.test(wordInfo.word)) {
      const boundary = {
        word: wordInfo.word,
        start: wordInfo.start,
        end: wordInfo.end,
        requestId: ++this.requestId,
      };
      this.pendingBoundary = boundary;
      this.resolveBoundary(boundary);
    }
    
    // Otherwise just add space normally
    return {
      text: text.substring(0, cursorPos) + ' ' + text.substring(cursorPos),
      cursorPos: cursorPos + 1
    };
  }

  async resolveBoundary(boundary) {
    const suggestions = await getTransliterationSuggestions(boundary.word);
    if (this.pendingBoundary !== boundary || !suggestions[0]) return;

    const currentText = this.textareaRef.current?.value;
    if (!currentText || currentText.substring(boundary.start, boundary.end) !== boundary.word) return;

    const before = currentText.substring(0, boundary.start);
    const after = currentText.substring(boundary.end);
    const text = before + suggestions[0] + after;
    const cursorPos = boundary.start + suggestions[0].length + (after.startsWith(' ') ? 1 : 0);
    this.onUpdate(text);
    this.onSuggestions([]);
    this.pendingBoundary = null;
    setTimeout(() => {
      if (this.textareaRef.current) {
        this.textareaRef.current.selectionStart = cursorPos;
        this.textareaRef.current.selectionEnd = cursorPos;
      }
    }, 0);
  }
  
  cleanup() {
    if (this.timer) {
      clearTimeout(this.timer);
    }
    this.requestId += 1;
    this.pendingBoundary = null;
  }
}

