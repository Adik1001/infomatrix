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
from PIL import Image, ImageDraw, ImageTk, ImageEnhance, ImageFilter

# --- THEME CONSTANTS ---
THEME_BG_DARK = "#000000"
THEME_CARD_DARK = "#141414"
THEME_ACCENT_RED = "#FF4B4B"
THEME_ACCENT_GREEN = "#00D68F"
THEME_TEXT_WHITE = "#FFFFFF"
THEME_TEXT_GRAY = "#888888"
THEME_BG_LIGHT = "#FFFFFF"
THEME_TEXT_DARK = "#000000"

CONFIG_FILE = "smart_folders.json"
HISTORY_FILE = "history.json"
STATS_FILE = "stats.json"
APP_CONFIG_FILE = "app_config.json"

# --- HELPERS ---
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

# --- LOGIC ---
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
            msg = str(e).lower()
            if "403" in msg or "leaked" in msg or "permission_denied" in msg:
                self.app_callback("critical_error", "Your API Key is invalid or leaked.\nPlease update it in Settings.")
            else:
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
            msg = str(e).lower()
            if "403" in msg or "leaked" in msg or "permission_denied" in msg:
                raise e
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
                dest_base = self.controller.app_config.get("track_folder")
                if not dest_base: return
            
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

# --- APP ---
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("AI Renamer")
        self.geometry("1000x700")
        self.configure(fg_color=THEME_BG_DARK)
        
        self.stats = load_stats()
        self.smart_folders = load_json(CONFIG_FILE)
        self.history = load_json(HISTORY_FILE)
        self.app_config = load_app_config()
        
        if not self.app_config["track_folder"]:
            self.app_config["track_folder"] = os.path.join(os.environ['USERPROFILE'], 'Pictures', 'Screenshots')

        self.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)
        self.setup_tray()
        
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
            self.after(0, self.frames["MainMenu"].update_ui)
        elif type_ == "critical_error":
            self.after(0, lambda: self.handle_critical_error(data))

    def handle_critical_error(self, message):
        if self.monitoring:
            self.toggle_monitoring()
            self.frames["MainMenu"].update_status(False)
        messagebox.showerror("Critical Error", message)
        self.show_frame("SettingsPage")

# --- PAGES ---

