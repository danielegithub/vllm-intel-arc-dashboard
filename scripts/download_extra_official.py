#!/usr/bin/env python3
import os
from pathlib import Path
from huggingface_hub import snapshot_download

MODELS_DIR = Path.home() / "my_models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

DOWNLOAD_LIST = [
    {
        "repo_id": "google/gemma-2-2b-it",
        "folder": "gemma-2-2b-it",
        "desc": "Google Gemma 2 2B Instruct (Ufficiale Google) - ~5.0 GB"
    },
    {
        "repo_id": "Qwen/Qwen2-VL-7B-Instruct-AWQ",
        "folder": "Qwen2-VL-7B-Instruct-AWQ",
        "desc": "Qwen2 Vision-Language 7B Instruct (Testo + Immagini) - ~5.8 GB"
    },
    {
        "repo_id": "deepseek-ai/DeepSeek-V2-Lite-Chat",
        "folder": "DeepSeek-V2-Lite-Chat",
        "desc": "DeepSeek V2 Lite Chat (Ufficiale DeepSeek MoE) - ~6.0 GB"
    }
]

def main():
    print("=" * 60)
    print("🚀 Inizio download modelli ufficiali:")
    print("=" * 60)

    for item in DOWNLOAD_LIST:
        repo_id = item["repo_id"]
        folder = item["folder"]
        desc = item["desc"]
        dest = MODELS_DIR / folder

        print(f"\n⬇️ [{desc}]")
        print(f"   Origine: {repo_id}")
        print(f"   Destinazione: {dest}")

        try:
            snapshot_download(
                repo_id=repo_id,
                local_dir=str(dest),
                local_dir_use_symlinks=False,
                resume_download=True
            )
            print(f"   ✅ Completato: {folder}")
        except Exception as e:
            print(f"   ❌ Errore durante il download di {repo_id}: {e}")

    print("\n" + "=" * 60)
    print("🎉 Tutti i download selezionati sono terminati!")
    print("=" * 60)

if __name__ == "__main__":
    main()
