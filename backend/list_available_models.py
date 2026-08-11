#!/usr/bin/env python3
"""List all available Gemini models from the API"""

import requests
from config import settings

def list_models():
    api_key = settings.GEMINI_API_KEY
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        print("Available Gemini Models:")
        print("=" * 80)
        
        if "models" in data:
            for model in data["models"]:
                name = model.get("name", "").replace("models/", "")
                display_name = model.get("displayName", "")
                supported_methods = model.get("supportedGenerationMethods", [])
                
                # Only show models that support generateContent
                if "generateContent" in supported_methods:
                    print(f"\n✓ {name}")
                    print(f"  Display Name: {display_name}")
                    print(f"  Methods: {', '.join(supported_methods)}")
        else:
            print("No models found in response")
            print(data)
            
    except Exception as e:
        print(f"Error: {e}")
        if hasattr(e, 'response') and e.response:
            print(e.response.text)

if __name__ == "__main__":
    list_models()
