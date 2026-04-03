import os
import json
import re
import zipfile
import pandas as pd
from pathlib import Path
import google.generativeai as genai
from dotenv import load_dotenv

# --- LOAD ENV ---
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def resolve_root_dir() -> Path:
    root_env = os.getenv("ROOT_PATH", "").strip()
    if not root_env or root_env in {".", "./"}:
        return PROJECT_ROOT

    env_path = Path(root_env)
    if env_path.is_absolute():
        return env_path

    # Hindari duplikasi folder jika ROOT_PATH sama dengan nama folder project.
    if env_path.name == PROJECT_ROOT.name:
        return PROJECT_ROOT

    return (PROJECT_ROOT / env_path).resolve()


# --- SETUP PATH ---
ROOT_DIR = resolve_root_dir()
CURRENT_MEETING = os.getenv("CURRENT_MEETING", "pertemuan_4")
ASSIGNMENT_TITLE = os.getenv(
    "ASSIGNMENT_TITLE", "Studi Kasus Pertemuan 4: Implementasi Rekursif"
)
SPECIAL_RULE = os.getenv("SPECIAL_RULE", "")
STUDENT_ID_REGEX = os.getenv("STUDENT_ID_REGEX", r"^\d{14}_[a-zA-Z0-9]+$")
ALLOWED_EXTENSIONS = tuple(
    ext.strip().lower()
    for ext in os.getenv("ALLOWED_EXTENSIONS", ".c,.cpp,.py,.java").split(",")
    if ext.strip()
)

SUB_DIR = ROOT_DIR / "submissions" / CURRENT_MEETING
EXTRACT_DIR = ROOT_DIR / "extracted" / CURRENT_MEETING
RESULT_DIR = ROOT_DIR / "results"
EXCEL_PATH = RESULT_DIR / f"{CURRENT_MEETING}_results.xlsx"

# --- CONFIG AI ---
genai.configure(api_key=os.getenv("GEMINI_API_KEY", "YOUR_API_KEY"))
model = genai.GenerativeModel(os.getenv("AI_MODEL", "gemini-1.5-flash"))


def initialize_folders():
    required_dirs = [
        ROOT_DIR / "src",
        ROOT_DIR / "logs",
        ROOT_DIR / "submissions",
        ROOT_DIR / "extracted",
        ROOT_DIR / "results",
        SUB_DIR,
        EXTRACT_DIR,
        RESULT_DIR,
    ]
    for directory in required_dirs:
        directory.mkdir(parents=True, exist_ok=True)

def validate_and_extract():
    """Validasi nama file zip dan ekstrak ke folder valid/invalid tanpa duplikasi."""
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    invalid_dir = EXTRACT_DIR / "INVALID_FORMAT"
    invalid_dir.mkdir(parents=True, exist_ok=True)

    try:
        format_pattern = re.compile(STUDENT_ID_REGEX)
    except re.error:
        # Fallback aman jika regex di .env tidak valid.
        format_pattern = re.compile(r"^\d{14}_[a-zA-Z0-9]+$")

    for zip_file in SUB_DIR.glob("*.zip"):
        filename = zip_file.stem
        is_valid = bool(format_pattern.fullmatch(filename))

        target_path = EXTRACT_DIR / filename if is_valid else invalid_dir / filename

        if target_path.exists():
            print(f"[-] Skip ekstrak {zip_file.name} (folder tujuan sudah ada)")
            continue

        with zipfile.ZipFile(zip_file, "r") as zip_ref:
            zip_ref.extractall(target_path)

        if not is_valid:
            print(f"[!] Format salah: {zip_file.name} -> {target_path}")

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

def grade_assignments():
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
            if file.suffix.lower() in ALLOWED_EXTENSIONS:
                with open(file, 'r', errors='ignore') as f:
                    code_bundle += f"\n\n--- FILE: {file.name} ---\n{f.read()}"

        if not code_bundle.strip():
            print(f"[!] Tidak ada source code yang sesuai ekstensi di {student_folder.name}")
            continue

        # PROMPT UNIVERSAL
        prompt = f"""
        Anda adalah asisten penilai teknis praktikum pemrograman.
        INSTRUKSI UTAMA (WAJIB DIPATUHI): {SPECIAL_RULE}

        Tugas: {ASSIGNMENT_TITLE}
        Pertemuan: {CURRENT_MEETING}

        Identitas Mahasiswa: {student_folder.name}
        Source Code:
        {code_bundle}

        Berikan penilaian teknis dalam format JSON berikut:
        {{
            "Kebenaran_Logika": "penjelasan singkat",
            "Kualitas_Kode": "penjelasan singkat",
            "Aturan_Khusus": "Evaluasi kepatuhan terhadap instruksi utama: {SPECIAL_RULE}",
            "Feedback_Edukatif": "poin perbaikan spesifik untuk mahasiswa",
            "Skor_Akhir": 85
        }}
        Pastikan respons hanya JSON valid tanpa markdown.
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


def run_grader(judul_tugas, rule_khusus):
    # Kompatibilitas: parameter lama tetap diterima, namun grading memakai konfigurasi .env
    _ = judul_tugas, rule_khusus
    grade_assignments()

if __name__ == "__main__":
    initialize_folders()
    grade_assignments()