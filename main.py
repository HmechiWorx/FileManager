import os, shutil, sqlite3, threading, time, difflib
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

DB_FILE = Path("file_manager.db")
VERSION_DIR = Path("versions")
LOCK_PASSWORD = "123"

class FileManagerApp:
    def save_root_folders(self):
        """Save the list of root folders to a file for persistence."""
        try:
            with open("root_folders.txt", "w", encoding="utf-8") as f:
                for folder in self.root_folders:
                    f.write(str(folder) + "\n")
        except Exception:
            pass

    def load_root_folders(self):
        """Load the list of root folders from a file if it exists."""
        try:
            if os.path.exists("root_folders.txt"):
                with open("root_folders.txt", "r", encoding="utf-8") as f:
                    self.root_folders = [Path(line.strip()) for line in f if line.strip()]
        except Exception:
            self.root_folders = []
    def open_cnc_editor_folder(self):
        os.startfile(r"D:\Program Files (x86)\CNC Syntax Editor\cncsyn.exe")

    def __init__(self, root):
        self.root = root
        self.root.title("MechiWork Private Limited - Advanced File Management System")
        self.root.geometry("1400x800")
        # Maximize the window on start
        self.root.state('zoomed')
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # --- LICENSE KEY CHECK ---
        self.license_file = Path("license.key")
        self.license_key = None
        if self.license_file.exists():
            with open(self.license_file, "r") as f:
                self.license_key = f.read().strip()
        if not self.license_key or not self.validate_license_key(self.license_key):
            self.prompt_for_license_key()

        # --- Folder persistence ---
        self.root_folders = []
        self.load_root_folders()
        self.save_root_folders()
        self.selected_file = None
        self.selected_file_mtime = None
        self.image_preview = None
        self.current_role = tk.StringVar(value="operator")
        self.search_var = tk.StringVar()
        self.part_search_var = tk.StringVar()
        self.draw_search_var = tk.StringVar()
        self.desc_search_var = tk.StringVar()
        self.cust_search_var = tk.StringVar()

        VERSION_DIR.mkdir(parents=True, exist_ok=True)
        self.db_conn = sqlite3.connect(DB_FILE)
        self.db_cursor = self.db_conn.cursor()
        self.setup_db()
        self.build_ui()
        self.update_folder_label()
        self.populate_tree()
        self.load_root_folders()
        self.start_file_monitor()

    def get_machine_id(self):
        """
        Returns a unique machine identifier (e.g., MAC address hash).
        """
        import uuid, hashlib
        mac = uuid.getnode()
        machine_id = hashlib.sha256(str(mac).encode()).hexdigest().upper()[:16]
        return machine_id


    def prompt_for_license_key(self):
        machine_id = self.get_machine_id()
        while True:
            # Custom dialog
            dialog = tk.Toplevel(self.root)
            dialog.title("License Key Required")
            dialog.geometry("420x220")
            dialog.grab_set()
            dialog.resizable(False, False)

            tk.Label(dialog, text="Your Machine ID:", font=("Helvetica", 11, "bold")).pack(pady=(18, 2))
            machine_id_entry = tk.Entry(dialog, width=32, font=("Consolas", 12), justify="center")
            machine_id_entry.insert(0, machine_id)
            machine_id_entry.config(state="readonly")
            machine_id_entry.pack(pady=(0, 5))

            def copy_machine_id():
                dialog.clipboard_clear()
                dialog.clipboard_append(machine_id)
                messagebox.showinfo("Copied!", "Machine ID copied to clipboard.", parent=dialog)

            copy_btn = tk.Button(dialog, text="Copy Machine ID", command=copy_machine_id)
            copy_btn.pack(pady=(0, 10))

            tk.Label(dialog, text="Send this Machine ID to the developer to get your license key.\nEnter your license key below:", wraplength=380, justify="center").pack(pady=(0, 8))
            license_var = tk.StringVar()
            license_entry = tk.Entry(dialog, textvariable=license_var, width=36, font=("Consolas", 12), show="*")
            license_entry.pack(pady=(0, 8))
            license_entry.focus_set()

            result = {'key': None}

            def submit():
                result['key'] = license_var.get().strip()
                dialog.destroy()

            def cancel():
                result['key'] = None
                dialog.destroy()

            btn_frame = tk.Frame(dialog)
            btn_frame.pack(pady=(0, 10))
            tk.Button(btn_frame, text="Submit", command=submit, width=10).pack(side=tk.LEFT, padx=5)
            tk.Button(btn_frame, text="Cancel", command=cancel, width=10).pack(side=tk.LEFT, padx=5)

            dialog.protocol("WM_DELETE_WINDOW", cancel)
            self.root.wait_window(dialog)

            key = result['key']
            if key is None or key == "":
                messagebox.showerror("License Required", "A license key is required to use this application.")
                self.root.destroy()
                exit()
            if self.validate_license_key(key, machine_id):
                with open(self.license_file, "w") as f:
                    f.write(key)
                self.license_key = key
                messagebox.showinfo("License Accepted", "Thank you! License key accepted.")
                break
            else:
                messagebox.showerror("Invalid License", "The license key entered is invalid. Please contact the developer.")

    def validate_license_key(self, key, machine_id=None):
        import hashlib
        if machine_id is None:
            machine_id = self.get_machine_id()
        secret = "MECHIWORK-2026-SECRET"
        data = f"{machine_id}:{secret}"
        expected = hashlib.sha256(data.encode()).hexdigest().upper()
        expected_key = "-".join([expected[i:i+8] for i in range(0, 32, 8)])
        return key == expected_key

        # (moved to __init__)

    def setup_db(self):
        # Add comment column if not exists
        self.db_cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS file_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT,
                timestamp TEXT,
                operator TEXT,
                version_path TEXT,
                comment TEXT DEFAULT ''
            )
        """
        )
        # Try to add comment column if missing (for upgrades)
        try:
            self.db_cursor.execute("ALTER TABLE file_versions ADD COLUMN comment TEXT DEFAULT ''")
        except Exception:
            pass
        self.db_cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS file_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT,
                timestamp TEXT,
                user_role TEXT,
                action TEXT,
                detail TEXT
            )
        """
        )
        self.db_conn.commit()

    def build_ui(self):
        # Color palette
        COLOR_PRIMARY = "#F5A623"  # orange
        COLOR_BG = "#F5F7FA"       # very light gray
        COLOR_DARK = "#181D29"    # almost black
        COLOR_BLUE = "#4662FA"    # vivid blue
        COLOR_WHITE = "#FFFFFF"
        COLOR_TEXT = "#181D29"
        COLOR_TEXT_SECONDARY = "#7B7B7B"
        COLOR_ACCENT = "#FF3B30"  # red

        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TButton', font=('Helvetica', 10, 'bold'), padding=6, relief='raised',
                        background=COLOR_DARK, foreground=COLOR_WHITE)
        style.map('TButton', background=[('active', COLOR_BLUE), ('!active', COLOR_DARK)])
        style.configure('Accent.TButton', background=COLOR_BLUE, foreground=COLOR_WHITE)
        style.map('Accent.TButton', background=[('active', COLOR_PRIMARY), ('!active', COLOR_BLUE)])
        style.configure('TLabel', font=('Helvetica', 10), background=COLOR_BG, foreground=COLOR_TEXT)
        style.configure('Treeview', font=('Helvetica', 9), rowheight=25, background=COLOR_WHITE, fieldbackground=COLOR_WHITE, foreground=COLOR_TEXT)
        style.configure('Treeview.Heading', font=('Helvetica', 10, 'bold'), background=COLOR_PRIMARY, foreground=COLOR_DARK)
        style.configure('TFrame', background=COLOR_BG)
        style.configure('TRadiobutton', font=('Helvetica', 10), background=COLOR_BG, foreground=COLOR_TEXT)

        self.root.configure(bg=COLOR_BG)

        # Header bar with HAL logo
        header = tk.Frame(self.root, bg=COLOR_PRIMARY, height=70)
        header.pack(fill=tk.X, side=tk.TOP)
        try:
            logo_img = Image.open("logo.jpg")
            logo_img = logo_img.resize((90, 40), Image.LANCZOS)
            self.header_logo = ImageTk.PhotoImage(logo_img)
            logo_label = tk.Label(header, image=self.header_logo, bg=COLOR_PRIMARY)
            logo_label.pack(side=tk.LEFT, padx=(20, 10), pady=5)
        except Exception:
            logo_label = tk.Label(header, text="", bg=COLOR_PRIMARY)
            logo_label.pack(side=tk.LEFT, padx=(20, 10), pady=5)
        header_label = tk.Label(header, text="Advanced File Management System", bg=COLOR_PRIMARY, fg=COLOR_DARK, font=("Helvetica", 18, "bold"), pady=18)
        header_label.pack(side=tk.LEFT, padx=10)

        main_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True)

        left_frame = ttk.Frame(main_pane, padding=10, style='TFrame')
        right_frame = ttk.Frame(main_pane, padding=10, style='TFrame')
        main_pane.add(left_frame, weight=1)
        main_pane.add(right_frame, weight=2)

        folder_select_frame = ttk.Frame(left_frame, style='TFrame')
        folder_select_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(folder_select_frame, text="Opened folders:", style='TLabel').pack(side=tk.LEFT)
        self.root_path_label = ttk.Label(folder_select_frame, text="<none>", style='TLabel')
        self.root_path_label.pack(side=tk.LEFT, padx=(5, 10))
        ttk.Button(folder_select_frame, text="Add Folder", command=self.add_folder, style='TButton').pack(side=tk.LEFT)
        ttk.Button(folder_select_frame, text="Clear Folders", command=self.clear_folders, style='TButton').pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(folder_select_frame, text="Remove Selected Folder", command=self.remove_selected_root_folder, style='TButton').pack(side=tk.LEFT, padx=(5, 0))
        self.cnc_editor_button = ttk.Button(folder_select_frame, text="Open CNC Editor", command=self.open_cnc_editor_folder, style='Accent.TButton')
        self.cnc_editor_button.pack(side=tk.LEFT, padx=(15, 0))

        ttk.Separator(left_frame, orient='horizontal').pack(fill='x', pady=(10, 5))

        tree_frame = ttk.Frame(left_frame, style='TFrame')
        tree_frame.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(tree_frame, columns=("Status", "Comments"), show="tree headings", style='Treeview')
        self.tree.heading("#0", text="File")
        self.tree.heading("Status", text="Status")
        self.tree.heading("Comments", text="Comments")
        self.tree.column("#0", width=250)
        self.tree.column("Status", width=80)
        self.tree.column("Comments", width=400, stretch=True)
        tree_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        tree_scroll_x = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=tree_scroll.set, xscrollcommand=tree_scroll_x.set)
        self.tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        tree_scroll.pack(fill=tk.Y, side=tk.LEFT)
        tree_scroll_x.pack(fill=tk.X, side=tk.BOTTOM)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        ttk.Separator(left_frame, orient='horizontal').pack(fill='x', pady=(5, 10))

        search_frame = ttk.Frame(left_frame, padding=(0, 10, 0, 0), style='TFrame')
        search_frame.pack(fill=tk.X)
        ttk.Label(search_frame, text="Search file/folder:", style='TLabel').pack(side=tk.LEFT)
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        ttk.Button(search_frame, text="Search", command=self.search_tree, style='Accent.TButton').pack(side=tk.LEFT)
        ttk.Button(search_frame, text="Clear Search", command=self.clear_search, style='TButton').pack(side=tk.LEFT, padx=(5, 0))

        ttk.Separator(left_frame, orient='horizontal').pack(fill='x', pady=(10, 5))

        field_search_frame = ttk.Frame(left_frame, padding=(0, 10, 0, 0), style='TFrame')
        field_search_frame.pack(fill=tk.X)
        ttk.Label(field_search_frame, text="Search fields:", style='TLabel').grid(row=0, column=0, columnspan=4, sticky=tk.W)
        ttk.Label(field_search_frame, text="part:", style='TLabel').grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
        ttk.Entry(field_search_frame, textvariable=self.part_search_var, width=15).grid(row=1, column=1, sticky=tk.W, padx=(5, 10), pady=(5, 0))
        ttk.Label(field_search_frame, text="draw:", style='TLabel').grid(row=1, column=2, sticky=tk.W, pady=(5, 0))
        ttk.Entry(field_search_frame, textvariable=self.draw_search_var, width=15).grid(row=1, column=3, sticky=tk.W, padx=(5, 0), pady=(5, 0))
        ttk.Label(field_search_frame, text="desc:", style='TLabel').grid(row=2, column=0, sticky=tk.W, pady=(5, 0))
        ttk.Entry(field_search_frame, textvariable=self.desc_search_var, width=15).grid(row=2, column=1, sticky=tk.W, padx=(5, 10), pady=(5, 0))
        ttk.Label(field_search_frame, text="cust:", style='TLabel').grid(row=2, column=2, sticky=tk.W, pady=(5, 0))
        ttk.Entry(field_search_frame, textvariable=self.cust_search_var, width=15).grid(row=2, column=3, sticky=tk.W, padx=(5, 0), pady=(5, 0))
        ttk.Button(field_search_frame, text="Search", command=self.search_nc_fields, style='Accent.TButton').grid(row=3, column=0, columnspan=4, sticky=tk.W, pady=(8, 0))

        ttk.Separator(left_frame, orient='horizontal').pack(fill='x', pady=(10, 5))

        action_frame = ttk.Frame(left_frame, padding=(0, 10, 0, 0), style='TFrame')
        action_frame.pack(fill=tk.X)
        ttk.Label(action_frame, text="Current role:", style='TLabel').grid(row=0, column=0, sticky=tk.W)
        ttk.Radiobutton(action_frame, text="Operator", variable=self.current_role, value="operator", command=self.on_role_change, style='TRadiobutton').grid(row=0, column=1, sticky=tk.W)
        ttk.Radiobutton(action_frame, text="Supervisor", variable=self.current_role, value="supervisor", command=self.on_role_change, style='TRadiobutton').grid(row=0, column=2, sticky=tk.W)

        self.lock_status_label = ttk.Label(action_frame, text="File locked: ", style='TLabel')
        self.lock_status_label.grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=(4, 8))

        buttons_frame = ttk.Frame(action_frame, style='TFrame')
        buttons_frame.grid(row=2, column=0, columnspan=3, sticky=tk.W)
        self.lock_button = ttk.Button(buttons_frame, text="Lock File", command=self.lock_file, style='TButton')
        self.lock_button.grid(row=0, column=0, padx=(0, 5))
        self.unlock_button = ttk.Button(buttons_frame, text="Unlock File", command=self.unlock_file, style='TButton')
        self.unlock_button.grid(row=0, column=1, padx=(0, 5))
        self.send_button = ttk.Button(buttons_frame, text="Send to Target Folder", command=self.send_file_to_target, style='Accent.TButton')
        self.send_button.grid(row=0, column=2, padx=(0, 5))
        self.update_button_visibility()

        ttk.Separator(left_frame, orient='horizontal').pack(fill='x', pady=(10, 5))

        status_frame = ttk.Frame(right_frame, padding=(0, 0, 0, 5), style='TFrame')
        status_frame.pack(fill=tk.X)
        self.file_info_label = ttk.Label(status_frame, text="No file selected", anchor=tk.W, justify=tk.LEFT, style='TLabel')
        self.file_info_label.pack(fill=tk.X)

        right_tabs = ttk.Notebook(right_frame)
        right_tabs.pack(fill=tk.BOTH, expand=True)

        preview_tab = ttk.Frame(right_tabs, style='TFrame')
        edit_tab = ttk.Frame(right_tabs, style='TFrame')
        compare_tab = ttk.Frame(right_tabs, style='TFrame')
        log_tab = ttk.Frame(right_tabs, style='TFrame')
        right_tabs.add(preview_tab, text="Preview")
        right_tabs.add(edit_tab, text="Edit")
        right_tabs.add(compare_tab, text="Compare")
        right_tabs.add(log_tab, text="Logs")

        # Preview
        self.preview_text = tk.Text(preview_tab, wrap="none", state=tk.DISABLED, bg=COLOR_WHITE, fg=COLOR_TEXT)
        preview_scroll_y = ttk.Scrollbar(preview_tab, orient=tk.VERTICAL, command=self.preview_text.yview)
        preview_scroll_x = ttk.Scrollbar(preview_tab, orient=tk.HORIZONTAL, command=self.preview_text.xview)
        self.preview_text.configure(yscrollcommand=preview_scroll_y.set, xscrollcommand=preview_scroll_x.set)
        self.preview_text.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        preview_scroll_y.pack(fill=tk.Y, side=tk.LEFT)
        preview_scroll_x.pack(fill=tk.X, side=tk.BOTTOM)

        # Edit
        button_frame = ttk.Frame(edit_tab, style='TFrame')
        button_frame.pack(fill=tk.X, padx=10, pady=5, side=tk.TOP)
        self.save_button = ttk.Button(button_frame, text="Save Changes", command=self.save_edits, style='Accent.TButton')
        self.save_button.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.edit_text = tk.Text(edit_tab, wrap="none", state=tk.NORMAL, bg=COLOR_WHITE, fg=COLOR_TEXT)
        edit_scroll_y = ttk.Scrollbar(edit_tab, orient=tk.VERTICAL, command=self.edit_text.yview)
        edit_scroll_x = ttk.Scrollbar(edit_tab, orient=tk.HORIZONTAL, command=self.edit_text.xview)
        self.edit_text.configure(yscrollcommand=edit_scroll_y.set, xscrollcommand=edit_scroll_x.set)
        self.edit_text.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        edit_scroll_y.pack(fill=tk.Y, side=tk.LEFT)
        edit_scroll_x.pack(fill=tk.X, side=tk.BOTTOM)

        # Compare Tab
        self.compare_text = tk.Text(compare_tab, wrap="none", state=tk.DISABLED, bg=COLOR_WHITE, fg=COLOR_TEXT)
        compare_scroll_y = ttk.Scrollbar(compare_tab, orient=tk.VERTICAL, command=self.compare_text.yview)
        compare_scroll_x = ttk.Scrollbar(compare_tab, orient=tk.HORIZONTAL, command=self.compare_text.xview)
        self.compare_text.configure(yscrollcommand=compare_scroll_y.set, xscrollcommand=compare_scroll_x.set)
        self.compare_text.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        compare_scroll_y.pack(fill=tk.Y, side=tk.LEFT)
        compare_scroll_x.pack(fill=tk.X, side=tk.BOTTOM)

        # Logs
        self.log_text = tk.Text(log_tab, wrap="none", state=tk.DISABLED, bg=COLOR_WHITE, fg=COLOR_TEXT)
        log_scroll = ttk.Scrollbar(log_tab, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        log_scroll.pack(fill=tk.Y, side=tk.LEFT)
        self.refresh_logs()

    def add_folder(self):
        folder = filedialog.askdirectory(title="Select a folder to add")
        if not folder:
            return
        folder_path = Path(folder)
        if folder_path in self.root_folders:
            messagebox.showinfo("Folder already added", "This folder is already opened.")
            return
        self.root_folders.append(folder_path)
        self.save_root_folders()
        self.update_folder_label()
        self.populate_tree()

    def clear_folders(self):
        self.root_folders.clear()
        self.save_root_folders()
        self.root_path_label.config(text="<none>")
        self.tree.delete(*self.tree.get_children())
        self.selected_file = None
        self.selected_file_mtime = None
        self.clear_preview_area()
        self.clear_edit_area()
        self.clear_compare_area()
        self.clear_file_info()

    def remove_selected_root_folder(self):
        """Remove only the selected root folder from the opened folders list."""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Remove Folder", "Select a folder root in the tree first.")
            return
        item = selected[0]
        values = self.tree.item(item, "values")
        if len(values) < 2:
            messagebox.showwarning("Remove Folder", "Select a root folder in the tree.")
            return
        folder_path = Path(values[1])
        if folder_path in self.root_folders:
            self.root_folders = [f for f in self.root_folders if f != folder_path]
            self.save_root_folders()
            self.update_folder_label()
            self.populate_tree()
        else:
            messagebox.showwarning("Remove Folder", "Selected item is not a root folder.")

    def _find_root_folder(self, path: Path):
        for folder in self.root_folders:
            try:
                if path == folder or folder in path.parents:
                    return folder
            except Exception:
                continue
        return None

    def populate_tree(self):
        self.tree.delete(*self.tree.get_children())
        for folder in self.root_folders:
            if not folder.exists():
                continue
            node = self.tree.insert("", "end", text=folder.name, open=True, values=("", str(folder)))
            self._populate_tree(node, folder)

    def update_folder_label(self):
        if not self.root_folders:
            self.root_path_label.config(text="<none>")
            return
        names = [folder.name for folder in self.root_folders]
        if len(names) > 2:
            self.root_path_label.config(text=f"{len(names)} folders opened")
        else:
            self.root_path_label.config(text=", ".join(names))

    def search_tree(self):
        query = self.search_var.get().strip().lower()
        if not query:
            messagebox.showinfo("Search", "Please enter text to search.")
            return

        self.tree.delete(*self.tree.get_children())
        total_matches = 0
        for folder in self.root_folders:
            if not folder.exists():
                continue
            root_node = self.tree.insert("", "end", text=folder.name, open=True, values=("", str(folder)))
            if self._populate_tree_filtered(root_node, folder, query):
                total_matches += 1
            else:
                self.tree.delete(root_node)

        if total_matches == 0:
            messagebox.showinfo("Search", "No matching files or folders found.")
            self.populate_tree()
            return

        first_item = self.tree.get_children()[0] if self.tree.get_children() else None
        if first_item:
            self.tree.selection_set(first_item)
            self.tree.see(first_item)
            self.on_tree_select()
        messagebox.showinfo("Search", f"Filtered tree to matching items.")

    def _populate_tree_filtered(self, parent, path: Path, query: str) -> bool:
        matched = query in path.name.lower()
        for child in sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
            if child.is_dir():
                child_node = self.tree.insert(parent, "end", text=child.name, open=False, values=("", str(child), ""))
                child_matched = self._populate_tree_filtered(child_node, child, query)
                if not child_matched:
                    self.tree.delete(child_node)
                else:
                    matched = True
            elif query in child.name.lower():
                status = "Locked" if self.is_file_locked_for_path(child) else "Unlocked"
                self.tree.insert(parent, "end", text=child.name, values=(status, str(child), ""))
                matched = True
        return matched

    def clear_search(self):
        self.search_var.set("")
        self.populate_tree()
        self.tree.selection_remove(self.tree.selection())

    def search_nc_fields(self):
        if not self.root_folders:
            messagebox.showwarning("Search", "No folders are opened. Add a folder first.")
            return

        search_values = {
            "N0010": self.part_search_var.get().strip().lower(),
            "N0020": self.draw_search_var.get().strip().lower(),
            "N0030": self.desc_search_var.get().strip().lower(),
            "N0040": self.cust_search_var.get().strip().lower(),
        }
        active_searches = {tag: value for tag, value in search_values.items() if value}
        if not active_searches:
            messagebox.showinfo("Search", "Enter at least one value for part, draw, desc, or cust.")
            return

        results = []
        for folder in self.root_folders:
            for path in folder.rglob("*.nc"):
                try:
                    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
                except Exception:
                    continue
                matches = {}
                for tag, search_value in active_searches.items():
                    matches[tag] = None
                for line in lines:
                    lower_line = line.lower()
                    for tag, search_value in active_searches.items():
                        if matches[tag] is None and tag.lower() in lower_line and search_value in lower_line:
                            matches[tag] = line.strip()
                if all(value is not None for value in matches.values()):
                    results.append((path, matches))
        if not results:
            messagebox.showinfo("Search", "No matching entries found.")
            return
        self.show_nc_search_results(results)

    def show_nc_search_results(self, results):
        window = tk.Toplevel(self.root)
        window.title(".nc Field Search Results")
        window.geometry("900x500")

        info = ttk.Label(window, text=f"Found {len(results)} matching .nc files. Double-click a line to open the file.")
        info.pack(fill=tk.X, padx=10, pady=(10, 0))

        result_frame = ttk.Frame(window)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        result_list = tk.Listbox(result_frame, activestyle="none")
        result_list.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        scroll = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=result_list.yview)
        scroll.pack(fill=tk.Y, side=tk.LEFT)
        result_list.configure(yscrollcommand=scroll.set)

        for path, match_data in results:
            if isinstance(match_data, dict):
                entry_text = f"{path} | " + ", ".join([f"{tag}:{line}" for tag, line in match_data.items()])
            else:
                entry_text = f"{path} | {match_data}"
            result_list.insert(tk.END, entry_text)

        def open_selected(event=None):
            selection = result_list.curselection()
            if not selection:
                return
            index = selection[0]
            path, _ = results[index]
            self.select_file_in_tree(path)
            window.destroy()

        result_list.bind("<Double-Button-1>", open_selected)

    def select_file_in_tree(self, path: Path):
        target = None
        for item in self.tree.get_children():
            target = self._find_tree_item(item, path)
            if target:
                break
        if target:
            self.tree.selection_set(target)
            self.tree.see(target)
            self.on_tree_select()

    def _find_tree_item(self, item, path: Path):
        item_path = Path(self.tree.item(item, "values")[1])
        if item_path == path:
            return item
        for child in self.tree.get_children(item):
            found = self._find_tree_item(child, path)
            if found:
                return found
        return None

    def clear_preview_area(self):
        self.preview_text.config(state=tk.NORMAL)
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.config(state=tk.DISABLED)

    def update_file_info(self, file_path: Path):
        if not file_path.exists():
            self.file_info_label.config(text="File information unavailable.")
            return
        size = file_path.stat().st_size
        modified = datetime.fromtimestamp(file_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        detail = [f"Path: {file_path}", f"Size: {size} bytes", f"Modified: {modified}", f"Type: {file_path.suffix or 'unknown'}"]
        self.file_info_label.config(text=" | ".join(detail))

    def on_role_change(self):
        if self.current_role.get() == "supervisor":
            password = simpledialog.askstring("Supervisor Access", "Enter supervisor password:", show="*")
            if password != LOCK_PASSWORD:
                messagebox.showerror("Access Denied", "Incorrect password. Switching back to Operator.")
                self.current_role.set("operator")
                return
            messagebox.showinfo("Access Granted", "Switched to Supervisor role.")
        # No password needed for operator
        self.update_button_visibility()

    def update_button_visibility(self):
        if self.current_role.get() == "supervisor":
            self.lock_button.grid()
            self.unlock_button.grid()
            self.lock_status_label.grid()
            self.send_button.grid()
            self.cnc_editor_button.pack(side=tk.LEFT, padx=(15, 0))
        else:
            self.lock_button.grid_remove()
            self.unlock_button.grid_remove()
            self.lock_status_label.grid_remove()
            self.send_button.grid_remove()
            self.cnc_editor_button.pack_forget()

    def is_file_locked_for_path(self, path):
        self.db_cursor.execute("SELECT action FROM file_logs WHERE file_path = ? ORDER BY id DESC LIMIT 1", (str(path),))
        row = self.db_cursor.fetchone()
        return row and row[0] == "lock"

    def _populate_tree(self, parent, path: Path):
        try:
            for child in sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
                if child.is_dir():
                    node = self.tree.insert(parent, "end", text=child.name, open=False, values=("", str(child), ""))
                    self._populate_tree(node, child)
                else:
                    status = "Locked" if self.is_file_locked_for_path(child) else "Unlocked"
                    comment = ""
                    if child.suffix.lower() == ".nc":
                        self.db_cursor.execute(
                            "SELECT comment FROM file_versions WHERE file_path = ? ORDER BY id DESC LIMIT 1",
                            (str(child),)
                        )
                        row = self.db_cursor.fetchone()
                        if row and row[0]:
                            comment = row[0]
                    self.tree.insert(parent, "end", text=child.name, values=(status, str(child), comment))
        except PermissionError:
            pass

    def on_tree_select(self, event=None):
        selected = self.tree.selection()
        if not selected:
            return
        item = selected[0]
        file_path = Path(self.tree.item(item, "values")[1])
        if file_path.is_file():
            self.selected_file = file_path
            self.selected_file_mtime = file_path.stat().st_mtime
            self.display_file_preview(file_path)
            self.update_lock_status()
            self.display_file_in_edit_tab(file_path)
            self.show_compare(auto=True)
            self.update_file_info(file_path)
        else:
            self.selected_file = None
            self.clear_preview_area()
            self.clear_edit_area()
            self.clear_compare_area()
            self.update_file_info(file_path)

    def display_file_in_edit_tab(self, file_path: Path):
        self.edit_text.config(state=tk.NORMAL)
        self.edit_text.delete("1.0", tk.END)
        ext = file_path.suffix.lower()
        if ext in {".txt", ".nc"}:
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(20000)
                self.edit_text.insert(tk.END, content)
            except Exception as e:
                self.edit_text.insert(tk.END, f"Unable to read file: {e}")
        else:
            self.edit_text.insert(tk.END, f"No editing available for {file_path.suffix} files.\nFile path: {file_path}")
        self.edit_text.config(state=tk.NORMAL)

    def display_file_preview(self, file_path: Path):
        self.preview_text.config(state=tk.NORMAL)
        self.preview_text.delete("1.0", tk.END)
        ext = file_path.suffix.lower()
        # Allow preview for .txt, .nc, .h, .mpf, .ncp files as text
        if ext in {".txt", ".nc", ".h", ".mpf", ".ncp"}:
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(20000)
                self.preview_text.insert(tk.END, content)
                if len(content) == 20000:
                    self.preview_text.insert(tk.END, "\n\n[Preview truncated]")
            except Exception as e:
                self.preview_text.insert(tk.END, f"Unable to read file: {e}")
        elif ext in {".jpg", ".jpeg", ".png", ".gif"}:
            try:
                image = Image.open(file_path)
                image.thumbnail((600, 500))
                self.image_preview = ImageTk.PhotoImage(image)
                self.preview_text.image_create(tk.END, image=self.image_preview)
            except ImportError:
                self.preview_text.insert(tk.END, "Image preview requires Pillow. Install with: pip install pillow")
            except Exception as e:
                self.preview_text.insert(tk.END, f"Image preview failed: {e}")
        else:
            self.preview_text.insert(tk.END, f"No preview available for {file_path.suffix} files.\nFile path: {file_path}")
        self.preview_text.config(state=tk.DISABLED)

    def on_edit_clicked(self):
        if not self.selected_file:
            messagebox.showwarning("Select file", "Please select a .nc file in the tree first.")
            return
        if self.selected_file.suffix.lower() != ".nc":
            messagebox.showwarning("Wrong file type", "Only .nc files can be edited and versioned.")
            return
        if self.is_file_locked():
            messagebox.showwarning("Locked", "This file is currently locked and cannot be edited.")
            return
        try:
            with open(self.selected_file, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            messagebox.showerror("Read error", f"Unable to open file: {e}")
            return
        self.edit_text.config(state=tk.NORMAL)
        self.edit_text.delete("1.0", tk.END)
        self.edit_text.insert(tk.END, content)
        self.edit_text.config(state=tk.NORMAL)
        self.save_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10,0))
        # Removed reference to self.edit_button

    def save_edits(self):
        if not self.selected_file:
            messagebox.showwarning("Select file", "Select a file before saving.")
            return
        if self.selected_file.suffix.lower() != ".nc":
            messagebox.showwarning("Wrong file type", "Only .nc files can be saved from the edit panel.")
            return
        if self.is_file_locked():
            messagebox.showwarning("Locked", "Cannot save edits while the file is locked.")
            return
        content = self.edit_text.get("1.0", tk.END)
        try:
            with open(self.selected_file, "r", encoding="utf-8", errors="replace") as f:
                original = f.read()
        except Exception as e:
            messagebox.showerror("Read error", f"Unable to read current file: {e}")
            return
        if content == original:
            messagebox.showinfo("No changes", "No changes detected to save.")
            return
        # Prompt for comment
        comment = simpledialog.askstring("Save Comment", "Enter a comment for this change:", parent=self.root)
        if comment is None:
            messagebox.showinfo("Cancelled", "Save cancelled.")
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Store version in the same folder as the original file
        version_filename = self.selected_file.parent / f"{self.selected_file.stem}_{timestamp}{self.selected_file.suffix}"
        shutil.copy2(self.selected_file, version_filename)
        try:
            with open(self.selected_file, "w", encoding="utf-8", errors="replace") as f:
                f.write(content)
        except Exception as e:
            messagebox.showerror("Save error", f"Unable to save file: {e}")
            return
        self.log_action(self.selected_file, "save", f"Saved edit as {version_filename.name}")
        self.db_cursor.execute(
            "INSERT INTO file_versions (file_path, timestamp, operator, version_path, comment) VALUES (?, ?, ?, ?, ?)",
            (str(self.selected_file), datetime.now().isoformat(), self.current_role.get(), str(version_filename), comment),
        )
        self.db_conn.commit()
        self.selected_file_mtime = self.selected_file.stat().st_mtime
        messagebox.showinfo("Saved", "Changes saved and version stored.")
        self.refresh_logs()
        self.show_compare(auto=True)
        self.populate_tree()

    def lock_file(self):
        if not self.selected_file:
            messagebox.showwarning("Select file", "Select a file first.")
            return
        if self.current_role.get() != "supervisor":
            messagebox.showwarning("Supervisor only", "Only supervisors may lock files.")
            return
        password = simpledialog.askstring("Supervisor Password", "Enter supervisor password:", show="*")
        if password != LOCK_PASSWORD:
            messagebox.showerror("Invalid password", "Supervisor password is incorrect.")
            return
        # Set file as read-only (Windows)
        try:
            os.chmod(self.selected_file, 0o444)
        except Exception as e:
            messagebox.showwarning("Read-only failed", f"Could not set file as read-only: {e}")
        self.db_cursor.execute(
            "INSERT INTO file_logs (file_path, timestamp, user_role, action, detail) VALUES (?, ?, ?, ?, ?)",
            (str(self.selected_file), datetime.now().isoformat(), self.current_role.get(), "lock", "File locked by supervisor"),
        )
        self.db_conn.commit()
        self.selected_file_mtime = self.selected_file.stat().st_mtime
        self.update_lock_status(True)
        messagebox.showinfo("Locked", "File has been locked for editing and set to read-only.")
        self.refresh_logs()
        self.populate_tree()

    def unlock_file(self):
        if not self.selected_file:
            messagebox.showwarning("Select file", "Select a file first.")
            return
        if self.current_role.get() != "supervisor":
            messagebox.showwarning("Supervisor only", "Only supervisors may unlock files.")
            return
        password = simpledialog.askstring("Supervisor Password", "Enter supervisor password:", show="*")
        if password != LOCK_PASSWORD:
            messagebox.showerror("Invalid password", "Supervisor password is incorrect.")
            return
        # Remove read-only attribute (Windows)
        try:
            os.chmod(self.selected_file, 0o666)
        except Exception as e:
            messagebox.showwarning("Writable failed", f"Could not remove read-only attribute: {e}")
        self.db_cursor.execute(
            "INSERT INTO file_logs (file_path, timestamp, user_role, action, detail) VALUES (?, ?, ?, ?, ?)",
            (str(self.selected_file), datetime.now().isoformat(), self.current_role.get(), "unlock", "File unlocked by supervisor"),
        )
        self.db_conn.commit()
        self.update_lock_status(False)
        messagebox.showinfo("Unlocked", "File has been unlocked and is now writable.")
        self.refresh_logs()
        self.populate_tree()

    def send_file_to_target(self):
        if not self.selected_file or not self.selected_file.is_file():
            messagebox.showwarning("Select file", "Select a file first.")
            return
        target = filedialog.askdirectory(title="Select target destination folder")
        if not target:
            return
        dest_path = Path(target) / self.selected_file.name
        try:
            shutil.copy2(self.selected_file, dest_path)
            self.log_action(self.selected_file, "send", f"Sent to {dest_path}")
            messagebox.showinfo("Sent", f"File copied to {dest_path}")
            self.refresh_logs()
        except Exception as e:
            messagebox.showerror("Copy failed", f"Unable to copy file: {e}")

    def show_compare(self, auto=False):
        if not self.selected_file or self.selected_file.suffix.lower() != ".nc":
            self.clear_compare_area()
            if not auto:
                messagebox.showwarning("Select .nc file", "Select a .nc file first.")
            return
        self.db_cursor.execute(
            "SELECT version_path FROM file_versions WHERE file_path = ? ORDER BY id DESC LIMIT 1",
            (str(self.selected_file),),
        )
        row = self.db_cursor.fetchone()
        if not row:
            self.clear_compare_area()
            if not auto:
                messagebox.showinfo("No versions", "No previous version available to compare.")
            return
        version_file = Path(row[0])
        if not version_file.exists():
            self.clear_compare_area()
            if not auto:
                messagebox.showerror("Version missing", "The previous version file is missing.")
            return
        try:
            with open(version_file, "r", encoding="utf-8", errors="replace") as f:
                old_text = f.readlines()
            with open(self.selected_file, "r", encoding="utf-8", errors="replace") as f:
                current_text = f.readlines()
        except Exception as e:
            self.clear_compare_area()
            if not auto:
                messagebox.showerror("Compare error", f"Unable to read files for comparison: {e}")
            return
        diff = self.generate_diff(old_text, current_text)
        self.compare_text.config(state=tk.NORMAL)
        self.compare_text.delete("1.0", tk.END)
        self.compare_text.insert(tk.END, diff)
        self.compare_text.config(state=tk.DISABLED)

    def generate_diff(self, old, new):
        diff_lines = difflib.unified_diff(old, new, fromfile="previous_version", tofile="current_file", lineterm="")
        return "\n".join(diff_lines) or "No differences detected."

    def refresh_logs(self):
        self.db_cursor.execute("SELECT timestamp, user_role, action, file_path, detail FROM file_logs ORDER BY id DESC LIMIT 200")
        rows = self.db_cursor.fetchall()
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        for timestamp, user_role, action, file_path, detail in rows:
            self.log_text.insert(tk.END, f"[{timestamp}] {user_role}: {action} - {file_path} {detail}\n")
        self.log_text.config(state=tk.DISABLED)

    def log_action(self, file_path, action, detail):
        self.db_cursor.execute(
            "INSERT INTO file_logs (file_path, timestamp, user_role, action, detail) VALUES (?, ?, ?, ?, ?)",
            (str(file_path), datetime.now().isoformat(), self.current_role.get(), action, detail),
        )
        self.db_conn.commit()

    def update_lock_status(self, locked=None):
        if locked is not None:
            status = locked
        elif not self.selected_file:
            status = False
        else:
            self.db_cursor.execute(
                "SELECT action FROM file_logs WHERE file_path = ? ORDER BY id DESC LIMIT 1",
                (str(self.selected_file),),
            )
            last = self.db_cursor.fetchone()
            status = last and last[0] == "lock"
        self.lock_status_label.config(text=f"File locked: {'yes' if status else 'no'}")

    def is_file_locked(self):
        if not self.selected_file:
            return False
        self.db_cursor.execute(
            "SELECT action FROM file_logs WHERE file_path = ? ORDER BY id DESC LIMIT 1",
            (str(self.selected_file),),
        )
        last = self.db_cursor.fetchone()
        return bool(last and last[0] == "lock")

    def clear_edit_area(self):
        self.edit_text.config(state=tk.NORMAL)
        self.edit_text.delete("1.0", tk.END)
        self.edit_text.config(state=tk.NORMAL)

    def clear_compare_area(self):
        self.compare_text.config(state=tk.NORMAL)
        self.compare_text.delete("1.0", tk.END)
        self.compare_text.config(state=tk.DISABLED)

    def start_file_monitor(self):
        def monitor_loop():
            while True:
                time.sleep(5)
                if self.selected_file and self.selected_file.exists() and self.selected_file.suffix.lower() == ".nc":
                    try:
                        current_mtime = self.selected_file.stat().st_mtime
                    except FileNotFoundError:
                        continue
                    if self.selected_file_mtime and current_mtime != self.selected_file_mtime:
                        self.selected_file_mtime = current_mtime
                        self.root.after(0, self.notify_external_change)
        thread = threading.Thread(target=monitor_loop, daemon=True)
        thread.start()

    def notify_external_change(self):
        if self.selected_file and self.selected_file.exists():
            if messagebox.askyesno("External change detected", "The selected .nc file has changed outside the editor. Reload preview? "):
                self.display_file_preview(self.selected_file)
                self.clear_edit_area()
                self.clear_compare_area()

    def on_close(self):
        self.db_conn.close()
        self.root.destroy()

if __name__ == "__main__":
    app = tk.Tk()
    FileManagerApp(app)
    app.mainloop()
