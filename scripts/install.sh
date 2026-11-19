#!/usr/bin/env bash
# Installs ffmpeg and a Python venv (.venv/) with everything in requirements.txt.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v ffmpeg >/dev/null; then
  echo "Installing ffmpeg..."
  if   command -v brew    >/dev/null; then brew install ffmpeg
  elif command -v apt-get >/dev/null; then sudo apt-get update && sudo apt-get install -y ffmpeg
  elif command -v dnf     >/dev/null; then sudo dnf install -y ffmpeg
  elif command -v pacman  >/dev/null; then sudo pacman -S --noconfirm ffmpeg
  else echo "Please install ffmpeg manually"; exit 1; fi
fi

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
if ! command -v nvidia-smi >/dev/null && [ "$(uname)" = "Linux" ]; then
  echo "No NVIDIA GPU found - installing the small CPU-only PyTorch (~1.5 GB instead of ~6 GB)"
  pip install torch --index-url https://download.pytorch.org/whl/cpu
fi
pip install -r requirements.txt
chmod +x scripts/*.sh start.sh start.command run.sh
echo "Done. Double-click start.sh / start.command, or run ./scripts/watch-channel.sh <channel>"
