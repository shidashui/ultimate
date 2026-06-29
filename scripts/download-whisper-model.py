#!/usr/bin/env python3
"""Download Whisper model (faster-whisper) to local project directory.

Usage:
    python scripts/download-whisper-model.py                  # download default (small)
    python scripts/download-whisper-model.py --model tiny     # download tiny
    python scripts/download-whisper-model.py --model small    # download small
    python scripts/download-whisper-model.py --check          # verify local model
    python scripts/download-whisper-model.py --model all      # download all common sizes
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Map model size → HuggingFace repo
MODEL_REPOS = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large": "Systran/faster-whisper-large-v3",
}

# Project root (two levels up from scripts/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "models" / "whisper"


def download_model(model_size: str) -> Path:
    """Download model snapshot, return local path."""
    repo_id = MODEL_REPOS[model_size]
    local_dir = MODELS_DIR / model_size

    print(f"Downloading {repo_id} → {local_dir} ...")

    from huggingface_hub import snapshot_download

    snapshot_download(
        repo_id=repo_id,
        local_dir=str(local_dir),
        local_dir_use_symlinks=False,
        resume_download=True,
        ignore_patterns=["*.h5", "*.ot"],
    )

    # Write marker file
    marker = local_dir / ".model_ready"
    marker.write_text(f"model={model_size}\nsource={repo_id}\n")
    print(f"✓ {model_size} model ready at {local_dir}")
    return local_dir


def check_model(model_size: str) -> bool:
    """Verify local model completeness."""
    local_dir = MODELS_DIR / model_size
    marker = local_dir / ".model_ready"

    if not local_dir.is_dir():
        print(f"✗ {model_size}: directory not found at {local_dir}")
        return False
    if not marker.is_file():
        print(f"✗ {model_size}: .model_ready marker missing (incomplete download)")
        return False

    # Check essential files exist
    required = ["model.bin", "config.json", "tokenizer.json"]
    missing = [f for f in required if not (local_dir / f).is_file()]
    if missing:
        print(f"✗ {model_size}: missing files: {', '.join(missing)}")
        return False

    # Rough size check: model.bin should be > 10MB
    model_bin = local_dir / "model.bin"
    size_mb = model_bin.stat().st_size / (1024 * 1024)
    if size_mb < 10:
        print(f"✗ {model_size}: model.bin too small ({size_mb:.1f} MB)")
        return False

    print(f"✓ {model_size}: {size_mb:.0f} MB, all files present")
    return True


def main():
    parser = argparse.ArgumentParser(description="Download Whisper model locally")
    parser.add_argument(
        "--model",
        default="small",
        choices=list(MODEL_REPOS.keys()) + ["all"],
        help="Model size to download (default: small, or 'all' for all sizes)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify local model integrity instead of downloading",
    )
    args = parser.parse_args()

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    if args.model == "all":
        sizes = list(MODEL_REPOS.keys())
    else:
        sizes = [args.model]

    all_ok = True
    for size in sizes:
        if args.check:
            ok = check_model(size)
            if not ok:
                all_ok = False
        else:
            try:
                download_model(size)
            except Exception as e:
                print(f"✗ {size}: download failed: {e}")
                all_ok = False

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
