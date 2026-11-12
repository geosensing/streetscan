from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
DERIVED_DIR = PROJECT_ROOT / "data" / "derived"
TABLE_DIR = PROJECT_ROOT / "tabs"
FIGURE_DIR = PROJECT_ROOT / "figs"
SCRIPT_DIR = PROJECT_ROOT / "scripts"

FIGURE_DPI = 180

# "<sha256>  <file>" per line, as shasum writes it.
RAW_FILES = {
    name: digest
    for digest, name in (
        line.split() for line in (RAW_DIR / "checksums.sha256").read_text().splitlines()
    )
}
