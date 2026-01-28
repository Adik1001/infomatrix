import os
from google import genai

if "GOOGLE_API_KEY" not in os.environ:
    print("Please set GOOGLE_API_KEY")
else:
    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    try:
        print("Debugging model object structure...")
        for model in client.models.list():
            print(f"Model Name: {model.name}")
            print(f"Directory: {dir(model)}")
            # Stop after the first one
            break
    except Exception as e:
        print(f"Error: {e}")
