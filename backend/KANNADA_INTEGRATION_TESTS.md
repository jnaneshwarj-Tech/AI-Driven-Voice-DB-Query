# Kannada Integration Testing Guide

## ✅ Testing Checklist

### Test 1: English (Regression - Must Still Work)
**Query**: `Show complete information about Manoj`  
**Expected**: Correct Manoj profile with all details  
**Translation**: None (direct English)  
**Success Criteria**: Same results as before integration

### Test 2: Pure Kannada Unicode
**Query**: `ಮನೋಜ್ ಅವರ ಸಂಪೂರ್ಣ ಮಾಹಿತಿ ತೋರಿಸಿ`  
**Expected**: Same Manoj profile as Test 1  
**Translation**: Backend translates to "Show complete information about Manoj"  
**Success Criteria**: Identical results to English query

### Test 3: Roman Kannada
**Query**: `manoj avara sampoorna mahiti torisi`  
**Expected**: Same Manoj profile  
**Translation**: Keyword normalization converts to English  
**Success Criteria**: Same student found

### Test 4: Mixed Kannada + English
**Query**: `Manoj ಅವರ complete information ತೋರಿಸಿ`  
**Expected**: Same Manoj profile  
**Translation**: Mixed translation preserves English technical terms  
**Success Criteria**: English terms preserved, Kannada translated

### Test 5: Kannada Academic Query
**Query**: `ಮೂರನೇ ಸೆಮಿಸ್ಟರ್‌ನ ಟಾಪ್ 10 ವಿದ್ಯಾರ್ಥಿಗಳನ್ನು ತೋರಿಸಿ`  
**Expected**: Top 10 students from 3rd semester  
**Translation**: "Show top 10 students of third semester"  
**Success Criteria**: Correct semester filter, correct count

### Test 6: Kannada with SGPA Filter
**Query**: `ಮೂರನೇ ಸೆಮಿಸ್ಟರ್‌ನಲ್ಲಿ 8 ಕ್ಕಿಂತ ಹೆಚ್ಚು SGPA ಪಡೆದ ವಿದ್ಯಾರ್ಥಿಗಳನ್ನು ತೋರಿಸಿ`  
**Expected**: Students with SGPA > 8 in semester 3  
**Translation**: "Show students who scored more than 8 SGPA in third semester"  
**Success Criteria**: Correct filtering, number "8" preserved

### Test 7: Kannada Fuzzy Search
**Query**: `ಸುದೀಪ್ ಬಿರಾದಾರ್`  
**Expected**: Fuzzy suggestions for "Sudeep Biradar"  
**Translation**: Name transliterated or passed through  
**Success Criteria**: Correct student found via fuzzy matching

### Test 8: Kannada Voice Input
**Action**: Speak Kannada query using microphone  
**Expected**: Kannada Unicode appears in textbox  
**Translation**: Backend processes after submit  
**Success Criteria**: Voice → Kannada text → correct results

### Test 9: Typing Performance (CRITICAL)
**Action**: Type long Kannada sentence continuously  
**Test**: `ಮನೋಜ್ ಅವರ ಸಂಪೂರ್ಣ ವೈಯಕ್ತಿಕ ಮತ್ತು ಶೈಕ್ಷಣಿಕ ಮಾಹಿತಿ ತೋರಿಸಿ`  
**Expected**:  
  - ✅ No character loss  
  - ✅ No delayed spaces  
  - ✅ No cursor jumping  
  - ✅ No textbox reset  
  - ✅ No API call per character  
  - ✅ Continuous smooth typing  
**Success Criteria**: Google-like typing experience

### Test 10: Entity Protection
**Query**: `4HG23CS032 USN ಗಾಗಿ ಮಾಹಿತಿ ತೋರಿಸಿ`  
**Expected**: USN "4HG23CS032" is NOT translated or corrupted  
**Translation**: "Show information for USN 4HG23CS032"  
**Success Criteria**: USN remains unchanged

