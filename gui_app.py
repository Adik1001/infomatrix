import customtkinter as ctk
import os
import sys
import threading
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from google import genai
from PIL import Image

# Setup
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class ScreenshotHandler(FileSystemEventHandler):
    def __init__(self, log_callback, model_name):
        self.log_callback = log_callback
        self.model_name = model_name

    def on_created(self, event):
        if event.is_directory:
            return
        
        filename = event.src_path
        ext = os.path.splitext(filename)[1].lower()
        
        if ext in ['.png', '.jpg', '.jpeg']:
            self.log_callback(f"[DETECTED] {os.path.basename(filename)}")
            # Wait a moment for file write
            time.sleep(2)
            # Process in a separate thread to avoid blocking observer? 
            # Watchdog callbacks run in the observer thread, which is separate from Main GUI.
            # But process_image calls API which is slow. It's fine for Observer thread to block slightly, 
            # but if it blocks too long, we might miss events? 
            # For this simple app, blocking the observer thread is okay as long as events are queued by OS.
            self.process_image(filename)

    def process_image(self, file_path):
        try:
            label = self.get_image_label(file_path)
            if label:
                self.log_callback(f"[ANALYSIS] Suggestion: {label}")
                self.rename_file(file_path, label)
            else:
                self.log_callback("[ANALYSIS] No confident label found.")
        except Exception as e:
            self.log_callback(f"[ERROR] Processing failed: {e}")

    def get_image_label(self, file_path):
        try:
            # Re-instantiate client here to ensure it picks up the latest env var or passed key
            client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))
            
            img = Image.open(file_path)
            prompt = "Analyze this image and provide a short, descriptive filename (2-5 words). Use only alphanumeric characters, spaces, or underscores. Do not include the file extension. Be specific but concise."
            
            response = client.models.generate_content(
                model=self.model_name,
                contents=[prompt, img]
            )
            
            if response.text:
                return response.text.strip()
            return None
        except Exception as e:
            self.log_callback(f"[API ERROR] {e}")
            return None

    def rename_file(self, file_path, label):
        directory = os.path.dirname(file_path)
        ext = os.path.splitext(file_path)[1]
        
        safe_label = "".join([c for c in label if c.isalnum() or c in (' ', '-', '_')]).strip()
        safe_label = safe_label.replace(' ', '_')
        if len(safe_label) > 50: safe_label = safe_label[:50]
        
        new_name = f"{safe_label}{ext}"
        new_path = os.path.join(directory, new_name)
        
        counter = 1
        while os.path.exists(new_path):
            new_name = f"{safe_label}_{counter}{ext}"
            new_path = os.path.join(directory, new_name)
            counter += 1
            
        try:
            os.rename(file_path, new_path)
            self.log_callback(f"[SUCCESS] Renamed to: {new_name}")
        except Exception as e:
            self.log_callback(f"[ERROR] Rename failed: {e}")

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("AI Screenshot Renamer")
        self.geometry("900x600")
        
        # Grid layout
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # Sidebar
        self.sidebar = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(5, weight=1)
        
        self.logo = ctk.CTkLabel(self.sidebar, text="AI Renamer", font=ctk.CTkFont(size=24, weight="bold"))
        self.logo.grid(row=0, column=0, padx=20, pady=(20, 10))
        
        self.api_key_label = ctk.CTkLabel(self.sidebar, text="Google API Key:")
        self.api_key_label.grid(row=1, column=0, padx=20, pady=(10, 0), sticky="w")
        
        self.api_key_entry = ctk.CTkEntry(self.sidebar, placeholder_text="Paste Key Here", show="*")
        self.api_key_entry.grid(row=2, column=0, padx=20, pady=(0, 10), sticky="ew")
        
        # Helper to load key from env if exists
        if "GOOGLE_API_KEY" in os.environ:
            self.api_key_entry.insert(0, os.environ["GOOGLE_API_KEY"])
        
        self.fetch_btn = ctk.CTkButton(self.sidebar, text="Fetch Models", command=self.fetch_models_threaded)
        self.fetch_btn.grid(row=3, column=0, padx=20, pady=10)
        
        self.model_label = ctk.CTkLabel(self.sidebar, text="Select Model:")
        self.model_label.grid(row=4, column=0, padx=20, pady=(10, 0), sticky="w")
        
        self.model_option = ctk.CTkOptionMenu(self.sidebar, values=["gemini-1.5-flash", "gemini-2.0-flash-exp"])
        self.model_option.grid(row=5, column=0, padx=20, pady=(0, 10), sticky="ew")
        
        self.start_btn = ctk.CTkButton(self.sidebar, text="START MONITORING", command=self.toggle_monitoring, 
                                       fg_color="#2ecc71", hover_color="#27ae60", height=40, font=ctk.CTkFont(weight="bold"))
        self.start_btn.grid(row=6, column=0, padx=20, pady=20, sticky="ew")

        # Main Log Area
        self.log_frame = ctk.CTkFrame(self)
        self.log_frame.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        self.log_frame.grid_rowconfigure(1, weight=1)
        self.log_frame.grid_columnconfigure(0, weight=1)
        
        self.log_label = ctk.CTkLabel(self.log_frame, text="Activity Log", font=ctk.CTkFont(size=16))
        self.log_label.grid(row=0, column=0, padx=10, pady=10, sticky="w")
        
        self.log_area = ctk.CTkTextbox(self.log_frame, width=400)
        self.log_area.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        self.log_area.configure(state="disabled") # Read-only
        
        self.observer = None
        self.monitoring = False
        
    def log(self, message):
        # Update UI in main thread (safe because ctk mostly handles it, but good practice)
        self.log_area.configure(state="normal")
        self.log_area.insert("end", f"{message}\n")
        self.log_area.see("end")
        self.log_area.configure(state="disabled")

    def fetch_models_threaded(self):
        threading.Thread(target=self.fetch_models, daemon=True).start()

    def fetch_models(self):
        key = self.api_key_entry.get().strip()
        if not key:
            self.log("[ERROR] Enter API Key first.")
            return
        
        os.environ["GOOGLE_API_KEY"] = key
        self.log("[INFO] Fetching models...")
        
        try:
            client = genai.Client(api_key=key)
            models = []
            for m in client.models.list():
                name = m.name.replace('models/', '')
                # Basic check
                if 'gemini' in name:
                    models.append(name)
            
            if models:
                self.log(f"[INFO] Found {len(models)} models.")
                # Update dropdown in main thread? customTkinter usually handles this ok
                self.model_option.configure(values=models)
                self.model_option.set(models[0])
            else:
                self.log("[WARN] No Gemini models found.")
        except Exception as e:
            self.log(f"[ERROR] Fetch failed: {e}")

    def toggle_monitoring(self):
        if not self.monitoring:
            # Start
            key = self.api_key_entry.get().strip()
            if not key:
                self.log("[ERROR] Please enter a valid Google API Key.")
                return
            
            os.environ["GOOGLE_API_KEY"] = key
            
            path = r"c:\Users\user\Pictures\Screenshots"
            if not os.path.exists(path):
                try:
                    os.makedirs(path)
                    self.log(f"[INFO] Created folder: {path}")
                except Exception as e:
                    self.log(f"[ERROR] Could not create folder: {e}")
                    return

            model = self.model_option.get()
            self.log(f"[INFO] Starting observer on {path}")
            self.log(f"[INFO] Using model: {model}")
            
            self.observer = Observer()
            handler = ScreenshotHandler(self.log, model)
            self.observer.schedule(handler, path, recursive=False)
            
            try:
                self.observer.start()
                self.monitoring = True
                self.start_btn.configure(text="STOP MONITORING", fg_color="#e74c3c", hover_color="#c0392b")
                self.api_key_entry.configure(state="disabled")
            except Exception as e:
                self.log(f"[ERROR] Failed to start: {e}")
        else:
            # Stop
            self.log("[INFO] Stopping observer...")
            if self.observer:
                self.observer.stop()
                self.observer.join()
            self.observer = None
            self.monitoring = False
            self.start_btn.configure(text="START MONITORING", fg_color="#2ecc71", hover_color="#27ae60")
            self.api_key_entry.configure(state="normal")
            self.log("[INFO] Stopped.")

if __name__ == "__main__":
    app = App()
    app.mainloop()
