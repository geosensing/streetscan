"""Run the numbered stages in order. Stages pass results only through files."""

import runpy

from streetscan.config import DERIVED_DIR, FIGURE_DIR, SCRIPT_DIR, TABLE_DIR

for directory in (DERIVED_DIR, TABLE_DIR, FIGURE_DIR):
    directory.mkdir(parents=True, exist_ok=True)

stages = sorted(SCRIPT_DIR.glob("[0-8][0-9]_*.py"))
for stage in stages:
    print(f"Running {stage.name}")
    runpy.run_path(str(stage), run_name="__main__")
