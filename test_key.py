import os
from google import genai

def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        api_key = input("Please paste your Gemini API Key here: ").strip()
        if not api_key:
            print("No API key provided. Exiting.")
            return
        
    client = genai.Client(api_key=api_key)
    print("Searching for available GenerateContent 'Flash' models on your account...")
    
    found_models = ()
    try:
        models = client.models.list()
        for m in models:
            if "flash" in m.name:
                print(f" ✅ Found working model string: {m.name}")
    except Exception as e:
        print("❌ Could not list models:", e)

if __name__ == "__main__":
    main()
