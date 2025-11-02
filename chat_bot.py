import speech_recognition as sr
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import csv
import os
from datetime import datetime
import subprocess
import tempfile
import random
import string
import sys
import argparse
import json
from difflib import SequenceMatcher

# Try to import various TTS libraries
try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False

try:
    import win32com.client
    WIN32COM_AVAILABLE = True
except ImportError:
    WIN32COM_AVAILABLE = False

try:
    from gtts import gTTS
    import pygame
    GTTS_AVAILABLE = True
    pygame.mixer.init()
except ImportError:
    GTTS_AVAILABLE = False

# Unified CSV configuration (authentication + complaints)
CSV_PATH = "users_data.csv"  # keep existing filename for compatibility
CSV_HEADER = [
    "Username",
    "Password_Hash",
    "Name",
    "Mobile Number",
    "Location",
    "Complaint Type",
    "Complaint Description",
    "Ticket ID",
    "Status",
    "Ticket Alive",
    "Timestamp",
    "Last_Updated",  # New column for tracking status updates
    "Assigned Department"  # New column to track department
]

# Department-specific CSV configuration
DEPARTMENT_CSV_HEADER = [
    "Ticket ID",
    "Username",
    "Name", 
    "Mobile Number",
    "Location",
    "Complaint Type",
    "Complaint Description",
    "Status",
    "Urgency Level",
    "Timestamp",
    "Last_Updated"
]

TICKET_PREFIX = "TCKT"
TICKET_START = 1001

# Department mapping with file names
DEPARTMENT_MAPPING = {
    "Electrical Department": "electrical_department.csv",
    "Water Department": "water_department.csv", 
    "Public Works Department": "public_works_department.csv",
    "Sanitation Department": "sanitation_department.csv",
    "Revenue Department": "revenue_department.csv",
    "Municipal Corporation": "municipal_corporation.csv",
    "Health Department": "health_department.csv",
    "Education Department": "education_department.csv",
    "General Administration": "general_administration.csv"
}

