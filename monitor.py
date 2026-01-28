import sys
import time
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from google import genai
from PIL import Image

# Global variable to store the selected model name
SELECTED_MODEL = None

class ScreenshotHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        
        filename = event.src_path
        ext = os.path.splitext(filename)[1].lower()
        
        if ext in ['.png', '.jpg', '.jpeg']:
            print(f"[EVENT] New file detected: {os.path.basename(filename)}")
            # Wait a moment for the file to be fully written/released
            time.sleep(2)
            self.process_image(filename)

    def process_image(self, file_path):
        try:
            # Analyze image
            label = self.get_image_label(file_path)
            if label:
                print(f"[ANALYSIS] Suggested name: {label}")
                self.rename_file(file_path, label)
            else:
                print("[ANALYSIS] No confident label found.")
        except Exception as e:
            print(f"[ERROR] Failed to process image: {e}")

    def get_image_label(self, file_path):
        """Uses Google Gen AI SDK to describe the image."""
        global SELECTED_MODEL
        if not SELECTED_MODEL:
            print("[ERROR] No valid model selected.")
            return None
            
        try:
            client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
            
            # Load the image
            img = Image.open(file_path)
            
            # Prompt for the model
            prompt = "Analyze this image and provide a short, descriptive filename (2-5 words). Use only alphanumeric characters, spaces, or underscores. Do not include the file extension. Be specific but concise."
            
            response = client.models.generate_content(
                model=SELECTED_MODEL,
                contents=[prompt, img]
            )
            
            if response.text:
                return response.text.strip()
            return None
        except Exception as e:
            print(f"[API ERROR] {e}")
            return None

    def rename_file(self, file_path, label):
        directory = os.path.dirname(file_path)
        ext = os.path.splitext(file_path)[1]
        
        # Sanitize label for filename
        safe_label = "".join([c for c in label if c.isalnum() or c in (' ', '-', '_')]).strip()
        safe_label = safe_label.replace(' ', '_')
        
        # Ensure the filename isn't too long
        if len(safe_label) > 50:
            safe_label = safe_label[:50]
            
        new_name = f"{safe_label}{ext}"
        new_path = os.path.join(directory, new_name)
        
        # Handle duplicates
        counter = 1
        while os.path.exists(new_path):
            new_name = f"{safe_label}_{counter}{ext}"
            new_path = os.path.join(directory, new_name)
            counter += 1
            
        try:
            os.rename(file_path, new_path)
            print(f"[SUCCESS] Renamed to: {new_name}")
        except Exception as e:
            print(f"[ERROR] Could not rename file: {e}")

def select_model():
    """Dynamically selects a supported model."""
    global SELECTED_MODEL
    try:
        print("Finding available models...")
        client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
        
        available_models = []
        for model in client.models.list():
            # Debug: print first model attributes to help diagnose if needed
            if not available_models: 
                print(f"[DEBUG] First model object keys: {dir(model)}")
            
            # Try to determine if it supports generation using multiple attribute names
            supports_gen = False
            methods = getattr(model, 'supported_generation_methods', [])
            if not methods:
                methods = getattr(model, 'supportedGenerationMethods', [])
            
            if methods and "generateContent" in methods:
                supports_gen = True
            
            # Heuristic: if it has 'gemini' in the name, it's likely a gen model
            if "gemini" in model.name:
                supports_gen = True
                
            if supports_gen:
                print(f"[DEBUG] Found candidate: {model.name}")
                available_models.append(model.name)
        
        # Priorities (try these first)
        priorities = [
            'gemini-1.5-flash', 
            'gemini-1.5-flash-001',
            'gemini-2.0-flash-exp',
            'gemini-1.5-pro',
            'gemini-1.0-pro'
        ]
        
        for priority in priorities:
            for m in available_models:
                # m usually looks like "models/gemini-1.5-flash"
                if m == priority or m == f"models/{priority}" or m.endswith(f"/{priority}"):
                    SELECTED_MODEL = m.replace('models/', '') # SDK often wants the short name
                    print(f"[INFO] Selected model: {SELECTED_MODEL}")
                    return

        if available_models:
            SELECTED_MODEL = available_models[0].replace('models/', '')
            print(f"[INFO] Fallback model selected: {SELECTED_MODEL}")
        else:
            print("[ERROR] No models found. Using default fallback.")
            SELECTED_MODEL = 'gemini-1.5-flash'

    except Exception as e:
        print(f"[ERROR] Could not list models: {e}")
        SELECTED_MODEL = 'gemini-1.5-flash'
        print(f"[INFO] Defaulting to {SELECTED_MODEL}")

if __name__ == "__main__":
    # Check for credentials
    if "GOOGLE_API_KEY" not in os.environ:
        print("----------------------------------------------------------------")
        print("[WARNING] GOOGLE_API_KEY environment variable not set.")
        print("Please set it to your Google Generative AI API key.")
        print("Example (Windows PowerShell): $env:GOOGLE_API_KEY='your_api_key'")
        print("Example (CMD): set GOOGLE_API_KEY=your_api_key")
        print("----------------------------------------------------------------")
    else:
        select_model()
    
    path = r"c:\Users\user\Pictures\Screenshots"
    
    if not os.path.exists(path):
        try:
            os.makedirs(path)
            print(f"[INFO] Created directory: {path}")
        except Exception as e:
            print(f"[ERROR] Could not create directory {path}: {e}")
            sys.exit(1)

    event_handler = ScreenshotHandler()
    observer = Observer()
    observer.schedule(event_handler, path, recursive=False)
    
    observer.start()
    print(f"Monitoring {path} for screenshots...")
    print("Press Ctrl+C to stop.")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
