import os
import zipfile
import google.generativeai as genai
import pandas as pd

# 1. Konfigurasi AI
genai.configure(api_key="YOUR_GEMINI_API_KEY")
model = genai.GenerativeModel('gemini-1.5-flash') # Versi cepat & murah

def grade_code(student_name, code_contents):
    """
    Mengirimkan 4 kode praktikan ke AI untuk dinilai
    """
    prompt = f"""
    Anda adalah asisten Lab Pemrograman. Tugas Anda menilai 4 file kode dari praktikan bernama {student_name}.
    
    Berikut adalah kodenya:
    {code_contents}
    
    Kriteria Penilaian:
    1. Logika (0-50): Apakah kode berjalan sesuai algoritma?
    2. Clean Code (0-30): Penamaan variabel dan kerapihan.
    3. Komentar (0-20): Penjelasan fungsi.
    
    Format Output (HARUS JSON):
    {{
        "skor_total": ...,
        "feedback": "...",
        "poin_perbaikan": "..."
    }}
    """
    response = model.generate_content(prompt)
    return response.text

def main():
    submission_dir = 'submissions'
    extract_dir = 'extracted'
    results = []

    # 2. Loop semua file zip di folder submissions
    for zip_name in os.listdir(submission_dir):
        if zip_name.endswith('.zip'):
            student_id = zip_name.replace('.zip', '')
            zip_path = os.path.join(submission_dir, zip_name)
            student_extract_path = os.path.join(extract_dir, student_id)

            # Ekstrak file
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(student_extract_path)

            # 3. Baca 4 file source code di dalamnya
            all_code_text = ""
            for root, dirs, files in os.walk(student_extract_path):
                for file in files:
                    if file.endswith(('.py', '.c', '.java', '.cpp')): # Sesuaikan bahasa
                        with open(os.path.join(root, file), 'r', errors='ignore') as f:
                            all_code_text += f"\n--- File: {file} ---\n"
                            all_code_text += f.read()

            # 4. Kirim ke AI untuk dinilai
            print(f"Sedang menilai {student_id}...")
            evaluation = grade_code(student_id, all_code_text)
            
            # Simpan hasil sementara
            results.append({
                "NIM_Nama": student_id,
                "Hasil_AI": evaluation
            })

    # 5. Simpan hasil ke Excel/CSV atau kirim ke Google Sheets
    df = pd.DataFrame(results)
    df.to_csv('hasil_penilaian.csv', index=False)
    print("Selesai! Cek file hasil_penilaian.csv")

if __name__ == "__main__":
    main()