# Spandana AI — Complaint Registration (Tkinter)

This repository contains two main Python GUI scripts you can run locally on Windows:

- `complaint_app.py` — a focused Tkinter / optional customtkinter app that implements a single "View Form Data" button, a review window with Preview and Save Data, automatic Ticket ID generation, and unified CSV storage (`app_data.csv`).
- `chat_bot.py` — the existing voice-enabled chatbot GUI (speech recognition + TTS) that collects complaint inputs and can generate tickets and save data.

This README explains how to create a Python virtual environment, install dependencies, and run either app.

---

## Requirements

- Python 3.8+ (3.10/3.11 recommended)
- Windows (tested in this environment)

Recommended packages (listed in `requirements.txt`) include:

- speechrecognition
- pyaudio (for microphone input) — on Windows you may prefer installing via `pipwin`
- pyttsx3 (TTS)
- pywin32 (SAPI on Windows)
- gTTS and pygame (optional Google TTS playback)
- customtkinter (optional for a modern UI style — app falls back to standard tkinter if not installed)

Note: `complaint_app.py` will run with the standard library `tkinter` alone. `chat_bot.py` uses microphone and TTS — you will need audio drivers and optionally `pyaudio`.

---

## Setup (PowerShell)

Run these commands in PowerShell from the project folder `D:\spandana_env`:

```powershell
python -m venv .venv

# activate virtual environment
.\.venv\Scripts\Activate.ps1

# upgrade pip
python -m pip install --upgrade pip

# install dependencies
pip install -r requirements.txt
```

If you have trouble installing `pyaudio` on Windows, install `pipwin` and use it to install a prebuilt wheel:

```powershell
pip install pipwin
pipwin install pyaudio
```

Or download a matching wheel from a trusted source and `pip install` it.

---

## Run the GUI apps

1) Run the complaint form app (recommended for reviewing the single-button flow):

```powershell
# with the virtualenv active
python complaint_app.py
```

This opens a modern Tkinter window (customtkinter used if installed). Fill all fields, then click the single "View Form Data" button. In the review window use "Preview" to edit (fields will become editable) and "Save Data" to append the data to `app_data.csv`. The app will automatically generate a Ticket ID (e.g. `TCKT1001`) and set `Status` to `Open`, `Ticket Alive` to `Yes`.

2) Run the voice chatbot (microphone + TTS):

```powershell
python chat_bot.py
```

The chatbot will guide you with speech/audio to collect Name, Mobile Number, Location, Complaint Type and Description. After completing all fields you can use the View Form Data / Generate Ticket / Save Data controls in the chat UI. `chat_bot.py` writes ticket-level CSVs (`tickets_data.csv`, `complaints_data.csv`) in the same folder.

---

## CSV storage

- `app_data.csv` — used by `complaint_app.py` (created automatically if missing). It contains columns:
  `Username, Password, Name, Mobile Number, Location, Complaint Type, Complaint Description, Ticket ID, Status, Ticket Alive`

- `complaints_data.csv` and `tickets_data.csv` — used by `chat_bot.py` / TicketGenerator. These are appended to and not overwritten.

If you prefer a single unified CSV for everything, you can remove or consolidate the other CSV writers and direct them to `app_data.csv`.

---

## Notes and troubleshooting

- If `customtkinter` is not installed the app falls back to plain `tkinter` and should still look correct.
- Microphone issues: ensure Windows microphone privacy settings allow apps to access the mic and drivers are installed. `pyaudio` is required for some mic backends.
- TTS engines: `chat_bot.py` attempts to use Windows SAPI, `pyttsx3`, `gTTS`, and `espeak`. Availability depends on your system and installed packages.

If you want, I can also:
- Add a consolidated `requirements.txt` to pin versions.
- Modify `chat_bot.py` to write to the same `app_data.csv` file for a true single-CSV approach.

---

If you want step-by-step hand-holding I can run a few verification steps or generate the `requirements.txt` with pinned versions next.

