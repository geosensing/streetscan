"""Results in the manuscript come from generated macros, not typed numbers."""

import re

from streetscan.config import PROJECT_ROOT, TABLE_DIR

MANUSCRIPT = (PROJECT_ROOT / "ms" / "main.tex").read_text()
BODY = MANUSCRIPT.split(r"\begin{abstract}")[1].split(r"\clearpage")[0]


def test_every_macro_used_is_defined():
    defined = set(re.findall(r"\\newcommand{\\(\w+)}", MANUSCRIPT))
    generated = (TABLE_DIR / "macros.tex").read_text()
    defined |= set(re.findall(r"\\newcommand{\\(\w+)}", generated))
    used = set(re.findall(r"\\((?:video|streetview|noise|air|sim|condition)\w*)", BODY))
    used |= set(re.findall(r"\\((?:frames|days|nearest|sample|frame|kmh)\w+)", BODY))
    assert not used - defined


def test_no_typed_percentages_with_decimals():
    """A decimal percentage is a result; design facts are whole numbers."""
    assert not re.findall(r"\d+\.\d+\\%", BODY)


def test_headline_numbers_are_not_typed():
    for typed in ["19.8", "23.5", "18.7", "14.4", "8.1", "27.4"]:
        assert typed not in BODY
