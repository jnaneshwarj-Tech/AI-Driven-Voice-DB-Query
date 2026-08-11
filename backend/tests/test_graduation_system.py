import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag_sql_generator import classify_query_intent
from graduation_manager import parse_usn_full


def test_classify_query_intent_handles_graduation_synonyms():
    cases = [
        ("Show graduated students", {"intent": "graduation_status", "status": "graduated"}),
        ("Show 2024 graduates", {"intent": "graduation_year", "year": 2024}),
        ("Show 2023 admission batch", {"intent": "admission_batch", "batch": 2023}),
        ("Show active students", {"intent": "graduation_status", "status": "active"}),
        ("Show Computer Science graduates", {"intent": "graduation_status", "branch": "CS"}),
    ]

    for query, expected in cases:
        result = classify_query_intent(query)
        for key, value in expected.items():
            assert result.get(key) == value, (query, result)


def test_lateral_entry_admission_batch_is_corrected():
    parsed = parse_usn_full("4HG24CS401")
    assert parsed is not None
    assert parsed["student_type"] == "Lateral Entry"
    assert parsed["admission_batch"] == 2023
    assert parsed["graduation_year"] == 2027
