import hashlib

import pandas as pd

from streetscan.config import RAW_DIR, RAW_FILES


def verify_sources():
    """Stop if any raw table differs from the one the analysis was written for."""
    for name, expected in RAW_FILES.items():
        actual = hashlib.sha256((RAW_DIR / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"{name} does not match its recorded SHA-256")


def read_raw(name):
    return pd.read_csv(RAW_DIR / name)
