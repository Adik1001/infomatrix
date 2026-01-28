import customtkinter as ctk
import os
import threading
import time
import json
import shutil
import sys
import pystray
import random
import math
import tkinter
import traceback
from tkinter import messagebox
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from google import genai
from PIL import Image, ImageDraw, ImageTk

# Setup
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("green")

CONFIG_FILE = "smart_folders.json"
HISTORY_FILE = "history.json"
STATS_FILE = "stats.json"
APP_CONFIG_FILE = "app_config.json"

# Colors
C_BG = "#1a1a2e"
C_ACCENT = "#e94560"
C_BUTTON = "#16213e"
C_TEXT = "#ffffff"

def load_json(file_path):
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as f: return json.load(f)
        except: return []
    return []

def save_json(file_path, data):
    with open(file_path, 'w') as f: json.dump(data, f, indent=4)

def load_stats():
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, 'r') as f: return json.load(f)
        except: pass
    return {"total_count": 0, "is_pro": False}

def save_stats(stats):
    with open(STATS_FILE, 'w') as f: json.dump(stats, f, indent=4)

def load_app_config():
    default = {"api_key": "", "model": "gemini-2.5-flash", "track_folder": "", "dest_folder": ""}
    if os.path.exists(APP_CONFIG_FILE):
        try:
            with open(APP_CONFIG_FILE, 'r') as f:
                data = json.load(f)
                default.update(data)
                default["model"] = "gemini-2.5-flash"
        except: pass
    return default

def save_app_config(config):
    config["model"] = "gemini-2.5-flash"
    with open(APP_CONFIG_FILE, 'w') as f: json.dump(config, f, indent=4)

def extract_json(text):
    try:
        text = text.strip()
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            return json.loads(text[start:end+1])
        return json.loads(text)
    except: return None