### Test 11: Number Protection
**Query**: `8.5 CGPA ಗಿಂತ ಹೆಚ್ಚಿನ ವಿದ್ಯಾರ್ಥಿಗಳನ್ನು ತೋರಿಸಿ`  
**Expected**: Number "8.5" preserved  
**Translation**: "Show students with more than 8.5 CGPA"  
**Success Criteria**: Number not corrupted

### Test 12: Branch Code Protection
**Query**: `CSE ಶಾಖೆಯ ವಿದ್ಯಾರ್ಥಿಗಳನ್ನು ತೋರಿಸಿ`  
**Expected**: "CSE" remains as-is  
**Translation**: "Show students from CSE branch"  
**Success Criteria**: Technical term preserved

### Test 13: Response Language - Kannada Mode
**Action**: Select Kannada language mode  
**Query**: Any valid query  
**Expected**: Field labels in Kannada (ವಿದ್ಯಾರ್ಥಿ ಸಂಖ್ಯೆ, ಹೆಸರು, etc.)  
**Success Criteria**: UI labels in Kannada, data values unchanged

### Test 14: Response Language - Mixed Mode
**Action**: Select Mixed language mode  
**Query**: Any valid query  
**Expected**: Bilingual display  
**Success Criteria**: Natural mixed language response

### Test 15: Complete Profile Intent (Kannada)
**Query**: `ಮನೋಜ್ ಅವರ ಸಂಪೂರ್ಣ ಪ್ರೊಫೈಲ್ ತೋರಿಸಿ`  
**Expected**: Both personal and academic information  
**Intent**: complete_profile  
**Success Criteria**: Personal + Academic sections visible

---

## 🔍 Backend Testing

### Test Backend Translation Directly

```python
# Test translation service
from translation_service import translate_query_if_needed

# Test 1: Pure Kannada
result, metadata = translate_query_if_needed(
    "ಮನೋಜ್ ಅವರ ಸಂಪೂರ್ಣ ಮಾಹಿತಿ ತೋರಿಸಿ",
    "kannada"
)
print(f"Original: {metadata['original_query']}")
print(f"Translated: {result}")
print(f"Method: {metadata['translation_method']}")
print(f"Confidence: {metadata['translation_confidence']}")

# Test 2: Entity protection
result, metadata = translate_query_if_needed(
    "4HG23CS032 ಗಾಗಿ 8.5 CGPA ಮಾಹಿತಿ",
    "kannada"
)
print(f"Translated: {result}")
# Should preserve "4HG23CS032" and "8.5" and "CGPA"

# Test 3: English passthrough
result, metadata = translate_query_if_needed(
    "Show complete information about Manoj",
    "english"
)
print(f"Translated: {result}")
# Should remain unchanged
```

### Test Query Endpoint with Kannada

```bash
# Using curl
curl -X POST http://localhost:8000/api/query/generate \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "natural_query": "ಮನೋಜ್ ಅವರ ಸಂಪೂರ್ಣ ಮಾಹಿತಿ ತೋರಿಸಿ",
    "language": "kannada",
    "response_language": "kannada"
  }'
```

---

## 🐛 Common Issues & Fixes

### Issue 1: "No module named 'translation_service'"
**Fix**: Restart backend server after creating translation_service.py

### Issue 2: Google Translate API fails
**Symptom**: All Kannada queries fall back to keyword normalization  
**Fix**: Check internet connection, Google API may be rate-limited  
**Fallback**: System uses keyword normalization automatically

### Issue 3: Kannada typing still slow/laggy
**Check**: Look for remaining transliteration code in handleQueryChange  
**Fix**: Ensure handleQueryChange ONLY updates state, no API calls

### Issue 4: Translation corrupts USN/numbers
**Check**: Look at translation_metadata in backend logs  
**Fix**: Verify _protect_entities() is working correctly

### Issue 5: Fuzzy search not working for Kannada names
**Check**: Translation quality for names  
**Fix**: May need to add name transliteration rules

