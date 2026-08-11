#!/usr/bin/env python3
"""Quick test to verify Gemini API connection with new model"""

from llm_service import llm_service

def test_llm():
    print(f"Testing LLM Service...")
    print(f"Model: {llm_service.model}")
    print(f"Fallback models: {llm_service.fallback_models}")
    print(f"API Key present: {'Yes' if llm_service.api_key else 'No'}")
    print()
    
    # Simple test query
    test_prompt = "Generate a SQL query to select all students from students table"
    print(f"Test prompt: {test_prompt}")
    print("Sending request to Gemini API...")
    print()
    
    result = llm_service.generate_query(test_prompt)
    
    if result.startswith("ERROR"):
        print("❌ TEST FAILED")
        print(result)
        return False
    else:
        print("✅ TEST PASSED")
        print(f"Response: {result}")
        return True

if __name__ == "__main__":
    success = test_llm()
    exit(0 if success else 1)
