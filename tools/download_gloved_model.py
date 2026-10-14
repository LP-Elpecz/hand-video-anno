"""Download pinned Grounding DINO weights with SHA256 checks."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hand_anno.gloved_model import download_gloved_model

if __name__ == "__main__":
    print(download_gloved_model(progress=lambda _, __, message: print(message, flush=True)))