---

## 📊 Performance Benchmarks

### Typing Performance
- **Target**: <16ms per keystroke (60 FPS)
- **Maximum**: 50ms (still feels smooth)
- **Current**: Measure with browser DevTools Performance tab

### Translation Latency
- **Google API**: ~300-800ms
- **Keyword Fallback**: <10ms
- **Target**: <1 second total query time

### Query Execution
- **English**: Unchanged from baseline
- **Kannada**: +300-800ms (translation overhead)
- **Cached**: <50ms

---

## ✅ Definition of Done

Feature is complete ONLY when:

1. ✅ All 15 tests above pass
2. ✅ Kannada typing is smooth (Test 9)
3. ✅ English queries still work (Test 1)
4. ✅ Entities are protected (Tests 10-12)
5. ✅ Fuzzy search works for Kannada (Test 7)
6. ✅ Voice input works (Test 8)
7. ✅ Response language modes work (Tests 13-14)
8. ✅ No frontend translation during typing
9. ✅ Backend logs show translation metadata
10. ✅ No errors in browser console
11. ✅ No errors in backend logs
12. ✅ Code is clean (no duplicate logic)
13. ✅ Documentation is updated

---

## 🚀 Testing Procedure

1. **Restart Backend**:
   ```bash
   cd backend
   .venv\Scripts\activate
   python main.py
   ```

2. **Open Browser DevTools**:
   - Console tab: Check for errors
   - Network tab: Monitor API calls
   - Performance tab: Profile typing performance

3. **Test Each Query**:
   - Type query in textbox
   - Observe typing smoothness
   - Click Run Query
   - Verify results
   - Check backend console logs

4. **Verify Translation**:
   - Look for `[TRANSLATE]` logs in backend
   - Confirm translation method used
   - Check confidence score

5. **Test Regression**:
   - Run all existing English queries
   - Verify no broken functionality

---

## 📝 Test Results Template

```
Date: ___________
Tester: ___________

Test 1 (English):          ☐ Pass ☐ Fail
Test 2 (Kannada Unicode):  ☐ Pass ☐ Fail
Test 3 (Roman Kannada):    ☐ Pass ☐ Fail
Test 4 (Mixed):            ☐ Pass ☐ Fail
Test 5 (Academic):         ☐ Pass ☐ Fail
Test 6 (SGPA Filter):      ☐ Pass ☐ Fail
Test 7 (Fuzzy Search):     ☐ Pass ☐ Fail
Test 8 (Voice):            ☐ Pass ☐ Fail
Test 9 (Typing Perf):      ☐ Pass ☐ Fail
Test 10 (USN Protection):  ☐ Pass ☐ Fail
Test 11 (Number Protect):  ☐ Pass ☐ Fail
Test 12 (Branch Code):     ☐ Pass ☐ Fail
Test 13 (Kannada Response):☐ Pass ☐ Fail
Test 14 (Mixed Response):  ☐ Pass ☐ Fail
Test 15 (Complete Profile):☐ Pass ☐ Fail

Overall Status: ☐ All Pass ☐ Some Failures

Notes:
_________________________________________________
_________________________________________________
_________________________________________________
```

---

## 🎯 Next Steps After Testing

1. **If all tests pass**: Feature is complete ✅
2. **If typing is slow**: Review handleQueryChange, remove any async calls
3. **If translation fails**: Check translation_service.py, add more error handling
4. **If entities corrupted**: Improve _protect_entities() regex patterns
5. **If fuzzy search broken**: Verify translation quality for names

---

## 📚 Additional Resources

- Google Translate API: https://cloud.google.com/translate/docs
- Kannada Unicode: https://unicode.org/charts/PDF/U0C80.pdf
- Speech Recognition API: https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition

---

**Remember**: This is a BACKEND translation feature. The frontend should NEVER modify typed text during input. Translation happens ONLY on submit.