class MainMenu(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color=THEME_BG_DARK)
        self.controller = controller
        
        self.angle_offset = 0
        self.is_animating = False
        self.progress_val = 0
        self.limit_val = 50
        self.glowing = True

        # Create glow effect image
        glow_size = 250
        self.glow_image_pil = Image.new('RGBA', (glow_size, glow_size), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(self.glow_image_pil)
        center = glow_size // 2
        radius = 70
        glow_draw.ellipse((center-radius, center-radius, center+radius, center+radius), fill=(239, 68, 68, 100))
        self.glow_image_pil = self.glow_image_pil.filter(ImageFilter.GaussianBlur(radius=30))
        self.glow_image_tk = ImageTk.PhotoImage(self.glow_image_pil)


        # --- HEADER ---
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=40, pady=24, side="top")

        logo_frame = ctk.CTkFrame(header, fg_color="transparent")
        logo_frame.pack(side="left")

        box_icon = ctk.CTkImage(Image.open("box (1).png"), size=(28, 28))
        logo_icon_label = ctk.CTkLabel(logo_frame, text="", image=box_icon)
        logo_icon_label.pack(side="left", padx=(0,12))

        logo_text = ctk.CTkLabel(logo_frame, text="AI Renamer", font=("Permanent Marker", 24, "bold"), text_color="white")
        logo_text.pack(side="left")

        header_actions = ctk.CTkFrame(header, fg_color="transparent")
        header_actions.pack(side="right")

        sparkles_icon = ctk.CTkImage(Image.open("sparkles (1).png"), size=(16, 16))
        upgrade_btn = ctk.CTkButton(header_actions, text="Upgrade Plan", image=sparkles_icon,
                                     fg_color="#09090b", text_color="white",
                                     border_width=1, border_color="#27272a",
                                     font=("Permanent Marker", 14, "normal"),
                                     corner_radius=8,
                                     compound="left",
                                     height=36,
                                     )
        upgrade_btn.pack(side="left", padx=16)

        settings_icon = ctk.CTkImage(Image.open("settings (1).png"), size=(24,24))
        settings_btn = ctk.CTkButton(header_actions, text="", image=settings_icon, fg_color="transparent",
                                       width=40, height=40,
                                       font=("Permanent Marker", 24),
                                       command=lambda: controller.show_frame("SettingsPage"))
        settings_btn.pack(side="left")

        # --- MAIN STAGE ---
        main_stage = ctk.CTkFrame(self, fg_color="transparent")
        main_stage.pack(fill="both", expand=True)

        self.progress_container = ctk.CTkFrame(main_stage, fg_color="transparent", width=400, height=400)
        self.progress_container.place(relx=0.5, rely=0.45, anchor="center")

        self.canvas = ctk.CTkCanvas(self.progress_container, bg=THEME_BG_DARK, highlightthickness=0, width=400, height=400)
        self.canvas.pack()
        
        self.bind("<Configure>", self.on_resize)
        
        center_content = ctk.CTkFrame(self.progress_container, fg_color="transparent")
        center_content.place(relx=0.5, rely=0.5, anchor="center")

        self.power_btn = ctk.CTkButton(center_content, text="START",
                                       fg_color="#ef4444", hover_color="#d04040",
                                       font=("Permanent Marker", 24, "bold"),
                                       corner_radius=100,
                                       width=192, height=72,
                                       command=self.toggle)
        self.power_btn.pack(pady=16)

        self.counter_label = ctk.CTkLabel(center_content, text="0 / 50", font=("Permanent Marker", 18, "bold"), text_color="#a1a1aa")
        self.counter_label.pack()
        
        # --- NAV ACTIONS ---
        nav_actions = ctk.CTkFrame(self, fg_color="transparent")
        nav_actions.pack(fill="x", side="bottom", pady=(0, 64))
        
        nav_actions_inner = ctk.CTkFrame(nav_actions, fg_color="transparent")
        nav_actions_inner.pack()

        self.create_nav_card(nav_actions_inner, "Smart Folders", "Manage sources", "FoldersPage", "folder-search (1).png", 0)
        self.create_nav_card(nav_actions_inner, "Gallery", "View processed files", "GalleryPage", "image (1).png", 1)

    def create_nav_card(self, parent, title, subtitle, page, icon_path, col):
        card = ctk.CTkFrame(parent, fg_color="#09090b", border_width=1, border_color="#27272a",
                             corner_radius=12, cursor="hand2")
        card.grid(row=0, column=col, padx=12)
        
        command = lambda e, p=page: self.controller.show_frame(p)
        card.bind("<Button-1>", command)
        
        card.grid_rowconfigure(0, weight=1)

        icon_frame = ctk.CTkFrame(card, fg_color="#27272a", corner_radius=6, width=40, height=40)
        icon_frame.grid(row=0, column=0, padx=(20, 16), pady=20)
        icon_frame.grid_propagate(False) # This is important, to prevent the frame from shrinking to the image size
        icon_frame.bind("<Button-1>", command)
        
        pil_image = Image.open(icon_path)
        icon_image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=(22, 22))

        icon_label = ctk.CTkLabel(icon_frame, text="", image=icon_image)
        icon_label.place(relx=0.5, rely=0.5, anchor="center")
        icon_label.bind("<Button-1>", command)

        text_frame = ctk.CTkFrame(card, fg_color="transparent")
        text_frame.grid(row=0, column=1, padx=(0, 20), pady=20, sticky="ew")
        text_frame.bind("<Button-1>", command)

        title_label = ctk.CTkLabel(text_frame, text=title, font=("Permanent Marker", 16, "bold"), text_color="white")
        title_label.pack(anchor="w")
        title_label.bind("<Button-1>", command)

        subtitle_label = ctk.CTkLabel(text_frame, text=subtitle, font=("Permanent Marker", 12), text_color="#a1a1aa")
        subtitle_label.pack(anchor="w")
        subtitle_label.bind("<Button-1>", command)
    
    def on_resize(self, event=None):
        self.draw_canvas()
        
    def draw_canvas(self):
        self.canvas.delete("all")
        w, h = 400, 400
        cx, cy = w/2, h/2

        if self.glowing:
            self.canvas.create_image(cx, cy, image=self.glow_image_tk)

        r = 180
        
        # Ring Background
        self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r, outline="#27272a", width=12)
        
        # Progress Arc
        if self.limit_val > 0:
            angle = (self.progress_val / self.limit_val) * 360
            if angle > 360: angle = 360
            self.canvas.create_arc(cx-r, cy-r, cx+r, cy+r, start=90, extent=-angle, outline="#10b981", width=12, style="arc")
            
        # Spinner
        if self.is_animating:
            r_spin = r # Spinner on the same radius
            self.canvas.create_arc(cx-r, cy-r, cx+r, cy+r, start=self.angle_offset, extent=80, outline="#ffffff", width=4, style="arc")
            self.canvas.create_arc(cx-r, cy-r, cx+r, cy+r, start=self.angle_offset+180, extent=80, outline="#ffffff", width=4, style="arc")

    def animate(self):
        if self.is_animating:
            self.angle_offset = (self.angle_offset - 15) % 360
            self.draw_canvas()
            self.after(30, self.animate)

    def update_ui(self):
        count = self.controller.stats.get("total_count", 0)
        self.progress_val = count
        self.counter_label.configure(text=f"{count} / 50")
        self.draw_canvas()

    def toggle(self):
        if self.controller.monitoring:
            self.controller.toggle_monitoring()
            self.update_status(False)
        else:
            self.power_btn.configure(text="LOADING...", fg_color="#E0E0E0", text_color="black", state="disabled")
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
        self.glowing = not running
        text = "STOP" if running else "START"
        color = THEME_ACCENT_GREEN if running else "#ef4444"
        text_col = "white"
        self.power_btn.configure(text=text.upper(), fg_color=color, text_color=text_col)
        self.draw_canvas()

    def refresh(self): self.update_ui()

class SettingsPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color=THEME_BG_DARK)
        self.controller = controller
        
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=40, pady=30)

        ctk.CTkButton(header, text="← Back", fg_color="transparent", width=60, command=lambda: controller.show_frame("MainMenu")).pack(side="left", anchor="n")
        
        title_frame = ctk.CTkFrame(header, fg_color="transparent")
        title_frame.pack(side="left", fill="x", expand=True)
        
        ctk.CTkLabel(title_frame, text="Settings", font=("Permanent Marker", 32, "bold"), text_color="white").pack()

        ctk.CTkButton(header, text="Save Changes", fg_color="white", text_color="black", hover_color="#ddd", width=120, height=40, corner_radius=8, command=self.save).pack(side="right", anchor="n")
        
        # Content
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=40, pady=(0, 40))
        
        # API Config Card
        self.create_section("API Configuration", "Manage your secret API keys")
        
        api_frame = ctk.CTkFrame(self.scroll, fg_color=THEME_CARD_DARK, height=50, corner_radius=12)
        api_frame.pack(fill="x", pady=(10, 30))

        self.api_entry = ctk.CTkEntry(api_frame, placeholder_text="sk_live_...", fg_color="transparent", border_width=0, text_color="white", show="*")
        self.api_entry.pack(side="left", fill="x", expand=True, padx=20, pady=5)
        self.add_context_menu(self.api_entry)
        
        ctk.CTkButton(api_frame, text="👁", width=40, fg_color="transparent", text_color="white", font=("Arial", 20),
                      command=self.toggle_api_key_visibility).pack(side="right", padx=10)

        # Source Dir Card
        self.create_section("Source Directory", "Input folder where raw files are located")
        self.track_var = ctk.StringVar()
        f1 = ctk.CTkFrame(self.scroll, fg_color=THEME_CARD_DARK, height=60, corner_radius=12)
        f1.pack(fill="x", pady=(10, 30))
        ctk.CTkEntry(f1, textvariable=self.track_var, fg_color="transparent", border_width=0, height=60, text_color="white").pack(side="left", fill="x", expand=True, padx=20)
        ctk.CTkButton(f1, text="Browse", fg_color="transparent", border_width=1, border_color="#333", width=80, command=lambda: self.browse(self.track_var)).pack(side="right", padx=20, pady=10)

        # Dest Dir Card
        self.create_section("Destination Directory", "Output location for processed builds")
        self.dest_var = ctk.StringVar()
        f2 = ctk.CTkFrame(self.scroll, fg_color=THEME_CARD_DARK, height=60, corner_radius=12)
        f2.pack(fill="x", pady=(10, 30))
        ctk.CTkEntry(f2, textvariable=self.dest_var, fg_color="transparent", border_width=0, height=60, text_color="white").pack(side="left", fill="x", expand=True, padx=20)
        ctk.CTkButton(f2, text="Browse", fg_color="transparent", border_width=1, border_color="#333", width=80, command=lambda: self.browse(self.dest_var)).pack(side="right", padx=20, pady=10)

    def create_section(self, title, sub):
        ctk.CTkLabel(self.scroll, text=title, font=("Permanent Marker", 18, "bold"), text_color="white").pack(anchor="w")
        ctk.CTkLabel(self.scroll, text=sub, font=("Permanent Marker", 14), text_color=THEME_TEXT_GRAY).pack(anchor="w")

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

    def toggle_api_key_visibility(self):
        if self.api_entry.cget("show") == "*":
            self.api_entry.configure(show="")
        else:
            self.api_entry.configure(show="*")

