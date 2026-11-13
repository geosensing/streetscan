.PHONY: restore analysis manuscript paper format lint test check ci-docker clean

SOURCES = src scripts tests

restore:
	uv sync

analysis:
	uv run python scripts/99_run_all.py

manuscript:
	cd ms && latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex

paper: analysis
	$(MAKE) manuscript

format:
	uv run isort $(SOURCES)
	uv run black $(SOURCES)

lint:
	uv run isort --check-only $(SOURCES)
	uv run black --check $(SOURCES)
	uv run flake8 $(SOURCES)
	uv run codespell

test: analysis
	uv run pytest

check: paper lint test

# The container gets its own virtualenv so it never touches the host's .venv.
ci-docker:
	docker run --rm -v "$(CURDIR):/project" -w /project \
		-e UV_PROJECT_ENVIRONMENT=/tmp/venv \
		python:3.13 bash -c "apt-get update && apt-get install -y latexmk texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended lmodern && pip install uv && make restore check"

clean:
	cd ms && latexmk -C main.tex
