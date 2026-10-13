"""Download and SHA256-check the default pinned hand detector."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hand_anno.detector import download_model

if __name__ == "__main__":
    print(download_model())
