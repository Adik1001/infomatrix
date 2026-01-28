import os
from google import genai

if "GOOGLE_API_KEY" not in os.environ:
    print("Please set GOOGLE_API_KEY environment variable.")
else:
    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    try:
        print("Listing available models:")
        for model in client.models.list():
            # Check if generateContent is supported
            if "generateContent" in model.supported_generation_methods:
                print(f"- {model.name} (Supported methods: {model.supported_generation_methods})")
    except Exception as e:
        print(f"Error listing models: {e}")
