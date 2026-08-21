#!/usr/bin/env python3
import os
from pathlib import Path
from huggingface_hub import snapshot_download

MODELS_DIR = Path.home() / "my_models"

QUEUE = [
    {
        "repo_id": "meta-llama/Llama-3.2-3B-Instruct",
        "folder": "Llama-3.2-3B-Instruct",
        "desc": "Meta Llama 3.2 3B Instruct (Ufficiale Meta) - ~6.0 GB"
    },
    {
        "repo_id": "meta-llama/Llama-3.2-1B-Instruct",
        "folder": "Llama-3.2-1B-Instruct",
        "desc": "Meta Llama 3.2 1B Instruct (Ufficiale Meta) - ~2.4 GB"
    }
]

def main():
    print("=" * 60)
    print("🚀 Avvio download modelli ufficiali Meta Llama 3.2")
    print("=" * 60)

    for item in QUEUE:
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
            print(f"   ✅ Download completato con successo: {folder}")
        except Exception as e:
            print(f"   ❌ Errore durante il download di {repo_id}: {e}")

    print("\n" + "=" * 60)
    print("🎉 Download di tutti i modelli Meta completati!")
    print("=" * 60)

if __name__ == "__main__":
    main()
