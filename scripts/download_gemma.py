#!/usr/bin/env python3
import os
from pathlib import Path
from huggingface_hub import snapshot_download

MODELS_DIR = Path.home() / "my_models"
DEST = MODELS_DIR / "gemma-2-2b-it"

def main():
    print("=" * 60)
    print("🚀 Avvio download ufficiale: google/gemma-2-2b-it")
    print(f"📂 Destinazione: {DEST}")
    print("=" * 60)

    try:
        snapshot_download(
            repo_id="google/gemma-2-2b-it",
            local_dir=str(DEST),
            local_dir_use_symlinks=False,
            resume_download=True
        )
        print("=" * 60)
        print("🎉 Download di google/gemma-2-2b-it COMPLETATO CON SUCCESSO!")
        print("=" * 60)
    except Exception as e:
        print(f"❌ Errore durante il download: {e}")

if __name__ == "__main__":
    main()
