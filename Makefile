.PHONY: test run run-pit gap all doc doc-clean

PY ?= python3
export PYTHONPATH := .

test:
	$(PY) -m pytest

run:
	$(PY) -m ledger.replay

run-pit:
	$(PY) -m ledger.replay --policy point-in-time

gap:
	$(PY) -m pytest tests/test_known_gap.py --runxfail

all: test run

doc:
	cd doc && latexmk -pdf -interaction=nonstopmode -halt-on-error architecture.tex

doc-clean:
	cd doc && latexmk -c
