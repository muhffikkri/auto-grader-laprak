import os
import json
import re
import zipfile
import logging
import time
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
STUDENT_ID_REGEX = os.getenv(
    "STUDENT_ID_REGEX",
    r"^\d{14}_\d+\s-\s[a-zA-Z][a-zA-Z\s'.-]*$",
)
SUBMISSION_SUBFOLDER = os.getenv("SUBMISSION_SUBFOLDER", "submissions")
EXTRACTED_SUBFOLDER = os.getenv("EXTRACTED_SUBFOLDER", "extracted")
RESULTS_SUBFOLDER = os.getenv("RESULTS_SUBFOLDER", "results")
LOGS_SUBFOLDER = os.getenv("LOGS_SUBFOLDER", "logs")
API_DELAY_SECONDS = float(os.getenv("API_DELAY_SECONDS", "2"))
ALLOWED_EXTENSIONS = tuple(
    ext.strip().lower()
    for ext in os.getenv("ALLOWED_EXTENSIONS", ".c,.cpp,.py,.java").split(",")
    if ext.strip()
)

SUB_DIR = ROOT_DIR / SUBMISSION_SUBFOLDER / CURRENT_MEETING
EXTRACT_DIR = ROOT_DIR / EXTRACTED_SUBFOLDER / CURRENT_MEETING
RESULT_DIR = ROOT_DIR / RESULTS_SUBFOLDER
EXCEL_PATH = RESULT_DIR / f"{CURRENT_MEETING}_results.xlsx"
LOG_DIR = ROOT_DIR / LOGS_SUBFOLDER
LOG_PATH = LOG_DIR / f"{CURRENT_MEETING}.log"
CHECKPOINT_PATH = LOG_DIR / f"{CURRENT_MEETING}_last_student.txt"

RESULT_COLUMNS = [
    "NIM_Nama",
    "Kebenaran_Logika",
    "Kualitas_Kode",
    "Aturan_Khusus",
    "Feedback_Edukatif",
    "Skor_Akhir",
]

# --- CONFIG AI ---
genai.configure(api_key=os.getenv("GEMINI_API_KEY", "YOUR_API_KEY"))
model = genai.GenerativeModel(os.getenv("AI_MODEL", "gemini-1.5-flash"))


def setup_logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("auto_grader")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


logger = setup_logger()


def write_checkpoint(student_name: str, status: str):
    CHECKPOINT_PATH.write_text(
        f"status={status}\nstudent={student_name}\n",
        encoding="utf-8",
    )


