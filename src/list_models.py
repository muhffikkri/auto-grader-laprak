import os
from dotenv import load_dotenv
from pathlib import Path
import google.generativeai as genai

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def safe_get(obj, attr_name, default="N/A"):
    value = getattr(obj, attr_name, None)
    if value is None:
        return default
    return value


def format_limit(value):
    if value in (None, "N/A"):
        return "N/A"
    return str(value)


def main():
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("GEMINI_API_KEY belum di-set pada file .env")
        return

    genai.configure(api_key=api_key)

    print("Daftar model Gemini yang mendukung generateContent")
    print("Catatan: limit Requests/Minute dan Requests/Day tidak selalu tersedia dari endpoint list_models.")
    print("-" * 140)
    print(
        f"{'Model':45} {'InputToken/Prompt':18} {'OutputToken':12} {'Req/Minute':12} {'Req/Day':10} {'Token/Minute':14}"
    )
    print("-" * 140)

    rows = []
    for model in genai.list_models():
        methods = safe_get(model, "supported_generation_methods", [])
        if "generateContent" not in methods:
            continue

        rows.append(
            {
                "model": safe_get(model, "name", "unknown"),
                "input_token_limit": safe_get(model, "input_token_limit"),
                "output_token_limit": safe_get(model, "output_token_limit"),
                "requests_per_minute": safe_get(model, "requests_per_minute"),
                "requests_per_day": safe_get(model, "requests_per_day"),
                "tokens_per_minute": safe_get(model, "tokens_per_minute"),
            }
        )

    if not rows:
        print("Tidak ada model yang bisa ditampilkan. Cek API key atau akses akun Anda.")
        return

    for row in sorted(rows, key=lambda x: x["model"]):
        print(
            f"{row['model'][:45]:45} "
            f"{format_limit(row['input_token_limit']):18} "
            f"{format_limit(row['output_token_limit']):12} "
            f"{format_limit(row['requests_per_minute']):12} "
            f"{format_limit(row['requests_per_day']):10} "
            f"{format_limit(row['tokens_per_minute']):14}"
        )


if __name__ == "__main__":
    main()
