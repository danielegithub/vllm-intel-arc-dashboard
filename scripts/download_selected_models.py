#!/usr/bin/env python3
import os
import sys
from pathlib import Path
from huggingface_hub import snapshot_download

MODELS_DIR = Path.home() / "my_models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

TARGET_MODELS = [
    {
        "repo_id": "hugging-quants/Meta-Llama-3.1-8B-Instruct-AWQ-INT4",
        "folder": "Llama-3.1-8B-Instruct-AWQ",
        "description": "Meta Llama 3.1 8B Instruct (AWQ 4-bit) - ~5.5 GB"
    },
    {
        "repo_id": "hugging-quants/Mistral-7B-Instruct-v0.3-AWQ-INT4",
        "folder": "Mistral-7B-Instruct-v0.3-AWQ",
        "description": "Mistral 7B Instruct v0.3 (AWQ 4-bit) - ~4.8 GB"
    },
    {
        "repo_id": "hugging-quants/Llama-3.2-3B-Instruct-AWQ-INT4",
        "folder": "Llama-3.2-3B-Instruct-AWQ",
        "description": "Meta Llama 3.2 3B Instruct (AWQ 4-bit) - ~2.2 GB"
    }
]

def main():
    print("=" * 60)
    print("🚀 Inizio download modelli ottimizzati per Intel Arc B580 (12GB)")
    print(f"📂 Cartella di destinazione: {MODELS_DIR}")
    print("=" * 60)

    for m in TARGET_MODELS:
        repo_id = m["repo_id"]
        folder = m["folder"]
        desc = m["description"]
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
            print(f"   ✅ Download completato con successo: {folder}")
        except Exception as e:
            print(f"   ❌ Errore durante il download di {repo_id}: {e}")

    print("\n" + "=" * 60)
    print("🎉 Tutti i download sono stati completati!")
    print("=" * 60)

if __name__ == "__main__":
    main()
