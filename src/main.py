import os
import json
import re
import zipfile
import pandas as pd
from pathlib import Path
import google.generativeai as genai

# --- SETUP PATH ---
ROOT_DIR = Path("auto-grader-laprak")
# Folder ini akan berubah sesuai pertemuan yang sedang dikoreksi
CURRENT_MEETING = "pertemuan_4" 

SUB_DIR = ROOT_DIR / "submissions" / CURRENT_MEETING
EXTRACT_DIR = ROOT_DIR / "extracted" / CURRENT_MEETING
RESULT_DIR = ROOT_DIR / "results"
EXCEL_PATH = RESULT_DIR / f"{CURRENT_MEETING}_results.xlsx"

# --- CONFIG AI ---
genai.configure(api_key="YOUR_API_KEY")
model = genai.GenerativeModel('gemini-1.5-flash')

def validate_and_extract():
    """Poin A: Memisahkan file yang salah format ke folder khusus"""
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    INVALID_DIR = EXTRACT_DIR / "INVALID_FORMAT"
    INVALID_DIR.mkdir(exist_ok=True)
    
    # Format: 14 digit NIM + Nama
    format_pattern = re.compile(r'^\d{14}_[a-zA-Z0-9]+')

    for zip_file in SUB_DIR.glob("*.zip"):
        student_id = zip_file.stem
        is_valid = bool(format_pattern.match(student_id))
        
        target_path = EXTRACT_DIR / student_id if is_valid else INVALID_DIR / student_id
        
        if not target_path.exists():
            with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                zip_ref.extractall(target_path)
            if not is_valid:
                print(f"[!] Format Salah: {student_id} (Pindah ke INVALID_FORMAT)")

def save_incremental(new_data):
    """Poin B: Simpan setiap satu mahasiswa selesai agar data aman"""
    if EXCEL_PATH.exists():
        df_old = pd.read_excel(EXCEL_PATH)
        df_new = pd.DataFrame([new_data])
        # Gunakan concat untuk menambah baris di bawah
        df_final = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_final = pd.DataFrame([new_data])
    
    df_final.to_excel(EXCEL_PATH, index=False)

def run_grader(judul_tugas, rule_khusus):
    validate_and_extract()
    
    # Checkpoint: Mahasiswa yang sudah ada di excel tidak akan diproses ulang
    processed_students = []
    if EXCEL_PATH.exists():
        processed_students = pd.read_excel(EXCEL_PATH)['NIM_Nama'].astype(str).tolist()

    for student_folder in EXTRACT_DIR.iterdir():
        if not student_folder.is_dir() or student_folder.name == "INVALID_FORMAT":
            continue
        
        if student_folder.name in processed_students:
            print(f"[-] Skip {student_folder.name} (Sudah dinilai)")
            continue

        print(f"[*] Menganalisis {student_folder.name}...")
        
        # Gabungkan semua source code mahasiswa
        code_bundle = ""
        for file in student_folder.rglob("*"):
            if file.suffix in ['.c', '.cpp', '.py', '.java']:
                with open(file, 'r', errors='ignore') as f:
                    code_bundle += f"\n\n--- FILE: {file.name} ---\n{f.read()}"

        # PROMPT UNIVERSAL
        prompt = f"""
        Tugas: {judul_tugas}
        ATURAN KHUSUS (Prioritas): {rule_khusus}
        
        Identitas Mahasiswa: {student_folder.name}
        Source Code:
        {code_bundle}
        
        Berikan penilaian teknis dalam format JSON berikut:
        {{
            "Kebenaran_Logika": "penjelasan singkat",
            "Kualitas_Kode": "penjelasan singkat",
            "Aturan_Khusus": "Evaluasi apakah mahasiswa mengikuti: {rule_khusus}",
            "Feedback_Edukatif": "poin perbaikan spesifik untuk mahasiswa",
            "Skor_Akhir": 85
        }}
        """
        
        try:
            response = model.generate_content(prompt)
            # Bersihkan karakter non-JSON jika AI memberi markdown
            clean_json = re.sub(r'```json|```', '', response.text).strip()
            res_json = json.loads(clean_json)
            
            res_json['NIM_Nama'] = student_folder.name
            
            save_incremental(res_json)
            print(f"[OK] {student_folder.name} selesai.")
            
        except Exception as e:
            print(f"[!] Gagal memproses {student_folder.name}: {e}")

if __name__ == "__main__":
    # Inisialisasi folder
    for d in [SUB_DIR, EXTRACT_DIR, RESULT_DIR, ROOT_DIR / "logs"]:
        d.mkdir(parents=True, exist_ok=True)

    # --- INPUT USER ---
    tugas = "Studi Kasus Pertemuan 4: Implementasi Rekursif"
    # Contoh Rule Khusus:
    aturan = "Mahasiswa WAJIB menggunakan fungsi rekursif untuk menyelesaikan masalah. Jika menggunakan loop biasa, kolom Aturan_Khusus diberi peringatan keras dan skor dikurangi."
    
    run_grader(tugas, aturan)