def get_auth_data():
    """
    Fetch authentication data from auth system session file or environment
    Returns: dict with 'username' and 'password_hash' or None if not available
    """
    try:
        # Try to read from session file (created by auth system)
        session_file = os.path.join(os.path.dirname(__file__), 'spandana_session.json')
        if os.path.exists(session_file):
            with open(session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
                return {
                    'username': session_data.get('username', ''),
                    'password_hash': session_data.get('password_hash', '')
                }
        
        # Alternative: Try to get from environment variables
        username = os.environ.get('SPANDANA_USERNAME')
        password_hash = os.environ.get('SPANDANA_PASSWORD_HASH')
        if username and password_hash:
            return {
                'username': username,
                'password_hash': password_hash
            }
            
    except Exception as e:
        print(f"Warning: Could not fetch auth data: {e}")
    
    return None

def ensure_csv_has_header(path: str, header: list):
    """
    Ensure the CSV exists and has the expected header. If the file exists with a different header,
    attempt to normalize existing rows into the new header (preserving data where possible).
    """
    try:
        if not os.path.exists(path):
            with open(path, "w", newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=header)
                writer.writeheader()
            return

        # Read existing rows
        with open(path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            rows = list(reader)

        if not rows:
            with open(path, "w", newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=header)
                writer.writeheader()
            return

        existing_header = rows[0]
        if existing_header == header:
            return

        # Read as dicts using existing header and normalize
        with open(path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            existing_rows = list(reader)

        normalized = []
        for r in existing_rows:
            new_row = {col: r.get(col, "") for col in header}
            # For existing rows without Last_Updated, set it to Timestamp value
            if 'Last_Updated' not in r or not r['Last_Updated']:
                new_row['Last_Updated'] = r.get('Timestamp', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            normalized.append(new_row)

        # Rewrite with normalized rows and desired header
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=header)
            writer.writeheader()
            for nr in normalized:
                writer.writerow(nr)

    except Exception:
        # If normalization fails, don't crash the app; raise to be handled by caller
        raise

def ensure_department_csv_exists(department_name: str):
    """
    Ensure department-specific CSV file exists with proper header
    """
    if department_name not in DEPARTMENT_MAPPING:
        return None
    
    csv_file = DEPARTMENT_MAPPING[department_name]
    
    if not os.path.exists(csv_file):
        with open(csv_file, "w", newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=DEPARTMENT_CSV_HEADER)
            writer.writeheader()
    
    return csv_file

def load_all_rows(path: str) -> list:
    ensure_csv_has_header(path, CSV_HEADER)
    with open(path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return list(reader)

def append_row(path: str, row: dict):
    ensure_csv_has_header(path, CSV_HEADER)
    with open(path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
        writer.writerow(row)

def append_to_department_csv(department_name: str, row: dict):
    """
    Append complaint data to department-specific CSV file
    """
    csv_file = ensure_department_csv_exists(department_name)
    if not csv_file:
        return False
    
    try:
        with open(csv_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=DEPARTMENT_CSV_HEADER)
            writer.writerow(row)
        return True
    except Exception as e:
        print(f"Error writing to department CSV {csv_file}: {e}")
        return False

def update_complaint_status(ticket_id: str, new_status: str):
    """
    Update the status and last_updated timestamp for a specific complaint
    in both main CSV and department CSV
    """
    try:
        rows = load_all_rows(CSV_PATH)
        updated = False
        department_name = None
        
        # Update main CSV and get department name
        for i, row in enumerate(rows):
            if row.get('Ticket ID') == ticket_id:
                department_name = row.get('Assigned Department')
                rows[i]['Status'] = new_status
                rows[i]['Last_Updated'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                updated = True
                break
        
        if updated:
            # Rewrite the entire main file with updated data
            with open(CSV_PATH, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
                writer.writeheader()
                for row in rows:
                    writer.writerow(row)
            
            # Also update department CSV if department is known
            if department_name:
                update_department_complaint_status(department_name, ticket_id, new_status)
            
            return True
        return False
    except Exception as e:
        print(f"Error updating complaint status: {e}")
        return False

def update_department_complaint_status(department_name: str, ticket_id: str, new_status: str):
    """
    Update complaint status in department-specific CSV
    """
    csv_file = ensure_department_csv_exists(department_name)
    if not csv_file:
        return False
    
    try:
        # Read all rows from department CSV
        with open(csv_file, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        # Update the specific ticket
        updated = False
        for i, row in enumerate(rows):
            if row.get('Ticket ID') == ticket_id:
                rows[i]['Status'] = new_status
                rows[i]['Last_Updated'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                updated = True
                break
        
        if updated:
            # Rewrite the department CSV
            with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=DEPARTMENT_CSV_HEADER)
                writer.writeheader()
                for row in rows:
                    writer.writerow(row)
            return True
        return False
    except Exception as e:
        print(f"Error updating department complaint status: {e}")
        return False

class TicketGenerator:
    def __init__(self):
        self.department_mapping = {
            "electricity": "Electrical Department",
            "water": "Water Department", 
            "road": "Public Works Department",
            "sanitation": "Sanitation Department",
            "tax": "Revenue Department",
            "property": "Municipal Corporation",
            "health": "Health Department",
            "education": "Education Department",
            "other": "General Administration"
        }
        
        self.urgency_mapping = {
            "emergency": "High",
            "urgent": "High", 
            "critical": "High",
            "important": "Medium",
            "normal": "Medium",
            "routine": "Low",
            "minor": "Low"
        }
        
        # Track the last used ticket number
        self.last_ticket_number = self.get_last_ticket_number()
    
    def get_last_ticket_number(self):
        """Get the last ticket number from CSV file"""
        try:
            if os.path.exists(CSV_PATH):
                rows = load_all_rows(CSV_PATH)
                max_num = 0
                for r in rows:
                    tid = (r.get('Ticket ID') or '').strip()
                    if tid.startswith(TICKET_PREFIX):
                        try:
                            n = int(tid[len(TICKET_PREFIX):])
                            if n > max_num:
                                max_num = n
                        except Exception:
                            continue
                if max_num >= TICKET_START:
                    return max_num
            return TICKET_START - 1  # so first generated is TICKET_START
        except Exception:
            return TICKET_START - 1
    
    def generate_ticket_id(self):
        """Generate unique ticket ID in TCKT1001 format"""
        self.last_ticket_number += 1
        return f"TCKT{self.last_ticket_number}"
    
    def categorize_complaint(self, complaint_type, description):
        """Categorize complaint and determine urgency"""
        complaint_lower = complaint_type.lower()
        desc_lower = description.lower()
        
        # Determine department
        department = "General Administration"
        for key, value in self.department_mapping.items():
            if key in complaint_lower or key in desc_lower:
                department = value
                break
        
        # Determine urgency level
        urgency = "Medium"
        for key, value in self.urgency_mapping.items():
            if key in desc_lower:
                urgency = value
                break
        
        # Check for emergency keywords
        emergency_keywords = ["emergency", "urgent", "immediate", "critical", "accident", "fire", "flood"]
        if any(keyword in desc_lower for keyword in emergency_keywords):
            urgency = "High"
        
        return department, urgency
    
    def create_ticket(self, user_data):
        """Create a complete ticket from user data"""
        ticket_id = self.generate_ticket_id()
        citizen_name = user_data.get("Name", "Not provided")
        location = user_data.get("Location", "Not provided")
        complaint_type = user_data.get("Complaint Type", "General")
        complaint_desc = user_data.get("Complaint Description", "No description provided")
        
        # Categorize the complaint
        assigned_department, urgency_level = self.categorize_complaint(complaint_type, complaint_desc)
        
        # Create summary
        summary = f"{complaint_type}: {complaint_desc[:100]}{'...' if len(complaint_desc) > 100 else ''}"
        
        ticket = {
            "Ticket ID": ticket_id,
            "Citizen Name": citizen_name,
            "Location": location,
            "Complaint Category": complaint_type,
            "Urgency Level": urgency_level,
            "Summary": summary,
            "Assigned Department": assigned_department,
            "Status": "Open",
            "Date Submitted": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Mobile Number": user_data.get("Mobile Number", "Not provided")
        }
        
        return ticket

class UniversalTTS:
    def __init__(self):
        self.available_engines = self.detect_engines()
        self.voice_gender = 'female'  # Default to female voice
        print("Available TTS engines:", list(self.available_engines.keys()))
        
    def detect_engines(self):
        engines = {}
        
        # Check Windows SAPI
        if WIN32COM_AVAILABLE:
            try:
                win32com.client.Dispatch("SAPI.SpVoice")
                engines['sapi'] = True
            except:
                engines['sapi'] = False
        else:
            engines['sapi'] = False
        
        # Check pyttsx3
        if PYTTSX3_AVAILABLE:
            try:
                engine = pyttsx3.init()
                engine.say("")
                engine.runAndWait()
                engines['pyttsx3'] = True
            except:
                engines['pyttsx3'] = False
        else:
            engines['pyttsx3'] = False
            
        # Check Google TTS
        engines['gtts'] = GTTS_AVAILABLE
        
        # Check eSpeak
        try:
            result = subprocess.run(['espeak', '--version'], 
                                  capture_output=True, text=True, shell=True)
            engines['espeak'] = result.returncode == 0
        except:
            engines['espeak'] = False
            
        return engines    
        
    def set_female_voice_pyttsx3(self, engine):
        """Set female voice for pyttsx3 if available"""
        voices = engine.getProperty('voices')
        for voice in voices:
            # Look for female voices - common indicators
            if 'female' in voice.name.lower() or 'zira' in voice.name.lower() or 'eva' in voice.name.lower():
                engine.setProperty('voice', voice.id)
                return True
            # For some systems, female voices might be marked differently
            elif 'female' in voice.id.lower() or 'zira' in voice.id.lower():
                engine.setProperty('voice', voice.id)
                return True
        return False
    
    def set_female_voice_sapi(self, speaker):
        """Set female voice for SAPI if available"""
        try:
            voices = speaker.GetVoices()
            for voice in voices:
                if 'female' in voice.GetDescription().lower() or 'zira' in voice.GetDescription().lower():
                    speaker.Voice = voice
                    return True
        except:
            pass
        return False
    
    def speak_sapi(self, text):
        try:
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            
            # Try to set female voice
            if self.voice_gender == 'female':
                self.set_female_voice_sapi(speaker)
            
            speaker.Speak(text)
            return True
        except Exception as e:
            print(f"SAPI Error: {e}")
            return False
    
    def speak_pyttsx3(self, text):
        try:
            engine = pyttsx3.init()
            
            # Try to set female voice
            if self.voice_gender == 'female':
                self.set_female_voice_pyttsx3(engine)
            
            # Adjust speech rate and volume for better quality
            engine.setProperty('rate', 150)  # Speed percent
            engine.setProperty('volume', 0.9)  # Volume 0-1
            
            engine.say(text)
            engine.runAndWait()
            return True
        except Exception as e:
            print(f"pyttsx3 Error: {e}")
            return False
    
    def speak_gtts(self, text, lang='en'):
        try:
            # For Telugu, use 'te' language code
            tts_lang = 'te' if lang == 'te' else 'en'
            tts = gTTS(text=text, lang=tts_lang, slow=False)
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as fp:
                temp_file = fp.name
            
            tts.save(temp_file)
            pygame.mixer.music.load(temp_file)
            pygame.mixer.music.play()
            
            # Wait for playback to complete
            while pygame.mixer.music.get_busy():
                pygame.time.wait(100)
            
            os.unlink(temp_file)
            return True
        except Exception as e:
            print(f"gTTS Error: {e}")
            return False
    
    def speak_espeak(self, text, language='en'):
        try:
            # For female voice in eSpeak, use -v with female variant
            voice_param = f'{language}+f3' if self.voice_gender == 'female' else language
            cmd = ['espeak', '-v', voice_param, '-s', '150', '-p', '50', text]
            subprocess.run(cmd, capture_output=True, shell=True)
            return True
        except Exception as e:
            print(f"eSpeak Error: {e}")
            return False
    
    def set_voice_gender(self, gender):
        """Set voice gender (male/female)"""
        self.voice_gender = gender
        print(f"Voice gender set to: {gender}")
    
    def speak(self, text, language='te'):
        def run_speak():
            # Try engines in order of preference
            if self.available_engines.get('sapi', False):
                if self.speak_sapi(text):
                    print("Used SAPI for TTS")
                    return
            
            if self.available_engines.get('pyttsx3', False):
                if self.speak_pyttsx3(text):
                    print("Used pyttsx3 for TTS")
                    return
            
            if self.available_engines.get('gtts', False):
                if self.speak_gtts(text, language):
                    print("Used gTTS for TTS")
                    return
            
            if self.available_engines.get('espeak', False):
                if self.speak_espeak(text, language):
                    print("Used eSpeak for TTS")
                    return
            
            # Fallback: just print the text
            print(f"No TTS available. Would speak: {text}")
        
        thread = threading.Thread(target=run_speak)
        thread.daemon = True
        thread.start()

class DataManager:
    def __init__(self):
        self.csv_file = CSV_PATH
        # Ensure file and header are correct
        try:
            ensure_csv_has_header(self.csv_file, CSV_HEADER)
        except Exception as e:
            print(f"Warning: failed to ensure CSV header: {e}")
    
    def ensure_csv_file(self):
        """Ensure the CSV file exists with proper headers"""
        # Deprecated: initialization handled by ensure_csv_has_header in __init__
        ensure_csv_has_header(self.csv_file, CSV_HEADER)
    
    def save_complaint_data(self, user_data, ticket_data):
        """Save complaint data to CSV file with authentication data and also to department CSV"""
        try:
            # Get authentication data
            auth_data = get_auth_data()
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            assigned_department = ticket_data.get('Assigned Department', 'General Administration')
            
            # Build a dict matching CSV_HEADER and append
            row = {
                'Username': auth_data.get('username', 'N/A') if auth_data else 'N/A',
                'Password_Hash': auth_data.get('password_hash', 'N/A') if auth_data else 'N/A',
                'Name': user_data.get('Name', ''),
                'Mobile Number': user_data.get('Mobile Number', ''),
                'Location': user_data.get('Location', ''),
                'Complaint Type': user_data.get('Complaint Type', ''),
                'Complaint Description': user_data.get('Complaint Description', ''),
                'Ticket ID': ticket_data.get('Ticket ID', ''),
                'Status': 'Open',
                'Ticket Alive': 'Yes',
                'Timestamp': current_time,
                'Last_Updated': current_time,  # Set initial last updated time
                'Assigned Department': assigned_department  # Store department in main CSV
            }
            
            # Save to main CSV
            append_row(self.csv_file, row)
            
            # Also save to department-specific CSV
            department_row = {
                'Ticket ID': ticket_data.get('Ticket ID', ''),
                'Username': auth_data.get('username', 'N/A') if auth_data else 'N/A',
                'Name': user_data.get('Name', ''),
                'Mobile Number': user_data.get('Mobile Number', ''),
                'Location': user_data.get('Location', ''),
                'Complaint Type': user_data.get('Complaint Type', ''),
                'Complaint Description': user_data.get('Complaint Description', ''),
                'Status': 'Open',
                'Urgency Level': ticket_data.get('Urgency Level', 'Medium'),
                'Timestamp': current_time,
                'Last_Updated': current_time
            }
            
            append_to_department_csv(assigned_department, department_row)
            
            return True
        except Exception as e:
            print(f"Error saving data: {e}")
            return False

    def find_duplicate_complaint(self, user_data):
        """
        Check if the same user has already submitted the same complaint type.
        Uses Username + Password_Hash + Complaint Type to identify duplicates.
        Returns: (is_duplicate, existing_ticket_id)
        """
        try:
            auth_data = get_auth_data()
            if not auth_data or not auth_data.get('username') or not auth_data.get('password_hash'):
                return False, None
                
            username = auth_data.get('username')
            password_hash = auth_data.get('password_hash')
            complaint_type = user_data.get('Complaint Type', '').strip().lower()
            
            rows = load_all_rows(self.csv_file)
            
            for r in rows:
                # Check if same user (username + password_hash) and same complaint type
                if (r.get('Username', '').strip() == username.strip() and 
                    r.get('Password_Hash', '').strip() == password_hash.strip() and
                    r.get('Complaint Type', '').strip().lower() == complaint_type):
                    return True, r.get('Ticket ID', 'Unknown')
            
            return False, None
            
        except Exception as e:
            print(f"Error checking duplicate complaint: {e}")
            return False, None

    def get_complaint_history(self, ticket_id: str):
        """
        Get the complete history of a complaint including status changes
        """
        try:
            rows = load_all_rows(self.csv_file)
            for r in rows:
                if r.get('Ticket ID') == ticket_id:
                    return {
                        'ticket_id': r.get('Ticket ID'),
                        'status': r.get('Status'),
                        'created': r.get('Timestamp'),
                        'last_updated': r.get('Last_Updated'),
                        'complaint_type': r.get('Complaint Type'),
                        'description': r.get('Complaint Description'),
                        'department': r.get('Assigned Department')
                    }
            return None
        except Exception as e:
            print(f"Error getting complaint history: {e}")
            return None

    def get_department_complaints(self, department_name: str):
        """
        Get all complaints for a specific department
        """
        try:
            csv_file = ensure_department_csv_exists(department_name)
            if not csv_file:
                return []
            
            with open(csv_file, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                return list(reader)
        except Exception as e:
            print(f"Error getting department complaints: {e}")
            return []

class VoiceChatbotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("SPANDANA AI")
        self.root.geometry("900x650")
        self.root.configure(bg='#000000')  # Black background
        
        # Initialize speech components
        self.tts_engine = UniversalTTS()
        self.recognizer = sr.Recognizer()
        
        # Initialize ticket generator and data manager
        self.ticket_generator = TicketGenerator()
        self.data_manager = DataManager()
        
        # Set female voice by default
        self.tts_engine.set_voice_gender('female')
        
        # User data storage
        self.user_data = {}
        self.current_field_index = 0
        
        # Define fields in Telugu
        self.fields = {
            "Name": "Please say your name.",
            "Mobile Number": "Please say your mobile number.", 
            "Location": "Please say your location.",
            "Complaint Type": "What type of complaint do you have?",
            "Complaint Description": "Please describe your complaint."
        }
        
        self.setup_ui()
        self.start_conversation()
    
    def setup_ui(self):
        # Header
        header_frame = tk.Frame(self.root, bg='#000000', height=120)
        header_frame.pack(fill=tk.X, padx=20, pady=10)
        header_frame.pack_propagate(False)
        
        title_label = tk.Label(
            header_frame, 
            text="SPANDANA AI", 
            font=('Arial', 22, 'bold'),
            fg='white',  # White text
            bg='#000000'  # Black background
        )
        title_label.pack(expand=True, pady=5)
        
        # Progress indicator
        self.progress_label = tk.Label(
            header_frame,
            text="Progress: 0/5 completed",
            font=('Arial', 10, 'bold'),
            fg='white',
            bg='#000000'
        )
        self.progress_label.pack(expand=True, pady=2)
        
        # Main content area
        main_frame = tk.Frame(self.root, bg="#000000")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Chat display area
        self.chat_frame = tk.Frame(main_frame, bg="#000000")
        self.chat_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create a canvas and scrollbar for the chat
        self.chat_canvas = tk.Canvas(self.chat_frame, bg='#000000', highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.chat_frame, orient="vertical", command=self.chat_canvas.yview)
        self.scrollable_frame = tk.Frame(self.chat_canvas, bg='#000000')
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.chat_canvas.configure(scrollregion=self.chat_canvas.bbox("all"))
        )
        
        self.chat_canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.chat_canvas.configure(yscrollcommand=scrollbar.set)
        
        self.chat_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Input area
        input_frame = tk.Frame(main_frame, bg='#000000')
        input_frame.pack(fill=tk.X, pady=10)
        
        # Status label
        self.status_label = tk.Label(
            input_frame,
            text="Ready to listen",
            font=('Arial', 10, 'italic'),
            bg='#000000',
            fg='white'
        )
        self.status_label.pack(side=tk.TOP, fill=tk.X, pady=5)
        
        # Buttons frame
        button_frame = tk.Frame(input_frame, bg='#000000')
        button_frame.pack(fill=tk.X, pady=5)
        
        # Listen button
        self.listen_btn = tk.Button(
            button_frame,
            text="Start Listening",
            command=self.start_listening,
            font=('Arial', 12, 'bold'),
            bg='#333333',  # Dark gray
            fg='white',
            padx=20,
            pady=10,
            relief='flat'
        )
        self.listen_btn.pack(side=tk.LEFT, padx=5)
        
        # Voice gender toggle button
        self.voice_toggle_btn = tk.Button(
            button_frame,
            text="Switch to Male Voice",
            command=self.toggle_voice_gender,
            font=('Arial', 10),
            bg='#333333',  # Dark gray
            fg='white',
            padx=15,
            pady=5,
            relief='flat'
        )
        self.voice_toggle_btn.pack(side=tk.LEFT, padx=5)
        
        # Clear response button
        self.clear_response_btn = tk.Button(
            button_frame,
            text="Clear Last Response",
            command=self.clear_current_response,
            font=('Arial', 10),
            bg='#333333',  # Dark gray
            fg='white',
            padx=15,
            pady=5,
            relief='flat'
        )
        self.clear_response_btn.pack(side=tk.LEFT, padx=5)
        
        # Single "View Form Data" button (replaces all previous buttons)
        self.view_data_btn = tk.Button(
            button_frame,
            text="View Form Data",
            command=self.show_form_data_review,
            font=('Arial', 12, 'bold'),
            bg='#1E88E5',  # Blue color
            fg='white',
            padx=20,
            pady=10,
            relief='flat',
            state=tk.DISABLED
        )
        self.view_data_btn.pack(side=tk.RIGHT, padx=5)
        
        # Progress bar
        self.progress = ttk.Progressbar(
            input_frame, 
            orient=tk.HORIZONTAL, 
            length=100, 
            mode='determinate'
        )
        self.progress.pack(fill=tk.X, pady=5)
        self.update_progress()

    def show_form_data_review(self):
        """Show the form data review window with Preview and Save Data buttons"""
        if not self.user_data or len(self.user_data) < len(self.fields):
            messagebox.showwarning("Incomplete Data", "Please complete all questions first.")
            return
        
        # Create review window
        review_window = tk.Toplevel(self.root)
        review_window.title("Review Your Complaint Details - SPANDANA AI")
        review_window.geometry("700x650")  # Increased size
        review_window.configure(bg='#2C3E50')
        review_window.resizable(True, True)
        
        # Center the window and make sure it's on top
        review_window.transient(self.root)
        review_window.grab_set()
        
        # Use grid for better layout control
        review_window.grid_rowconfigure(1, weight=1)  # Main content area expands
        review_window.grid_columnconfigure(0, weight=1)
        
        # Header
        header_frame = tk.Frame(review_window, bg='#34495E', height=80)
        header_frame.grid(row=0, column=0, sticky='ew', padx=0, pady=0)
        header_frame.grid_propagate(False)
        
        title_label = tk.Label(
            header_frame,
            text="Complaint Details Review",
            font=('Arial', 18, 'bold'),
            fg='white',
            bg='#34495E'
        )
        title_label.pack(expand=True, pady=20)
        
        # Main content area with scrollbar
        main_content = tk.Frame(review_window, bg='#2C3E50')
        main_content.grid(row=1, column=0, sticky='nsew', padx=20, pady=10)
        main_content.grid_rowconfigure(0, weight=1)
        main_content.grid_columnconfigure(0, weight=1)
        
        # Create canvas and scrollbar
        canvas = tk.Canvas(main_content, bg='#2C3E50', highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_content, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg='#2C3E50')
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Data display frame
        data_frame = tk.Frame(scrollable_frame, bg='#34495E', relief='raised', bd=2, padx=20, pady=20)
        data_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Display user data in a structured format
        row = 0
        for field, value in self.user_data.items():
            # Field label
            field_label = tk.Label(
                data_frame,
                text=f"{field}:",
                font=('Arial', 12, 'bold'),
                bg='#34495E',
                fg='#ECF0F1',
                anchor='w'
            )
            field_label.grid(row=row, column=0, sticky='w', padx=15, pady=12)
            
            # Value label
            value_label = tk.Label(
                data_frame,
                text=value,
                font=('Arial', 11),
                bg='#34495E',
                fg='#BDC3C7',
                anchor='w',
                wraplength=450,
                justify=tk.LEFT
            )
            value_label.grid(row=row, column=1, sticky='w', padx=15, pady=12)
            
            row += 1
        
        # Configure grid weights for data_frame
        data_frame.columnconfigure(1, weight=1)
        
        # Pack canvas and scrollbar
        canvas.grid(row=0, column=0, sticky='nsew')
        scrollbar.grid(row=0, column=1, sticky='ns')
        
        # Buttons frame at bottom - FIXED: Using grid with proper row
        buttons_frame = tk.Frame(review_window, bg='#2C3E50', height=100)
        buttons_frame.grid(row=2, column=0, sticky='ew', padx=20, pady=15)
        buttons_frame.grid_propagate(False)
        buttons_frame.grid_columnconfigure(0, weight=1)
        buttons_frame.grid_columnconfigure(1, weight=1)
        
        # Preview button (allows editing) - LEFT side
        preview_btn = tk.Button(
            buttons_frame,
            text="Preview/Edit",
            command=lambda: self.open_editable_preview(review_window),
            font=('Arial', 12, 'bold'),
            bg='#F39C12',  # Orange
            fg='white',
            padx=30,
            pady=15,
            relief='raised',
            cursor='hand2',
            bd=3
        )
        preview_btn.grid(row=0, column=0, padx=10, pady=10, sticky='ew')
        
        # Save Data button - RIGHT side
        save_btn = tk.Button(
            buttons_frame,
            text="Save Data",
            command=lambda: self.save_complaint_data_and_show_ticket(review_window),
            font=('Arial', 12, 'bold'),
            bg='#27AE60',  # Green
            fg='white',
            padx=30,
            pady=15,
            relief='raised',
            cursor='hand2',
            bd=3
        )
        save_btn.grid(row=0, column=1, padx=10, pady=10, sticky='ew')
        
        # Configure button hover effects
        def on_enter_preview(e):
            preview_btn.config(bg='#E67E22', relief='sunken')
        
        def on_leave_preview(e):
            preview_btn.config(bg='#F39C12', relief='raised')
        
        def on_enter_save(e):
            save_btn.config(bg='#229954', relief='sunken')
        
        def on_leave_save(e):
            save_btn.config(bg='#27AE60', relief='raised')
        
        preview_btn.bind("<Enter>", on_enter_preview)
        preview_btn.bind("<Leave>", on_leave_preview)
        save_btn.bind("<Enter>", on_enter_save)
        save_btn.bind("<Leave>", on_leave_save)
        
        # Make sure window is visible
        review_window.focus_force()
        review_window.lift()

    def open_editable_preview(self, parent_window):
        """Open an editable preview window"""
        editable_window = tk.Toplevel(parent_window)
        editable_window.title("Edit Complaint Details - SPANDANA AI")
        editable_window.geometry("600x550")
        editable_window.configure(bg='#2C3E50')
        editable_window.resizable(True, True)
        
        # Center the window
        editable_window.transient(parent_window)
        editable_window.grab_set()
        
        # Use grid for layout
        editable_window.grid_rowconfigure(1, weight=1)
        editable_window.grid_columnconfigure(0, weight=1)
        
        # Header
        header_frame = tk.Frame(editable_window, bg='#34495E', height=60)
        header_frame.grid(row=0, column=0, sticky='ew', padx=0, pady=0)
        header_frame.grid_propagate(False)
        
        title_label = tk.Label(
            header_frame,
            text="Edit Your Complaint Details",
            font=('Arial', 16, 'bold'),
            fg='white',
            bg='#34495E'
        )
        title_label.pack(expand=True, pady=15)
        
        # Main content frame
        content_frame = tk.Frame(editable_window, bg='#2C3E50')
        content_frame.grid(row=1, column=0, sticky='nsew', padx=25, pady=20)
        content_frame.grid_columnconfigure(1, weight=1)
        
        # Create entry fields for editing
        self.edit_entries = {}
        row = 0
        
        for field, value in self.user_data.items():
            # Field label
            field_label = tk.Label(
                content_frame,
                text=f"{field}:",
                font=('Arial', 11, 'bold'),
                bg='#2C3E50',
                fg='#ECF0F1',
                anchor='w'
            )
            field_label.grid(row=row, column=0, sticky='w', padx=10, pady=12)
            
            # Entry field - use Text widget for Complaint Description for multi-line
            if field == "Complaint Description":
                entry = tk.Text(
                    content_frame,
                    font=('Arial', 11),
                    bg='white',
                    fg='#2C3E50',
                    width=40,
                    height=4,
                    wrap=tk.WORD
                )
                entry.insert('1.0', value)
            else:
                entry = tk.Entry(
                    content_frame,
                    font=('Arial', 11),
                    bg='white',
                    fg='#2C3E50',
                    width=40
                )
                entry.insert(0, value)
            
            entry.grid(row=row, column=1, sticky='ew', padx=10, pady=12)
            
            self.edit_entries[field] = entry
            row += 1
        
        # Buttons frame
        buttons_frame = tk.Frame(editable_window, bg='#2C3E50', height=80)
        buttons_frame.grid(row=2, column=0, sticky='ew', padx=20, pady=15)
        buttons_frame.grid_propagate(False)
        buttons_frame.grid_columnconfigure(0, weight=1)
        buttons_frame.grid_columnconfigure(1, weight=1)
        
        # Save Changes button
        save_changes_btn = tk.Button(
            buttons_frame,
            text="Save Changes",
            command=lambda: self.save_edited_data(editable_window, parent_window),
            font=('Arial', 11, 'bold'),
            bg='#27AE60',
            fg='white',
            padx=25,
            pady=12,
            relief='raised'
        )
        save_changes_btn.grid(row=0, column=1, padx=10, sticky='e')
        
        # Cancel button
        cancel_btn = tk.Button(
            buttons_frame,
            text="Cancel",
            command=editable_window.destroy,
            font=('Arial', 11),
            bg='#E74C3C',
            fg='white',
            padx=25,
            pady=12,
            relief='raised'
        )
        cancel_btn.grid(row=0, column=0, padx=10, sticky='w')

    def save_edited_data(self, edit_window, review_window):
        """Save the edited data back to user_data"""
        try:
            for field, entry in self.edit_entries.items():
                if field == "Complaint Description":
                    self.user_data[field] = entry.get('1.0', 'end-1c').strip()
                else:
                    self.user_data[field] = entry.get().strip()
            
            edit_window.destroy()
            review_window.destroy()
            
            # Refresh the review window with updated data
            self.show_form_data_review()
            
            messagebox.showinfo("Success", "Your changes have been saved successfully!")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save changes: {str(e)}")

    def save_complaint_data_and_show_ticket(self, review_window):
        """Save complaint data, then show the Ticket ID inside the review window and provide a Close button."""
        try:
            # Check required fields
            required_fields = ["Name", "Mobile Number", "Location", "Complaint Type", "Complaint Description"]
            for field in required_fields:
                if field not in self.user_data or not self.user_data[field].strip():
                    messagebox.showwarning("Incomplete Data", f"Please provide {field}.")
                    return
            
            # Check for exact duplicate complaint for the same user
            is_duplicate, existing_ticket_id = self.data_manager.find_duplicate_complaint(self.user_data)
            if is_duplicate:
                # Create the speech message
                speech_message = f"You have already registered a complaint of this type. Your existing ticket ID is {existing_ticket_id}. You cannot submit the same type of complaint again. Please check the status of your existing complaint or choose a different complaint type."
                
                # Start speaking the message in a separate thread
                threading.Thread(target=self.tts_engine.speak, args=(speech_message,), daemon=True).start()
                
                # Show messagebox at the same time
                messagebox.showwarning(
                    "Duplicate Complaint", 
                    f"❌ You have already registered a complaint of this type!\n\n"
                    f"Existing Ticket ID: {existing_ticket_id}\n"
                    f"Complaint Type: {self.user_data.get('Complaint Type', '')}\n\n"
                    f"You cannot submit the same type of complaint again. "
                    f"Please check the status of your existing complaint or choose a different complaint type."
                )
                
                # Close the review window
                review_window.destroy()
                # Reset the form for new complaint
                return
            
            # Generate ticket and save
            ticket = self.ticket_generator.create_ticket(self.user_data)
            success = self.data_manager.save_complaint_data(self.user_data, ticket)

            if not success:
                messagebox.showerror("Error", "Failed to save complaint data. Please try again.")
                return

            # Insert inline ticket info into review window
            try:
                info_frame = tk.Frame(review_window, bg='#2C3E50')
                info_frame.grid(row=3, column=0, sticky='ew', padx=20, pady=(5, 15))
                info_frame.grid_propagate(False)

                ticket_label = tk.Label(
                    info_frame,
                    text=f"✅ Your complaint has been submitted. Your Ticket ID is: {ticket['Ticket ID']}\nAssigned to: {ticket['Assigned Department']}",
                    font=('Arial', 12, 'bold'),
                    bg='#2C3E50',
                    fg='#2ECC71',
                    anchor='w',
                    justify=tk.LEFT
                )
                ticket_label.pack(side='left', padx=6, pady=8)

                # Disable buttons inside review window to prevent duplicate saves
                def disable_buttons(w):
                    for child in w.winfo_children():
                        try:
                            if isinstance(child, tk.Button):
                                child.config(state=tk.DISABLED)
                        except Exception:
                            pass
                        if hasattr(child, 'winfo_children'):
                            disable_buttons(child)

                disable_buttons(review_window)

                # Add Close button which closes the review window and resets the form
                close_btn = tk.Button(
                    info_frame,
                    text="Close",
                    command=lambda: (review_window.destroy(), self.reset_form()),
                    font=('Arial', 10, 'bold'),
                    bg='#2980B9',
                    fg='white',
                    padx=12,
                    pady=6
                )
                close_btn.pack(side='right', padx=6)
            except Exception:
                # If UI update failed, continue to show messagebox below
                pass

            # Show modal confirmation as well
            confirmation_msg = f"""✅ Your complaint has been successfully submitted!\n\nYour Ticket ID: {ticket['Ticket ID']}\nStatus: Open\nDepartment: {ticket['Assigned Department']}\nUrgency: {ticket['Urgency Level']}\n\nPlease note your Ticket ID for future reference."""
            messagebox.showinfo("Complaint Submitted", confirmation_msg)

            # Speak confirmation
            self.speak(f"Your complaint has been submitted successfully. Your ticket ID is {ticket['Ticket ID']} and it has been assigned to {ticket['Assigned Department']}.")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to save complaint: {str(e)}")

    def reset_form(self):
        """Reset the form for new complaint"""
        self.user_data = {}
        self.current_field_index = 0
        self.update_progress()
        self.update_buttons_state()
        
        # Clear chat display
        for child in self.scrollable_frame.winfo_children():
            child.destroy()
        
        # Restart conversation
        self.start_conversation()
    
    def toggle_voice_gender(self):
        """Toggle between male and female voice"""
        current_gender = self.tts_engine.voice_gender
        new_gender = 'male' if current_gender == 'female' else 'female'
        
        self.tts_engine.set_voice_gender(new_gender)
        
        # Update button text
        self.voice_toggle_btn.config(
            text="Switch to Male Voice" if new_gender == 'female' else "Switch to Female Voice"
        )
        
        # Test the new voice
        test_message = f"Hello, I am now using a {new_gender} voice."
        self.speak(test_message)
        
        messagebox.showinfo("Voice Changed", f"Voice changed to {new_gender}")
    
    def clear_current_response(self):
        """Clear the current response and allow user to re-answer"""
        if self.current_field_index > 0:
            current_field = list(self.fields.keys())[self.current_field_index - 1]
            
            if current_field in self.user_data:
                del self.user_data[current_field]
            
            self.current_field_index -= 1
            
            # Clear only the last question and answer from chat display
            children = self.scrollable_frame.winfo_children()
            if len(children) >= 2:
                # Remove last user message
                children[-1].destroy()
                # Remove last assistant message  
                children[-2].destroy()
            
            # Ask current question again
            current_question_field = list(self.fields.keys())[self.current_field_index]
            self.add_message("assistant", self.fields[current_question_field], False)
            self.speak(f"Please provide your answer again. {self.fields[current_question_field]}")
            
            self.update_progress()
            self.update_buttons_state()
            messagebox.showinfo("Response Cleared", "Your last response has been cleared. You can now provide a new answer.")
        else:
            messagebox.showinfo("No Response", "No responses have been recorded yet.")
    
    def update_buttons_state(self):
        """Update the state of buttons based on conversation progress"""
        if self.current_field_index == len(self.fields):
            # All questions completed - enable View Form Data button
            self.view_data_btn.config(state=tk.NORMAL, bg='#1E88E5')
            self.listen_btn.config(state=tk.DISABLED)
        else:
            # Conversation in progress
            self.view_data_btn.config(state=tk.DISABLED, bg='#666666')
            self.listen_btn.config(state=tk.NORMAL)
    
    def speak(self, text):
        """Universal speech function using available TTS engines"""
        print(f"Attempting to speak: {text}")
        self.tts_engine.speak(text)
    
    def add_message(self, sender, message, is_user=False):
        message_frame = tk.Frame(self.scrollable_frame, bg='#000000')
        message_frame.pack(fill=tk.X, padx=10, pady=5)
        
        if is_user:
            bg_color = '#333333'  # Dark gray for user
            align = 'e'
            sender_text = "You"
        else:
            bg_color = '#1a1a1a'  # Slightly lighter black for assistant
            align = 'w'
            sender_text = "Assistant"
        
        sender_label = tk.Label(
            message_frame,
            text=sender_text,
            font=('Arial', 9, 'bold'),
            bg='#000000',
            fg='white'
        )
        
        message_bubble = tk.Label(
            message_frame,
            text=message,
            font=('Arial', 11),
            bg=bg_color,
            fg='white',
            wraplength=500,
            justify=tk.LEFT,
            padx=15,
            pady=10,
            relief='flat',
            borderwidth=1
        )
        
        if align == 'w':
            sender_label.pack(anchor='w')
            message_bubble.pack(anchor='w')
        else:
            sender_label.pack(anchor='e')
            message_bubble.pack(anchor='e')
        
        self.chat_canvas.update_idletasks()
        self.chat_canvas.yview_moveto(1.0)
    
    def validate_response(self, field, response):
        """Validate user responses"""
        if not response or response.strip() == "":
            return False, "Please provide a response"
        
        if field == "Mobile Number":
            # Basic mobile number validation
            cleaned_response = response.replace(" ", "").replace("-", "").replace("+", "")
            if not cleaned_response.isdigit():
                return False, "Please enter a valid mobile number"
            if len(cleaned_response) != 10:
                return False, "Mobile number should be 10 digits"
        
        return True, "Valid response"
    
    def listen(self):
        try:
            with sr.Microphone() as source:
                self.status_label.config(text="Listening...")
                self.root.update()
                
                print("Adjusting for ambient noise...")
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                print("Listening...")
                audio = self.recognizer.listen(source, timeout=10, phrase_time_limit=15)
            
            self.status_label.config(text="Processing...")
            self.root.update()
            
            response = self.recognizer.recognize_google(audio)
            print(f"Speech recognition: {response}")
            
            self.status_label.config(text="Ready to listen")
            return response
        
        except sr.UnknownValueError:
            error_msg = "Sorry, I could not understand. Please try again."
            self.status_label.config(text=error_msg)
            print("Speech recognition could not understand audio")
            return None
        except sr.RequestError as e:
            error_msg = f"Speech service error: {e}"
            self.status_label.config(text=error_msg)
            print(f"Could not request results from speech recognition service; {e}")
            return None
        except sr.WaitTimeoutError:
            error_msg = "Listening timeout"
            self.status_label.config(text=error_msg)
            print("Listening timeout")
            return None
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            self.status_label.config(text=error_msg)
            print(f"Unexpected error: {e}")
            return None
    
    def start_listening(self):
        self.listen_btn.config(state=tk.DISABLED, text="Listening...")
        thread = threading.Thread(target=self.process_listening)
        thread.daemon = True
        thread.start()
    
    def process_listening(self):
        response = self.listen()
        self.root.after(0, lambda: self.listen_btn.config(state=tk.NORMAL, text="Start Listening"))
        
        if response:
            self.root.after(0, self.add_message, "user", response, True)
            current_field = list(self.fields.keys())[self.current_field_index]
            is_valid, validation_msg = self.validate_response(current_field, response)
            
            if is_valid:
                self.user_data[current_field] = response
                self.current_field_index += 1
                self.root.after(0, self.update_progress)
                self.root.after(0, self.update_buttons_state)
                
                if self.current_field_index < len(self.fields):
                    self.root.after(0, self.ask_next_question)
                else:
                    self.root.after(0, self.conversation_complete)
            else:
                error_prompt = f"{validation_msg}. {self.fields[current_field]}"
                self.root.after(0, self.add_message, "assistant", error_prompt, False)
                self.root.after(0, lambda: self.speak(error_prompt))
        else:
            self.root.after(0, self.ask_current_question_again)
    
    def ask_next_question(self):
        current_field = list(self.fields.keys())[self.current_field_index]
        prompt = self.fields[current_field]
        self.add_message("assistant", prompt, False)
        self.speak(prompt)
    
    def ask_current_question_again(self):
        current_field = list(self.fields.keys())[self.current_field_index]
        prompt = f"Sorry, I didn't catch that. {self.fields[current_field]}"
        self.add_message("assistant", prompt, False)
        self.speak(prompt)
    
    def start_conversation(self):
        welcome_msg = "Hello! I am your complaint assistant chatbot. I'll ask you a few questions to file your complaint."
        self.add_message("assistant", welcome_msg, False)
        self.speak(welcome_msg)
        self.root.after(2000, self.ask_next_question)
    
    def conversation_complete(self):
        completion_msg = "Thank you! Your complaint has been recorded. Click 'View Form Data' to review and submit your complaint."
        self.add_message("assistant", completion_msg, False)
        self.speak(completion_msg)
        self.update_buttons_state()
    
    def update_progress(self):
        progress_value = (self.current_field_index / len(self.fields)) * 100
        self.progress['value'] = progress_value
        self.progress_label.config(text=f"Progress: {self.current_field_index}/{len(self.fields)} completed")

def main():
    try:    
        root = tk.Tk()
        app = VoiceChatbotGUI(root)
        root.mainloop()
    except Exception as e:
        print(f"Application error: {e}")
        messagebox.showerror("Error", f"Application error: {e}")

if __name__ == "__main__":
    main()