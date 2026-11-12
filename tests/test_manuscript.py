"""Results in the manuscript come from generated macros, not typed numbers."""

import re

from streetscan.config import PROJECT_ROOT, TABLE_DIR

MANUSCRIPT = (PROJECT_ROOT / "ms" / "main.tex").read_text()
BODY = MANUSCRIPT.split(r"\begin{abstract}")[1].split(r"\clearpage")[0]


def test_every_generated_macro_used_is_defined():
    generated = (TABLE_DIR / "macros.tex").read_text()
    defined = set(re.findall(r"\\newcommand{\\(\w+)}", generated))
    prefixes = sorted({name[:5] for name in defined})
    used = {
        name
        for name in re.findall(r"\\([A-Za-z]+)", BODY)
        if any(name.startswith(prefix) for prefix in prefixes) and len(name) > 8
    }
    latex_words = {"simulation", "framebox", "samplesize", "classification"}
    assert not used - defined - latex_words


def test_no_typed_percentages_with_decimals():
    """A decimal percentage is a result; design facts are whole numbers."""
    assert not re.findall(r"\d+\.\d+\\%", BODY)


def test_headline_numbers_are_not_typed():
    for typed in ["20.4", "23.5", "18.7", "14.4", "8.1", "27.5"]:
        assert typed not in BODY


def test_every_reference_has_a_label():
    labels = set(re.findall(r"\\label{([^}]+)}", MANUSCRIPT))
    references = set(re.findall(r"\\ref{([^}]+)}", MANUSCRIPT))
    assert not references - labels
