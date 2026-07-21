import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
src_dir = str(ROOT / "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
