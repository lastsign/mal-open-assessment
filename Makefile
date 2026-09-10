.PHONY: test run run-pit gap all

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