class ScreenshotHandler(FileSystemEventHandler):
    def __init__(self, app_callback, config, folders):
        self.app_callback = app_callback
        self.config = config
        self.folders = folders

    def on_created(self, event):
        if event.is_directory: return
        filename = event.src_path
        ext = os.path.splitext(filename)[1].lower()
        if ext in ['.png', '.jpg', '.jpeg']:
            self.app_callback("detect", filename)
            threading.Thread(target=self.process_image_thread, args=(filename,)).start()

    def process_image_thread(self, file_path):
        time.sleep(2)
        self.process_image(file_path)

    def process_image(self, file_path):
        try:
            for _ in range(3):
                try:
                    with Image.open(file_path) as img:
                        img.verify()
                    break
                except:
                    time.sleep(1)
            
            result = self.analyze_image(file_path)
            if result:
                new_name = result.get("filename")
                folder_match = result.get("folder")
                
                if new_name:
                    old_name = os.path.basename(file_path)
                    new_path = self.rename_file(file_path, new_name)
                    
                    if new_path:
                        final_name = os.path.basename(new_path)
                        self.app_callback("success", {"path": new_path, "old": old_name, "new": final_name})
                        if folder_match: self.sort_file(new_path, folder_match)
        except Exception as e:
            print(f"Error: {e}")
            traceback.print_exc()

    def analyze_image(self, file_path):
        try:
            client = genai.Client(api_key=self.config["api_key"])
            img = Image.open(file_path)
            
            folder_info = [f"{f['name']} (Description: {f.get('description', '')})" for f in self.folders]
            categories_prompt = "No specific folders."
            if folder_info:
                categories_prompt = f"Match with one of these folders if appropriate based on name and description: {'; '.join(folder_info)}."
            
            prompt = (
                f"Analyze this image. Provide a JSON object with two keys:\n"
                f"1. 'filename': A short, descriptive filename (2-5 words), using underscores instead of spaces. No extension.\n"
                f"2. 'folder': The exact name of the matching folder from the list below, or null if no match.\n"
                f"{categories_prompt}\n"
                f"Respond ONLY with valid JSON."
            )
            
            response = client.models.generate_content(model=self.config["model"], contents=[prompt, img])
            if response.text:
                return extract_json(response.text)
        except Exception as e:
            print(f"Analyze Error: {e}")
            traceback.print_exc()
            return None

    def rename_file(self, file_path, label):
        directory = os.path.dirname(file_path)
        ext = os.path.splitext(file_path)[1]
        safe_label = "".join([c for c in label if c.isalnum() or c in (' ', '-', '_')]).strip().replace(' ', '_')[:50]
        new_name = f"{safe_label}{ext}"
        new_path = os.path.join(directory, new_name)
        counter = 1
        while os.path.exists(new_path):
            new_name = f"{safe_label}_{counter}{ext}"
            new_path = os.path.join(directory, new_name)
            counter += 1
        try:
            os.rename(file_path, new_path)
            return new_path
        except: return None

    def sort_file(self, file_path, folder_name):
        try:
            dest_base = self.config.get("dest_folder")
            if not dest_base or not os.path.exists(dest_base):
                dest_base = os.path.dirname(file_path)
            
            target_dir = os.path.join(dest_base, folder_name)
            if not os.path.exists(target_dir): os.makedirs(target_dir)
            
            filename = os.path.basename(file_path)
            target_path = os.path.join(target_dir, filename)
            
            if os.path.exists(target_path):
                base, ext = os.path.splitext(filename)
                target_path = os.path.join(target_dir, f"{base}_{int(time.time())}{ext}")
            
            shutil.copy2(file_path, target_path)
            print(f"Copied to {target_path}")
        except Exception as e:
            print(f"Sort Error: {e}")
            traceback.print_exc()

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("AI Renamer")
        self.geometry("900x600")
        self.configure(fg_color=C_BG)
        
        self.stats = load_stats()
        self.smart_folders = load_json(CONFIG_FILE)
        self.history = load_json(HISTORY_FILE)
        self.app_config = load_app_config()
        
        if not self.app_config["track_folder"]:
            self.app_config["track_folder"] = os.path.join(os.environ['USERPROFILE'], 'Pictures', 'Screenshots')

        self.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)
        self.setup_tray()
        
        # Container for pages
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True)
        
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)
        
        self.frames = {}
        for F in (MainMenu, SettingsPage, FoldersPage, GalleryPage):
            page_name = F.__name__
            frame = F(parent=self.container, controller=self)
            self.frames[page_name] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.show_frame("MainMenu")
        
        self.observer = None
        self.monitoring = False

    def show_frame(self, page_name):
        frame = self.frames[page_name]
        frame.tkraise()
        if hasattr(frame, 'refresh'): frame.refresh()

    def setup_tray(self):
        image = Image.new('RGB', (64, 64), color=(233, 69, 96))
        draw = ImageDraw.Draw(image)
        draw.ellipse((16, 16, 48, 48), fill="white")
        menu = pystray.Menu(pystray.MenuItem("Open", self.show_window), pystray.MenuItem("Exit", self.quit_app))
        self.tray_icon = pystray.Icon("AI Renamer", image, "AI Renamer", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def minimize_to_tray(self): self.withdraw()
    def show_window(self, icon=None, item=None): self.deiconify(); self.lift()
    def quit_app(self, icon=None, item=None): self.tray_icon.stop(); self.quit(); sys.exit()

    def toggle_monitoring(self):
        if not self.monitoring:
            if not self.check_limit():
                messagebox.showinfo("Limit Reached", "Upgrade to Pro! Limit is 50.")
                return False
            if not self.app_config["api_key"]:
                messagebox.showwarning("Config", "Please set API Key in Settings.")
                self.show_frame("SettingsPage")
                return False
            
            path = self.app_config["track_folder"]
            if not os.path.exists(path):
                messagebox.showerror("Error", f"Folder not found: {path}\nPlease check Settings.")
                return False
            
            try:
                self.observer = Observer()
                handler = ScreenshotHandler(self.handle_event, self.app_config, self.smart_folders)
                self.observer.schedule(handler, path, recursive=False)
                self.observer.start()
                self.monitoring = True
                return True 
            except Exception as e:
                traceback.print_exc()
                messagebox.showerror("Error", f"Failed to start monitoring: {e}")
                return False
        else:
            if self.observer: 
                self.observer.stop()
                self.observer.join()
            self.observer = None
            self.monitoring = False
            return False 

    def check_limit(self):
        limit = 20000 if self.stats.get("is_pro") else 50
        return self.stats.get("total_count", 0) < limit

    def handle_event(self, type_, data):
        if type_ == "success":
            self.stats["total_count"] = self.stats.get("total_count", 0) + 1
            save_stats(self.stats)
            self.history.append(data)
            save_json(HISTORY_FILE, self.history)
            self.frames["MainMenu"].update_ui()

class MainMenu(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color=C_BG)
        self.controller = controller
        
        # Full Screen Canvas
        self.canvas = ctk.CTkCanvas(self, bg=C_BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        
        # Load BG
        self.bg_image_pil = None
        self.bg_image_tk = None
        if os.path.exists("background.png"):
            try:
                self.bg_image_pil = Image.open("background.png")
            except: pass
            
        self.bind("<Configure>", self.on_resize)
        
        # Animation State
        self.angle_offset = 0
        self.is_animating = False
        self.animation_id = None
        
        # Progress State
        self.progress_val = 0
        self.limit_val = 50
        
        # UI Elements (Placed on top)
        # Upgrade
        ctk.CTkButton(self, text="UPGRADE 👑", fg_color="#ffd700", text_color="black", width=120, height=40, corner_radius=20, font=("Arial", 12, "bold")).place(x=30, y=30)
        # Settings
        ctk.CTkButton(self, text="⚙️", width=50, height=50, corner_radius=25, fg_color="transparent", border_width=2, border_color="white", text_color="white", font=("Arial", 20),
                      command=lambda: controller.show_frame("SettingsPage")).place(relx=1.0, x=-80, y=30)
        
        # Power Button (Centered)
        self.power_btn = ctk.CTkButton(self, text="START", width=100, height=100, corner_radius=50, 
                                       fg_color=C_ACCENT, hover_color="#d63d54", 
                                       font=("Arial", 20, "bold"),
                                       command=self.toggle)
        self.power_btn.place(relx=0.5, rely=0.45, anchor="center")
        
        # Bottom Buttons
        ctk.CTkButton(self, text="Smart Folders", width=200, height=60, corner_radius=20, fg_color=C_BUTTON, font=("Arial", 16, "bold"),
                      command=lambda: controller.show_frame("FoldersPage")).place(relx=0.5, rely=1.0, y=-100, x=-110, anchor="n")
                      
        ctk.CTkButton(self, text="Gallery", width=200, height=60, corner_radius=20, fg_color=C_BUTTON, font=("Arial", 16, "bold"),
                      command=lambda: controller.show_frame("GalleryPage")).place(relx=0.5, rely=1.0, y=-100, x=110, anchor="n")
        
        # Counter Label
        self.counter_label = ctk.CTkLabel(self, text="0 / 50", font=("Arial", 16, "bold"), text_color="white", fg_color="transparent")
        self.counter_label.place(relx=0.5, rely=0.45, y=80, anchor="center")

    def on_resize(self, event):
        w, h = event.width, event.height
        if self.bg_image_pil:
             img = self.bg_image_pil.resize((w, h))
             self.bg_image_tk = ImageTk.PhotoImage(img)
        self.draw_canvas()

    def draw_canvas(self):
        self.canvas.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        
        # Draw BG
        if self.bg_image_tk:
            self.canvas.create_image(0, 0, image=self.bg_image_tk, anchor="nw")
            
        # Draw Ring (Centered)
        cx, cy = w/2, h*0.45
        r = 175 # 350/2
        
        # Background ring
        self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r, outline="#333", width=15)
        
        # Progress Arc
        if self.limit_val > 0:
            angle = (self.progress_val / self.limit_val) * 360
            if angle > 360: angle = 360
            self.canvas.create_arc(cx-r, cy-r, cx+r, cy+r, start=90, extent=-angle, outline="#2ecc71", width=15, style="arc")
            
        # Spinner (Loading)
        if self.is_animating:
            r_spin = r + 20
            self.canvas.create_arc(cx-r_spin, cy-r_spin, cx+r_spin, cy+r_spin, start=self.angle_offset, extent=80, outline="#ffd700", width=6, style="arc")
            self.canvas.create_arc(cx-r_spin, cy-r_spin, cx+r_spin, cy+r_spin, start=self.angle_offset+180, extent=80, outline="#ffd700", width=6, style="arc")

    def animate(self):
        if self.is_animating:
            self.angle_offset = (self.angle_offset - 15) % 360
            self.draw_canvas()
            self.animation_id = self.after(30, self.animate)

    def update_ui(self):
        count = self.controller.stats.get("total_count", 0)
        self.progress_val = count
        self.limit_val = 50
        self.counter_label.configure(text=f"{count} / 50")
        self.draw_canvas()

    def toggle(self):
        if self.controller.monitoring:
            self.controller.toggle_monitoring()
            self.update_status(False)
        else:
            self.power_btn.configure(text="LOADING...", fg_color="#f59e0b", state="disabled")
            self.is_animating = True
            self.animate()
            self.after(3000, self.finish_start)

    def finish_start(self):
        self.is_animating = False
        self.power_btn.configure(state="normal")
        if self.controller.toggle_monitoring():
            self.update_status(True)
        else:
            self.update_status(False)
        self.draw_canvas()

    def update_status(self, running):
        text = "STOP" if running else "START"
        color = "#2ecc71" if running else "#ef4444"
        hover = "#27ae60" if running else "#d63d54"
        self.power_btn.configure(text=text, fg_color=color, hover_color=hover)

    def refresh(self): self.update_ui()

class SettingsPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color=C_BG)
        self.controller = controller
        
        ctk.CTkButton(self, text="< Back", width=80, fg_color="transparent", command=lambda: controller.show_frame("MainMenu")).pack(anchor="w", padx=20, pady=20)
        ctk.CTkLabel(self, text="Settings", font=("Arial", 24, "bold")).pack(pady=10)
        
        form = ctk.CTkFrame(self, fg_color=C_BUTTON)
        form.pack(pady=20, padx=40, fill="x")
        
        ctk.CTkLabel(form, text="API Key").pack(anchor="w", padx=20, pady=(20,5))
        self.api_entry = ctk.CTkEntry(form, width=400, show="*"); self.api_entry.pack(padx=20)
        self.add_context_menu(self.api_entry)
        
        ctk.CTkLabel(form, text="Track Folder").pack(anchor="w", padx=20, pady=(10,5))
        self.track_var = ctk.StringVar()
        ctk.CTkEntry(form, textvariable=self.track_var, width=400, state="readonly").pack(padx=20)
        ctk.CTkButton(form, text="Browse", command=lambda: self.browse(self.track_var)).pack(pady=5)
        
        ctk.CTkLabel(form, text="Destination Folder (Optional)").pack(anchor="w", padx=20, pady=(10,5))
        self.dest_var = ctk.StringVar()
        ctk.CTkEntry(form, textvariable=self.dest_var, width=400, state="readonly").pack(padx=20)
        ctk.CTkButton(form, text="Browse", command=lambda: self.browse(self.dest_var)).pack(pady=5)
        
        ctk.CTkButton(self, text="Save Settings", fg_color=C_ACCENT, command=self.save).pack(pady=20)

    def refresh(self):
        c = self.controller.app_config
        self.api_entry.delete(0, "end"); self.api_entry.insert(0, c["api_key"])
        self.track_var.set(c["track_folder"])
        self.dest_var.set(c["dest_folder"])

    def save(self):
        self.controller.app_config.update({
            "api_key": self.api_entry.get(),
            "model": "gemini-2.5-flash",
            "track_folder": self.track_var.get(),
            "dest_folder": self.dest_var.get()
        })
        save_app_config(self.controller.app_config)
        self.controller.show_frame("MainMenu")

    def browse(self, var): var.set(ctk.filedialog.askdirectory() or var.get())
    
    def add_context_menu(self, widget):
        menu = tkinter.Menu(widget, tearoff=0)
        menu.add_command(label="Paste", command=lambda: widget.event_generate("<<Paste>>"))
        widget.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))

class FoldersPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color=C_BG)
        self.controller = controller
        
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=20)
        ctk.CTkButton(header, text="< Back", width=80, fg_color="transparent", command=lambda: controller.show_frame("MainMenu")).pack(side="left")
        ctk.CTkLabel(header, text="Smart Folders", font=("Arial", 24, "bold")).pack(side="left", padx=20)
        ctk.CTkButton(header, text="+ Add", fg_color=C_ACCENT, width=80, command=self.add_rule).pack(side="right")
        
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=20)

    def refresh(self):
        for w in self.scroll.winfo_children(): w.destroy()
        for i, f in enumerate(self.controller.smart_folders):
            row = ctk.CTkFrame(self.scroll, fg_color=C_BUTTON)
            row.pack(fill="x", pady=5)
            
            lbl_name = ctk.CTkLabel(row, text=f['name'], font=("Arial", 16, "bold"), cursor="hand2")
            lbl_name.pack(side="left", padx=15, pady=10)
            lbl_name.bind("<Button-1>", lambda e, name=f['name']: self.open_folder(name))
            
            ctk.CTkLabel(row, text=f.get('description', '')).pack(side="left", padx=10)
            ctk.CTkButton(row, text="Del", width=50, fg_color="#ef4444", command=lambda x=i: self.delete(x)).pack(side="right", padx=10)

    def open_folder(self, folder_name):
        dest_base = self.controller.app_config.get("dest_folder")
        if not dest_base or not os.path.exists(dest_base):
            dest_base = self.controller.app_config.get("track_folder")
            if not dest_base: return
            
        path = os.path.join(dest_base, folder_name)
        if os.path.exists(path):
            os.startfile(path)
        else:
            messagebox.showinfo("Info", f"Folder '{folder_name}' does not exist yet.")

    def add_rule(self):
        d = ctk.CTkToplevel(self); d.geometry("400x300"); d.title("Add Rule"); d.attributes("-topmost", True)
        ctk.CTkLabel(d, text="Name").pack(pady=10); n = ctk.CTkEntry(d); n.pack()
        ctk.CTkLabel(d, text="Description").pack(pady=10); desc = ctk.CTkEntry(d); desc.pack()
        def s():
            if n.get() and desc.get():
                self.controller.smart_folders.append({"name":n.get(), "description":desc.get()})
                save_json(CONFIG_FILE, self.controller.smart_folders)
                self.refresh(); d.destroy()
        ctk.CTkButton(d, text="Save", command=s).pack(pady=20)

    def delete(self, idx):
        self.controller.smart_folders.pop(idx)
        save_json(CONFIG_FILE, self.controller.smart_folders)
        self.refresh()

class GalleryPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color=C_BG)
        self.controller = controller
        
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=20)
        ctk.CTkButton(header, text="< Back", width=80, fg_color="transparent", command=lambda: controller.show_frame("MainMenu")).pack(side="left")
        ctk.CTkLabel(header, text="Gallery", font=("Arial", 24, "bold")).pack(side="left", padx=20)
        
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=20)

    def refresh(self):
        for w in self.scroll.winfo_children(): w.destroy()
        # Grid layout for images
        self.scroll.grid_columnconfigure((0,1,2,3), weight=1)
        
        row = 0; col = 0
        for item in reversed(self.controller.history[-50:]): # Show last 50
            path = item.get("path")
            if path and os.path.exists(path):
                card = ctk.CTkFrame(self.scroll, fg_color=C_BUTTON)
                card.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
                
                try:
                    img = ctk.CTkImage(Image.open(path), size=(150, 100))
                    btn = ctk.CTkButton(card, text="", image=img, fg_color="transparent", hover=False, 
                                        command=lambda p=path: os.startfile(p))
                    btn.pack(pady=5)
                except: ctk.CTkLabel(card, text="Error").pack()
                
                ctk.CTkLabel(card, text=item.get("new", "")[:20], font=("Arial", 10)).pack(pady=(0,5))
                
                col += 1
                if col > 3: col=0; row+=1

if __name__ == "__main__":
    app = App()
    app.mainloop()
