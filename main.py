"""
Auth UI - Professional Login & Sign-Up (Tkinter)

Features:
- Modern, clean login and signup UI using Tkinter and ttk
- Secure password storage using PBKDF2-HMAC-SHA256 (salted) in users.csv
- Signup validates matching passwords and username uniqueness
- Login validates credentials and shows welcome message
- Password masking, toggle to show/hide, and inline validation messages
- Modular, well-commented code

How to run:
python d:\\spandana_env\\auth_ui.py

No external packages required.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import os
import csv
import hashlib
import secrets
import subprocess
import sys
import json
from typing import Optional, Tuple

# ---------- Configuration ----------
BASE_DIR = os.path.dirname(__file__)
# Make users CSV an absolute path to avoid relative-path permission surprises
USERS_CSV = os.path.abspath(os.path.join(BASE_DIR, 'users.csv'))
# Use the explicit chat bot path provided by the user to avoid "not found" issues
CHAT_BOT_PATH = os.path.normpath(r'D:\spandana_env\chat_bot.py')
# Global salt (only used internally if you choose to keep a salt that is not stored per-user).
# Since you requested no salt column, new users will be stored with a single hash (no salt stored).
# We still use a global salt here to make the stored hash less trivial than raw SHA256(password),
# but it is not written to the CSV. Change or remove if you prefer plain hashing.
GLOBAL_SALT = b'spandana_global_salt_v1'
# UI theme colors
PRIMARY = '#1E88E5'   # Blue
PRIMARY_DARK = '#1565C0'
BG_COLOR = '#F4F6F9'   # Light gray background for app
CARD_BG = '#FFFFFF'    # White card background
ACCENT = '#00BFA5'     # Teal accent
TEXT_COLOR = '#263238' # Dark text
ERROR_COLOR = '#D32F2F'

# ---------- Utilities: password hashing ----------
def ensure_users_csv():
    # If file doesn't exist, create with new header
    if not os.path.exists(USERS_CSV):
        with open(USERS_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['username', 'password'])
        return

    # If file exists, check for legacy columns and migrate to username,password
    try:
        with open(USERS_CSV, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            try:
                header = next(reader)
            except StopIteration:
                # empty file: write header
                with open(USERS_CSV, 'w', newline='', encoding='utf-8') as fw:
                    writer = csv.writer(fw)
                    writer.writerow(['username', 'password'])
                return
            hdr_lower = [h.strip().lower() for h in header]

        if 'salt' in hdr_lower or 'pwd_hash' in hdr_lower:
            # perform migration: read old rows, create backup, rewrite in new format
            migrate_users_csv()
    except Exception:
        # If any error reading, leave file untouched
        return


def migrate_users_csv():
    """Migrate legacy users.csv (username,salt,pwd_hash) to (username,password) where password is salt$hash.
    Creates a backup file users.csv.bak.TIMESTAMP before overwriting.
    """
    try:
        with open(USERS_CSV, 'r', newline='', encoding='utf-8') as f:
            dict_reader = csv.DictReader(f)
            rows = list(dict_reader)
    except Exception:
        return False

    # Detect if migration is needed
    need_migrate = False
    for r in rows:
        keys = [k.strip().lower() for k in r.keys()]
        if 'salt' in keys or 'pwd_hash' in keys:
            need_migrate = True
            break

    if not need_migrate:
        return True

    # Build new rows
    new_rows = []
    for r in rows:
        # find username key
        uname = ''
        for k in r.keys():
            if k.strip().lower() == 'username':
                uname = (r.get(k) or '').strip()
                break
        # find salt/hash
        salt = ''
        h = ''
        for k in r.keys():
            lk = k.strip().lower()
            if lk == 'salt':
                salt = (r.get(k) or '').strip()
            if lk == 'pwd_hash' or lk == 'hash' or lk == 'pwdhash':
                h = (r.get(k) or '').strip()
        combined = f"{salt}${h}"
        new_rows.append((uname, combined))

    # Backup original
    try:
        import shutil, time
        bak_name = USERS_CSV + f'.bak.{int(time.time())}'
        shutil.copy2(USERS_CSV, bak_name)
    except Exception:
        # if backup fails, abort to avoid data loss
        return False

    # Write new file with header username,password
    try:
        with open(USERS_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['username', 'password'])
            for uname, combined in new_rows:
                writer.writerow([uname, combined])
        return True
    except Exception:
        return False


def hash_password(password: str) -> str:
    """Return hash_hex using PBKDF2-HMAC-SHA256 with a global salt.

    Note: this does NOT return or store a per-user salt. The CSV will contain a single
    password column which is the hex hash. This meets the "no salt column" requirement.
    """
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), GLOBAL_SALT, 200_000)
    return pwd_hash.hex()


def verify_password_new(password: str, hash_hex: str) -> bool:
    """Verify a password against the new no-salt hash format."""
    expected = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), GLOBAL_SALT, 200_000)
    return expected.hex() == hash_hex


def verify_password_legacy(password: str, salt_hex: str, hash_hex: str) -> bool:
    """Verify against the legacy per-user salt$hash format."""
    salt = bytes.fromhex(salt_hex)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 200_000)
    return pwd_hash.hex() == hash_hex

# ---------- Auth manager ----------
class AuthManager:
    def __init__(self, path=USERS_CSV):
        # Normalize to absolute path
        self.path = os.path.abspath(path)
        # Ensure users file exists / migrate legacy formats
        try:
            ensure_users_csv()
        except Exception:
            # don't raise here; file permission issues will be surfaced on operations
            pass

    def _read_all(self):
        # Robust reader that accepts several CSV layouts:
        # - ['username','password'] (current)
        # - ['username','salt','pwd_hash'] (older)
        # - fallback to positional columns
        rows = []
        try:
            with open(self.path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                try:
                    header = next(reader)
                except StopIteration:
                    return []

                hdr_lower = [h.strip().lower() for h in header]

                # Case 1: username & password column names present
                if 'username' in hdr_lower and 'password' in hdr_lower:
                    # read with DictReader to preserve headers
                    f.seek(0)
                    dict_reader = csv.DictReader(f)
                    for r in dict_reader:
                        # normalize access via header names (case-insensitive)
                        uname_key = next((k for k in r.keys() if k.strip().lower() == 'username'), None)
                        pwd_key = next((k for k in r.keys() if k.strip().lower() == 'password'), None)
                        uname = (r.get(uname_key) or '').strip() if uname_key else ''
                        pwd = (r.get(pwd_key) or '').strip() if pwd_key else ''
                        rows.append({'username': uname, 'password': pwd})

                # Case 2: older format with salt and pwd_hash columns
                elif 'username' in hdr_lower and 'salt' in hdr_lower and 'pwd_hash' in hdr_lower:
                    f.seek(0)
                    dict_reader = csv.DictReader(f)
                    for r in dict_reader:
                        uname_key = next((k for k in r.keys() if k.strip().lower() == 'username'), None)
                        salt_key = next((k for k in r.keys() if k.strip().lower() == 'salt'), None)
                        hash_key = next((k for k in r.keys() if k.strip().lower() == 'pwd_hash'), None)
                        uname = (r.get(uname_key) or '').strip() if uname_key else ''
                        salt = (r.get(salt_key) or '').strip() if salt_key else ''
                        h = (r.get(hash_key) or '').strip() if hash_key else ''
                        combined = f"{salt}${h}"
                        rows.append({'username': uname, 'password': combined})

                else:
                    # Fallback: treat file as positional CSV (skip header already read)
                    # Use header row values as first data row if it doesn't look like headers
                    # If header looks like column names (contains non-empty strings), assume it's header and proceed with remaining rows
                    for r in reader:
                        if len(r) >= 2:
                            rows.append({'username': r[0].strip(), 'password': r[1].strip()})
                        elif len(r) == 1:
                            rows.append({'username': r[0].strip(), 'password': ''})
        except FileNotFoundError:
            return []
        return rows

    def user_exists(self, username: str) -> bool:
        rows = self._read_all()
        return any(row['username'] == username for row in rows)

    def create_user(self, username: str, password: str) -> Tuple[bool, str]:
        if self.user_exists(username):
            return False, 'Username already exists'
        # For new users we store only the hash (no per-user salt column)
        pwd_hash = hash_password(password)
        try:
            with open(self.path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([username, pwd_hash])
        except PermissionError:
            # Surface a helpful error message to the user without crashing the app
            try:
                messagebox.showerror('Permission denied',
                                     "Can't write to users.csv. Please check file permissions or run the application with sufficient privileges.")
            except Exception:
                pass
            return False, 'Permission denied writing users.csv'
        except Exception as ex:
            try:
                messagebox.showerror('Error', f'Failed to create user: {ex}')
            except Exception:
                pass
            return False, f'Failed to create user: {ex}'
        return True, 'User created'

    def verify_user(self, username: str, password: str) -> bool:
        rows = self._read_all()
        for r in rows:
            if r['username'] == username:
                # password column stores salt and hash combined as salt$hash
                stored = r.get('password', '')
                if not stored:
                    return False
                # Legacy format: salt$hash
                if '$' in stored:
                    salt_hex, hash_hex = stored.split('$', 1)
                    return verify_password_legacy(password, salt_hex, hash_hex)
                # New format: single hash only
                return verify_password_new(password, stored)
        return False

    def get_user_hash(self, username: str) -> str:
        """Get the password hash for a user"""
        rows = self._read_all()
        for r in rows:
            if r['username'] == username:
                return r.get('password', '')
        return ''

# ---------- GUI Application ----------
class AuthUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('SPANDANA AI')
        self.geometry('800x520')
        self.configure(bg=BG_COLOR)
        self.resizable(False, False)

        self.auth = AuthManager()
        self.style_setup()
        self.build_ui()

    def style_setup(self):
        s = ttk.Style(self)
        # Use clam theme for more modern look if available
        try:
            s.theme_use('clam')
        except Exception:
            pass
        s.configure('TFrame', background=BG_COLOR)
        s.configure('Card.TFrame', background=CARD_BG, relief='flat')
        s.configure('Header.TLabel', font=('Segoe UI', 16, 'bold'), background=CARD_BG, foreground=TEXT_COLOR)
        s.configure('TLabel', background=BG_COLOR, foreground=TEXT_COLOR, font=('Segoe UI', 10))
        s.configure('Card.TLabel', background=CARD_BG, foreground=TEXT_COLOR, font=('Segoe UI', 10))
        s.configure('Accent.TButton', background=PRIMARY, foreground='white', font=('Segoe UI', 10, 'bold'))
        s.map('Accent.TButton', background=[('active', PRIMARY_DARK)])
        s.configure('Link.TButton', background=CARD_BG, foreground=PRIMARY, borderwidth=0, font=('Segoe UI', 9, 'underline'))
        s.configure('Danger.TLabel', foreground=ERROR_COLOR, background=CARD_BG)

    # Helper: draw rounded rectangle on a canvas
    def _round_rect(self, canvas, x1, y1, x2, y2, r=25, **kwargs):
        points = [
            x1+r, y1,
            x1+r, y1,
            x2-r, y1,
            x2-r, y1,
            x2, y1,
            x2, y1+r,
            x2, y2-r,
            x2, y2-r,
            x2, y2,
            x2-r, y2,
            x1+r, y2,
            x1+r, y2,
            x1, y2,
            x1, y2-r,
            x1, y1+r,
            x1, y1+r,
            x1, y1
        ]
        return canvas.create_polygon(points, smooth=True, **kwargs)

    def build_ui(self):
        # Create a Canvas for a modern background and rounded card
        canvas = tk.Canvas(self, highlightthickness=0)
        canvas.pack(fill='both', expand=True)

        # Draw simple vertical gradient background
        w = 800
        h = 520
        # gradient from light blue to white
        for i in range(h):
            r1, g1, b1 = (227,242,253)  # #E3F2FD
            r2, g2, b2 = (255,255,255)  # #FFFFFF
            r = int(r1 + (r2-r1)*(i/h))
            g = int(g1 + (g2-g1)*(i/h))
            b = int(b1 + (b2-b1)*(i/h))
            color = f'#{r:02x}{g:02x}{b:02x}'
            canvas.create_line(0, i, w, i, fill=color)

        # Draw shadow rounded rect and main card
        card_x0, card_y0, card_x1, card_y1 = 220, 70, 760, 450
        radius = 18
        # shadow
        self._round_rect(canvas, card_x0+6, card_y0+6, card_x1+6, card_y1+6, radius, fill='#d9e9ff', outline='')
        # main card
        self._round_rect(canvas, card_x0, card_y0, card_x1, card_y1, radius, fill=CARD_BG, outline='')

        # Left branding box (circle)
        circle_cx, circle_cy = 360, 190
        circle_r = 64
        canvas.create_oval(circle_cx-circle_r, circle_cy-circle_r, circle_cx+circle_r, circle_cy+circle_r, fill=PRIMARY, outline='')
        canvas.create_text(circle_cx, circle_cy, text='SP', fill='white', font=('Segoe UI', 28, 'bold'))
        canvas.create_text(360, 260, text='User Authentication', font=('Segoe UI', 12), fill=TEXT_COLOR)

        # Place a Frame over the card area to host widgets (matching CARD_BG)
        self.card_frame = tk.Frame(self, bg=CARD_BG)
        self.card_frame.place(x=card_x0+10, y=card_y0+10, width=(card_x1-card_x0)-20, height=(card_y1-card_y0)-20)

        # Navigation buttons (Login / Sign Up) at top-right of card_frame
        nav_frame = tk.Frame(self.card_frame, bg=CARD_BG)
        nav_frame.pack(anchor='ne', pady=(6,12), padx=10)

        self.login_btn = tk.Button(nav_frame, text='Login', command=self.show_login, bg=PRIMARY, fg='white', bd=0, padx=14, pady=6, activebackground=PRIMARY_DARK, cursor='hand2')
        self.signup_btn = tk.Button(nav_frame, text='Sign Up', command=self.show_signup, bg=CARD_BG, fg=PRIMARY, bd=0, padx=10, pady=6, cursor='hand2')
        self.login_btn.pack(side='left')
        self.signup_btn.pack(side='left', padx=(8,0))

        # hover effects for nav buttons
        def _on_enter(btn, hover_bg):
            btn['bg'] = hover_bg

        def _on_leave(btn, normal_bg):
            btn['bg'] = normal_bg

        self.login_btn.bind('<Enter>', lambda e: _on_enter(self.login_btn, PRIMARY_DARK))
        self.login_btn.bind('<Leave>', lambda e: _on_leave(self.login_btn, PRIMARY))
        self.signup_btn.bind('<Enter>', lambda e: _on_enter(self.signup_btn, '#eaf6ff'))
        self.signup_btn.bind('<Leave>', lambda e: _on_leave(self.signup_btn, CARD_BG))

        # Placeholder for form widgets inside card_frame
        self.form_container = tk.Frame(self.card_frame, bg=CARD_BG)
        self.form_container.pack(fill='both', expand=True, padx=18, pady=6)

        # Initially show login
        self.show_login()

    # ----------------- Login Form -----------------
    def show_login(self):
        self._clear_form()
        # Update nav button styles to emphasize active (use tk button config)
        self.login_btn.config(bg=PRIMARY, fg='white')
        self.signup_btn.config(bg=CARD_BG, fg=PRIMARY)

        header = ttk.Label(self.form_container, text='Welcome back', style='Header.TLabel')
        header.pack(pady=(0,10))

        info = ttk.Label(self.form_container, text='Sign in to continue to your account', style='Card.TLabel')
        info.pack(pady=(0,12))

        frm = ttk.Frame(self.form_container, style='Card.TFrame')
        frm.pack()

        ttk.Label(frm, text='Username:', style='Card.TLabel').grid(row=0, column=0, sticky='e', padx=(0,8), pady=6)
        self.login_username = ttk.Entry(frm, width=30)
        self.login_username.grid(row=0, column=1, pady=6)

        ttk.Label(frm, text='Password:', style='Card.TLabel').grid(row=1, column=0, sticky='e', padx=(0,8), pady=6)
        self.login_password = ttk.Entry(frm, width=30, show='*')
        self.login_password.grid(row=1, column=1, pady=6)

        # show/hide password
        self.login_show_var = tk.BooleanVar(value=False)
        show_chk = ttk.Checkbutton(frm, text='Show', variable=self.login_show_var, command=self._toggle_login_show)
        show_chk.grid(row=1, column=2, padx=(8,0))

        self.login_error = ttk.Label(self.form_container, text='', style='Danger.TLabel')
        self.login_error.pack()

        btn = ttk.Button(self.form_container, text='Login', command=self.handle_login, style='Accent.TButton')
        btn.pack(fill='x', pady=(12,6))

        switch = ttk.Button(self.form_container, text="Don't have an account? Sign Up", command=self.show_signup, style='Link.TButton')
        switch.pack()

    def _toggle_login_show(self):
        if self.login_show_var.get():
            self.login_password.config(show='')
        else:
            self.login_password.config(show='*')

    def handle_login(self):
        username = self.login_username.get().strip()
        password = self.login_password.get().strip()
        self.login_error.config(text='')
        if not username or not password:
            self.login_error.config(text='Please enter username and password')
            return
        ok = self.auth.verify_user(username, password)
        if ok:
            # Get the stored password hash for the user
            stored_password_hash = self.auth.get_user_hash(username)
            
            # Create session file
            session_data = {
                'username': username,
                'password_hash': stored_password_hash
            }
            session_file = os.path.join(BASE_DIR, 'spandana_session.json')
            try:
                with open(session_file, 'w', encoding='utf-8') as f:
                    json.dump(session_data, f)
            except Exception as e:
                print(f"Failed to write session file: {e}")
            
            messagebox.showinfo('Login Successful', f'Welcome, {username}!')
            # Clear fields
            self.login_username.delete(0, tk.END)
            self.login_password.delete(0, tk.END)
            # Launch chat bot app in a separate process
            self._launch_chatbot()
        else:
            self.login_error.config(text='Invalid username or password')

    # ----------------- Sign Up Form -----------------
    def show_signup(self):
        self._clear_form()
        # Update nav button styles
        self.login_btn.config(bg=CARD_BG, fg=PRIMARY)
        self.signup_btn.config(bg=PRIMARY, fg='white')

        header = ttk.Label(self.form_container, text='Create an account', style='Header.TLabel')
        header.pack(pady=(0,10))

        info = ttk.Label(self.form_container, text='Sign up to access the application', style='Card.TLabel')
        info.pack(pady=(0,12))

        frm = ttk.Frame(self.form_container, style='Card.TFrame')
        frm.pack()

        ttk.Label(frm, text='Username:', style='Card.TLabel').grid(row=0, column=0, sticky='e', padx=(0,8), pady=6)
        self.signup_username = ttk.Entry(frm, width=30)
        self.signup_username.grid(row=0, column=1, pady=6)

        ttk.Label(frm, text='Password:', style='Card.TLabel').grid(row=1, column=0, sticky='e', padx=(0,8), pady=6)
        self.signup_password = ttk.Entry(frm, width=30, show='*')
        self.signup_password.grid(row=1, column=1, pady=6)

        ttk.Label(frm, text='Confirm Password:', style='Card.TLabel').grid(row=2, column=0, sticky='e', padx=(0,8), pady=6)
        self.signup_confirm = ttk.Entry(frm, width=30, show='*')
        self.signup_confirm.grid(row=2, column=1, pady=6)

        # show/hide password
        self.signup_show_var = tk.BooleanVar(value=False)
        show_chk2 = ttk.Checkbutton(frm, text='Show', variable=self.signup_show_var, command=self._toggle_signup_show)
        show_chk2.grid(row=1, column=2, rowspan=2, padx=(8,0))

        # Password requirement hint
        hint_text = 'Password must be 8 alphanumeric characters and a special character.'
        self.signup_hint = ttk.Label(self.form_container, text=hint_text, style='Card.TLabel', wraplength=360, foreground='#666')
        self.signup_hint.pack(pady=(4,4))

        self.signup_error = ttk.Label(self.form_container, text='', style='Danger.TLabel')
        self.signup_error.pack()

        btn = ttk.Button(self.form_container, text='Create Account', command=self.handle_signup, style='Accent.TButton')
        btn.pack(fill='x', pady=(12,6))

        switch = ttk.Button(self.form_container, text='Already have an account? Login', command=self.show_login, style='Link.TButton')
        switch.pack()

    def _toggle_signup_show(self):
        if self.signup_show_var.get():
            self.signup_password.config(show='')
            self.signup_confirm.config(show='')
        else:
            self.signup_password.config(show='*')
            self.signup_confirm.config(show='*')

    def handle_signup(self):
        username = self.signup_username.get().strip()
        password = self.signup_password.get().strip()
        confirm = self.signup_confirm.get().strip()
        self.signup_error.config(text='')
        if not username or not password or not confirm:
            self.signup_error.config(text='Please fill all fields')
            return
        if password != confirm:
            self.signup_error.config(text="Passwords do not match")
            return
        # Password complexity: at least 8 chars, uppercase, lowercase, digit, special char
        import re
        if len(password) < 8:
            self.signup_error.config(text='Password should be at least 8 characters')
            return
        if not re.search(r'[A-Z]', password):
            self.signup_error.config(text='Password must include at least one uppercase letter')
            return
        if not re.search(r'[a-z]', password):
            self.signup_error.config(text='Password must include at least one lowercase letter')
            return
        if not re.search(r'[0-9]', password):
            self.signup_error.config(text='Password must include at least one digit')
            return
        # special character: any non-alphanumeric
        if not re.search(r'[^A-Za-z0-9]', password):
            self.signup_error.config(text='Password must include at least one special character')
            return
        ok, msg = self.auth.create_user(username, password)
        if ok:
            # Get the stored password hash for the user
            stored_password_hash = self.auth.get_user_hash(username)
            
            # Create session file
            session_data = {
                'username': username,
                'password_hash': stored_password_hash
            }
            session_file = os.path.join(BASE_DIR, 'spandana_session.json')
            try:
                with open(session_file, 'w', encoding='utf-8') as f:
                    json.dump(session_data, f)
            except Exception as e:
                print(f"Failed to write session file: {e}")
            
            messagebox.showinfo('Success', 'Account created. Launching the chat bot...')
            # clear
            self.signup_username.delete(0, tk.END)
            self.signup_password.delete(0, tk.END)
            self.signup_confirm.delete(0, tk.END)
            # Launch chat bot app in a separate process
            self._launch_chatbot()
        else:
            self.signup_error.config(text=msg)

    # ----------------- Helpers -----------------
    def _clear_form(self):
        for child in self.form_container.winfo_children():
            child.destroy()

    def _launch_chatbot(self):
        """Launch the chat_bot.py as a separate Python process and close the auth UI."""
        try:
            # Check if the file exists and is accessible
            if not os.path.exists(CHAT_BOT_PATH):
                messagebox.showerror('File Not Found', 
                    f'chat_bot.py not found at:\n{CHAT_BOT_PATH}\n\n'
                    f'Please ensure the file exists at this location.')
                return
            
            # Check if it's a Python file
            if not CHAT_BOT_PATH.lower().endswith('.py'):
                messagebox.showerror('Invalid File', 
                    f'The specified file is not a Python file:\n{CHAT_BOT_PATH}')
                return

            # Get the directory of the chatbot
            chat_bot_dir = os.path.dirname(CHAT_BOT_PATH)
            
            # Verify the directory exists
            if not os.path.exists(chat_bot_dir):
                messagebox.showerror('Directory Not Found', 
                    f'Directory not found:\n{chat_bot_dir}')
                return

            try:
                # First, let's test if we can import the file to check for syntax errors
                import importlib.util
                spec = importlib.util.spec_from_file_location("chat_bot", CHAT_BOT_PATH)
                if spec is None:
                    messagebox.showerror('Invalid Python File', 
                        'The file exists but cannot be loaded as a Python module.')
                    return
                    
                # Try to load the module to catch syntax errors
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
            except SyntaxError as e:
                messagebox.showerror('Syntax Error', 
                    f'Syntax error in chat_bot.py:\n\nLine {e.lineno}: {e.msg}\n\n{e.text}')
                return
            except Exception as e:
                # Other import errors might be okay - the script might run fine
                print(f"Import check warning: {e}")

            # Launch the chatbot using subprocess
            try:
                process = subprocess.Popen(
                    [sys.executable, CHAT_BOT_PATH],
                    cwd=chat_bot_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                # Check if process started successfully
                if process.poll() is not None:
                    # Process terminated immediately, check for errors
                    stdout, stderr = process.communicate()
                    error_msg = stderr.strip() if stderr else stdout.strip()
                    if not error_msg:
                        error_msg = "Process started but terminated immediately with no error output."
                    
                    messagebox.showerror('Failed to Launch', 
                        f'Could not start chat_bot.py:\n\n{error_msg}')
                    return
                
                # Success - close the auth window
                self.destroy()
                
            except FileNotFoundError:
                messagebox.showerror('Python Not Found', 
                    'Python interpreter not found. Please ensure Python is installed and in your PATH.')
            except PermissionError:
                messagebox.showerror('Permission Denied', 
                    f'Permission denied when trying to execute:\n{CHAT_BOT_PATH}')
            except OSError as e:
                if e.winerror == 123:  # Specific Windows error for invalid filename/directory
                    messagebox.showerror('Invalid Path', 
                        f'The filename, directory name, or volume label syntax is incorrect:\n{CHAT_BOT_PATH}\n\n'
                        f'Please check the path for any invalid characters.')
                else:
                    messagebox.showerror('OS Error', 
                        f'Operating system error: {e}')
            except Exception as e:
                messagebox.showerror('Unexpected Error', 
                    f'An unexpected error occurred:\n{str(e)}')
                
        except Exception as e:
            messagebox.showerror('Error', 
                f'Failed to launch chatbot:\n{str(e)}')


if __name__ == '__main__':
    # Ensure the users.csv file exists and is in the correct format
    ensure_users_csv()
    
    # Create and run the application
    app = AuthUI()
    app.mainloop()