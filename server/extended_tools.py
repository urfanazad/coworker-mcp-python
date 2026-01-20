import os
import json
import subprocess
import httpx
from bs4 import BeautifulSoup
import xlsxwriter
from docx import Document
from fpdf import FPDF
from typing import List, Dict, Any
import time

# Audio imports
try:
    import sounddevice as sd
    from scipy.io import wavfile
    import speech_recognition as sr
    import numpy as np
    AUDIO_SUPPORT = True
except ImportError:
    AUDIO_SUPPORT = False

def browse_web(url: str) -> str:
    """Fetch and return text content from a URL."""
    try:
        response = httpx.get(url, follow_redirects=True, timeout=10.0)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        for script_or_style in soup(["script", "style"]):
            script_or_style.decompose()
            
        text = soup.get_text(separator='\n')
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        return text[:10000]
    except Exception as e:
        return f"Error browsing {url}: {str(e)}"

def create_excel(path: str, data: List[Dict[str, Any]]) -> str:
    """Create an Excel file using xlsxwriter."""
    try:
        workbook = xlsxwriter.Workbook(path)
        worksheet = workbook.add_worksheet()
        
        if not data:
            workbook.close()
            return f"Created empty Excel file at {path}"
            
        headers = list(data[0].keys())
        for col, header in enumerate(headers):
            worksheet.write(0, col, header)
            
        for row_idx, row_data in enumerate(data, start=1):
            for col_idx, header in enumerate(headers):
                worksheet.write(row_idx, col_idx, str(row_data.get(header, "")))
                
        workbook.close()
        return f"Successfully created Excel file at {path}"
    except Exception as e:
        return f"Error creating Excel: {str(e)}"

def create_word(path: str, content: str) -> str:
    """Create a Word document."""
    try:
        doc = Document()
        doc.add_paragraph(content)
        doc.save(path)
        return f"Successfully created Word file at {path}"
    except Exception as e:
        return f"Error creating Word file: {str(e)}"

def create_pdf(path: str, content: str) -> str:
    """Create a PDF document."""
    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("helvetica", size=12)
        for line in content.split('\n'):
            pdf.multi_cell(0, 10, txt=line)
        pdf.output(path)
        return f"Successfully created PDF file at {path}"
    except Exception as e:
        return f"Error creating PDF: {str(e)}"

def execute_python_code(code: str) -> str:
    """Execute Python code locally and return stdout."""
    try:
        temp_file = "temp_exec.py"
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(code)
        
        py_exec = os.path.join(os.getcwd(), "venv", "Scripts", "python.exe")
        if not os.path.exists(py_exec):
            py_exec = "python"

        result = subprocess.run(
            [py_exec, temp_file],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if os.path.exists(temp_file):
            os.remove(temp_file)
        
        output = result.stdout
        if result.stderr:
            output += f"\nErrors:\n{result.stderr}"
        return output if output else "Code executed successfully (no output)."
    except subprocess.TimeoutExpired:
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return "Error: Execution timed out (30s limit)"
    except Exception as e:
        return f"Error executing code: {str(e)}"

def search_audit_logs(query: str, workspace_root: str) -> str:
    audit_path = os.path.join(workspace_root, ".coworker_audit.jsonl")
    if not os.path.exists(audit_path):
        return "No audit logs found in this workspace."
    
    matches = []
    try:
        with open(audit_path, "r", encoding="utf-8") as f:
            for line in f:
                if query.lower() in line.lower():
                    matches.append(line.strip())
        
        if not matches:
            return f"No matches found for '{query}' in audit logs."
        
        return "\n".join(matches[-20:])
    except Exception as e:
        return f"Error searching logs: {str(e)}"

def search_google_drive(query: str) -> str:
    if not os.path.exists("credentials.json"):
        return ("Google Drive tool requires a 'credentials.json' file in the project root. "
                "Please download it from Google Cloud Console (OAuth 2.0 Client ID) and place it here.")
    return "Google Drive search logic initialized, but authentication is required. Run 'python auth_gdrive.py' first."

# --- MEETING ASSISTANT TOOLS ---

def record_and_transcribe(duration: int = 10) -> str:
    """Record audio and transcribe it in one go."""
    if not AUDIO_SUPPORT:
        return "Audio support is not available. Please install sounddevice, scipy, and SpeechRecognition."

    fs = 44100  # Sample rate
    temp_wav = "meeting_temp.wav"
    
    try:
        # 1. Record
        recording = sd.rec(int(duration * fs), samplerate=fs, channels=1)
        # print("Recording...")
        sd.wait()  # Wait until recording is finished
        wavfile.write(temp_wav, fs, recording)
        
        # 2. Transcribe
        r = sr.Recognizer()
        with sr.AudioFile(temp_wav) as source:
            audio_data = r.record(source)
            # Use Google's free recognizer
            text = r.recognize_google(audio_data)
        
        if os.path.exists(temp_wav):
            os.remove(temp_wav)
            
        return f"Transcript: {text}"
    except Exception as e:
        if os.path.exists(temp_wav):
            os.remove(temp_wav)
        return f"Meeting Assistant Error: {str(e)}"

def list_audio_devices() -> str:
    """List available audio input devices."""
    if not AUDIO_SUPPORT:
        return "Audio support not enabled."
    try:
        devices = sd.query_devices()
        return str(devices)
    except Exception as e:
        return str(e)
