import sys
from pathlib import Path

# Ensure src/ and repo root are in sys.path during pytest execution
pipeline_dir = Path(__file__).resolve().parent.parent
src_dir = pipeline_dir.parent
root_dir = src_dir.parent

for path_str in [str(src_dir), str(root_dir)]:
    if path_str not in sys.path:
        sys.path.insert(0, path_str)
