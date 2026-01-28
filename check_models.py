import json
import os
from google import genai

try:
    if os.path.exists("app_config.json"):
        with open("app_config.json", 'r') as f:
            config = json.load(f)
        api_key = config.get("api_key")
    else:
        api_key = os.environ.get("GOOGLE_API_KEY")

    if not api_key:
        print("No API Key found")
        exit()
    
    print(f"Using API Key: {api_key[:5]}...")
    client = genai.Client(api_key=api_key)
    print("Listing ALL models:")
    count = 0
    for m in client.models.list():
        print(f"Name: {m.name}")
        # print(f"Dir: {dir(m)}") 
        count += 1
    print(f"Total found: {count}")
        
except Exception as e:
    print(f"Error: {e}")