import datetime

def get_folder_stats(folder_path):
    if not os.path.exists(folder_path):
        return 0, 0
    
    total_size = 0
    file_count = 0
    for dirpath, dirnames, filenames in os.walk(folder_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)
            file_count += 1
    return total_size, file_count

def format_size(size_bytes):
    if size_bytes == 0:
        return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 1)
    return f"{s} {size_name[i]}"

class FoldersPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color=THEME_BG_DARK)
        self.controller = controller
        
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=40, pady=30)
        
        ctk.CTkButton(header, text="← Back", fg_color="transparent", width=60, command=lambda: controller.show_frame("MainMenu")).pack(side="left", anchor="n")

        title_frame = ctk.CTkFrame(header, fg_color="transparent")
        title_frame.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(title_frame, text="All Files", font=("Permanent Marker", 32, "bold"), text_color="white").pack()

        ctk.CTkButton(header, text="+ New Folder", fg_color="white", text_color="black", hover_color="#ddd", width=120, height=40, corner_radius=8, command=self.add_rule).pack(side="right", anchor="n")

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=40)

    def refresh(self):
        for w in self.scroll.winfo_children(): w.destroy()
        
        changed = False
        for f in self.controller.smart_folders:
            if 'creation_date' not in f:
                f['creation_date'] = datetime.datetime.now().isoformat()
                changed = True
        
        if changed:
            save_json(CONFIG_FILE, self.controller.smart_folders)

        for i, f in enumerate(self.controller.smart_folders):
            self.create_card(f, i)

    def create_card(self, f, i):
        card = ctk.CTkFrame(self.scroll, fg_color=THEME_CARD_DARK, corner_radius=16, height=80)
        card.pack(fill="x", pady=8)
        
        card.grid_columnconfigure(1, weight=1)

        icon = ctk.CTkButton(card, text="📁", width=50, height=50, fg_color="#222", hover=False, corner_radius=12, font=("Permanent Marker", 20))
        icon.grid(row=0, column=0, rowspan=2, padx=20, pady=15)
        
        name_lbl = ctk.CTkLabel(card, text=f['name'], font=("Permanent Marker", 16, "bold"), text_color="white", cursor="hand2")
        name_lbl.grid(row=0, column=1, sticky="w", padx=10)
        name_lbl.bind("<Button-1>", lambda e, name=f['name']: self.open_folder(name))
        
        dest_base = self.controller.app_config.get("dest_folder") or self.controller.app_config.get("track_folder")
        folder_path = os.path.join(dest_base, f['name']) if dest_base else ""
        
        size, count = get_folder_stats(folder_path)
        
        count_text = f"{count} files" if count > 0 else "Empty"
        
        count_lbl = ctk.CTkLabel(card, text=count_text, font=("Permanent Marker", 12), text_color=THEME_TEXT_GRAY)
        count_lbl.grid(row=1, column=1, sticky="w", padx=10)

        date_str = datetime.datetime.fromisoformat(f['creation_date']).strftime('%b %d, %Y')
        date_lbl = ctk.CTkLabel(card, text=date_str, font=("Permanent Marker", 12), text_color=THEME_TEXT_GRAY)
        date_lbl.grid(row=0, column=2, rowspan=2, padx=20)
        
        size_lbl = ctk.CTkLabel(card, text=format_size(size), font=("Permanent Marker", 12), text_color=THEME_TEXT_GRAY)
        size_lbl.grid(row=0, column=3, rowspan=2, padx=20)
        
        ctk.CTkButton(card, text="⋮", width=30, fg_color="transparent", text_color="white", font=("Permanent Marker", 20), 
                      command=lambda x=i: self.delete(x)).grid(row=0, column=4, rowspan=2, padx=20)

    def open_folder(self, folder_name):
        dest_base = self.controller.app_config.get("dest_folder") or self.controller.app_config.get("track_folder")
        if dest_base:
            path = os.path.join(dest_base, folder_name)
            if os.path.exists(path): os.startfile(path)

    def add_rule(self):
        d = ctk.CTkToplevel(self); d.geometry("400x300"); d.title("New Folder")
        d.configure(fg_color=THEME_BG_DARK)
        ctk.CTkLabel(d, text="Folder Name", text_color="white").pack(pady=10)
        n = ctk.CTkEntry(d, fg_color=THEME_CARD_DARK, text_color="white"); n.pack()
        ctk.CTkLabel(d, text="Description", text_color="white").pack(pady=10)
        desc = ctk.CTkEntry(d, fg_color=THEME_CARD_DARK, text_color="white"); desc.pack()
        
        def s():
            if n.get():
                self.controller.smart_folders.append({
                    "name": n.get(), 
                    "description": desc.get(),
                    "creation_date": datetime.datetime.now().isoformat()
                })
                save_json(CONFIG_FILE, self.controller.smart_folders)
                self.refresh(); d.destroy()
        ctk.CTkButton(d, text="Create", fg_color="white", text_color="black", command=s).pack(pady=20)

    def delete(self, idx):
        self.controller.smart_folders.pop(idx)
        save_json(CONFIG_FILE, self.controller.smart_folders)
        self.refresh()

class GalleryPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color=THEME_BG_DARK) # Dark Mode
        self.controller = controller
        
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=20)
        ctk.CTkButton(header, text="←", width=40, fg_color="transparent", text_color="white", font=("Permanent Marker", 20),
                      command=lambda: controller.show_frame("MainMenu")).pack(side="left")
        ctk.CTkLabel(header, text="Gallery", font=("Permanent Marker", 24, "bold"), text_color="white").pack(side="left", padx=10)
        
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=20)
        
        # Masonry Cols
        self.cols = [ctk.CTkFrame(self.scroll, fg_color="transparent") for _ in range(3)]
        for c in self.cols: c.pack(side="left", fill="both", expand=True, padx=5)

    def refresh(self):
        for c in self.cols:
            for w in c.winfo_children(): w.destroy()
            
        history = list(reversed(self.controller.history[-50:]))
        
        for i, item in enumerate(history):
            path = item.get("path")
            if path and os.path.exists(path):
                col_idx = i % 3
                self.add_image(path, self.cols[col_idx], i)

    def add_image(self, path, parent, index):
        try:
            pil_img = Image.open(path)
            # Aspect Ratio
            w_base = 250
            w_percent = (w_base / float(pil_img.size[0]))
            h_size = int((float(pil_img.size[1]) * float(w_percent)))
            
            img = ctk.CTkImage(pil_img, size=(w_base, h_size))
            
            # Container for hover effect
            card = ctk.CTkFrame(parent, fg_color="transparent")
            card.pack(pady=10, fill="x")
            
            # Animation delay (staggered)
            # This requires tricky updating. Simplest is just load.
            
            btn = ctk.CTkButton(card, text="", image=img, fg_color="transparent", hover=True,
                                corner_radius=12, command=lambda p=path: os.startfile(p))
            btn.pack()
            
            # Label
            name = os.path.basename(path)
            if len(name) > 20: name = name[:20] + "..."
            ctk.CTkLabel(card, text=name, text_color="white", font=("Permanent Marker", 11)).pack(pady=5)
            
        except: pass

if __name__ == "__main__":
    app = App()
    app.mainloop()
