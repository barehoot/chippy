import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))                                   # harness, synthetic
sys.path.insert(0, str(HERE.parents[1] / "python"))             # sr_lib