def initialize_folders():
    required_dirs = [
        ROOT_DIR / SUBMISSION_SUBFOLDER,
        ROOT_DIR / EXTRACTED_SUBFOLDER,
        ROOT_DIR / RESULTS_SUBFOLDER,
        ROOT_DIR / LOGS_SUBFOLDER,
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
        format_pattern = re.compile(r"^\d{14}_\d+\s-\s[a-zA-Z][a-zA-Z\s'.-]*$")

    for zip_file in SUB_DIR.glob("*.zip"):
        filename = zip_file.stem.strip()
        is_valid = bool(format_pattern.fullmatch(filename))

        target_path = EXTRACT_DIR / filename if is_valid else invalid_dir / filename

        if target_path.exists():
            print(f"[-] Skip ekstrak {zip_file.name} (folder tujuan sudah ada)")
            continue

        with zipfile.ZipFile(zip_file, "r") as zip_ref:
            zip_ref.extractall(target_path)

        if not is_valid:
            print(f"[!] Format salah: {zip_file.name} -> {target_path}")

def load_processed_students():
    """Ambil daftar mahasiswa yang sudah dinilai dari Excel hasil sebelumnya."""
    if not EXCEL_PATH.exists():
        return set()

    df_existing = pd.read_excel(EXCEL_PATH, engine="openpyxl")
    if "NIM_Nama" not in df_existing.columns:
        return set()

    # Normalisasi kolom agar konsisten lintas sesi.
    for col in RESULT_COLUMNS:
        if col not in df_existing.columns:
            df_existing[col] = ""

    df_existing = df_existing[RESULT_COLUMNS]
    df_existing.to_excel(EXCEL_PATH, index=False, engine="openpyxl")
    return set(df_existing["NIM_Nama"].astype(str).tolist())


def normalize_result_row(new_data):
    row = {col: new_data.get(col, "") for col in RESULT_COLUMNS}
    try:
        row["Skor_Akhir"] = int(row["Skor_Akhir"])
    except (TypeError, ValueError):
        row["Skor_Akhir"] = 0
    return row


def save_incremental(new_data):
    """Simpan hasil per mahasiswa langsung ke file Excel (incremental saving)."""
    normalized_row = normalize_result_row(new_data)
    df_new = pd.DataFrame([normalized_row], columns=RESULT_COLUMNS)

    if EXCEL_PATH.exists():
        df_old = pd.read_excel(EXCEL_PATH, engine="openpyxl")
        for col in RESULT_COLUMNS:
            if col not in df_old.columns:
                df_old[col] = ""
        df_old = df_old[RESULT_COLUMNS]
        df_final = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_final = df_new

    df_final = df_final[RESULT_COLUMNS]
    df_final.to_excel(EXCEL_PATH, index=False, engine="openpyxl")


def sanitize_ai_json(raw_text):
    """Ekstrak objek JSON dari output AI yang mungkin dibungkus markdown atau teks lain."""
    cleaned = re.sub(r"```json|```", "", raw_text or "", flags=re.IGNORECASE).strip()
    candidates = re.findall(r"\{[\s\S]*?\}", cleaned)

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    # Coba parse keseluruhan jika kandidat regex tidak valid.
    return json.loads(cleaned)


def build_empty_result(student_name):
    return {
        "NIM_Nama": student_name,
        "Kebenaran_Logika": "Tidak ada file kode yang valid ditemukan",
        "Kualitas_Kode": "Tidak ada file kode yang valid ditemukan",
        "Aturan_Khusus": f"Tidak dapat dievaluasi karena tidak ada kode. Aturan utama: {SPECIAL_RULE}",
        "Feedback_Edukatif": "Tidak ada file kode yang valid ditemukan",
        "Skor_Akhir": 0,
    }

def grade_assignments():
    validate_and_extract()
    logger.info("Mulai proses grading untuk %s", CURRENT_MEETING)

    # Checkpoint: Mahasiswa yang sudah ada di excel tidak akan diproses ulang
    processed_students = load_processed_students()

    for student_folder in EXTRACT_DIR.iterdir():
        if not student_folder.is_dir() or student_folder.name == "INVALID_FORMAT":
            continue
        
        if student_folder.name in processed_students:
            print(f"[-] Skip {student_folder.name} (Sudah dinilai)")
            logger.info("Skip %s (sudah dinilai)", student_folder.name)
            continue

        print(f"[*] Menganalisis {student_folder.name}...")
        logger.info("Mulai koreksi %s", student_folder.name)
        write_checkpoint(student_folder.name, "IN_PROGRESS")

        # Gabungkan semua source code mahasiswa
        code_bundle = ""
        for file in student_folder.rglob("*"):
            if file.suffix.lower() in ALLOWED_EXTENSIONS:
                with open(file, 'r', encoding='utf-8', errors='ignore') as f:
                    code_bundle += f"\n\n--- FILE: {file.name} ---\n{f.read()}"

        if not code_bundle.strip():
            print(f"[!] Tidak ada source code yang sesuai ekstensi di {student_folder.name}")
            logger.warning("Tidak ada source code valid untuk %s", student_folder.name)
            save_incremental(build_empty_result(student_folder.name))
            processed_students.add(student_folder.name)
            write_checkpoint(student_folder.name, "NO_SOURCE")
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
            res_json = sanitize_ai_json(response.text)
            
            res_json['NIM_Nama'] = student_folder.name
            
            save_incremental(res_json)
            processed_students.add(student_folder.name)
            print(f"[OK] {student_folder.name} selesai.")
            logger.info("Selesai koreksi %s", student_folder.name)
            write_checkpoint(student_folder.name, "COMPLETED")
            time.sleep(API_DELAY_SECONDS)
            
        except json.JSONDecodeError as e:
            print(f"[!] Gagal parse JSON untuk {student_folder.name}: {e}")
            logger.exception("Gagal parse JSON untuk %s", student_folder.name)
            write_checkpoint(student_folder.name, "FAILED_JSON")
            time.sleep(API_DELAY_SECONDS)

        except Exception as e:
            print(f"[!] Gagal memproses {student_folder.name}: {e}")
            logger.exception("Gagal memproses %s", student_folder.name)
            write_checkpoint(student_folder.name, "FAILED")
            time.sleep(API_DELAY_SECONDS)


def run_grader(judul_tugas, rule_khusus):
    # Kompatibilitas: parameter lama tetap diterima, namun grading memakai konfigurasi .env
    _ = judul_tugas, rule_khusus
    grade_assignments()

if __name__ == "__main__":
    try:
        initialize_folders()
        logger.info("Auto-grader dijalankan")
        grade_assignments()
        logger.info("Auto-grader selesai")
    except Exception:
        logger.exception("Proses berhenti karena error fatal")
        raise