.PHONY: test run run-pit gap all doc doc-clean complexity check

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

# Cognitive complexity (complexipy) gates at 15 per function and exits
# non-zero above it. Cyclomatic complexity (radon, McCabe) is reported
# alongside because they measure different things and disagree usefully.
complexity:
	complexipy --max-complexity-allowed 15 ledger tests
	radon cc ledger -s -a

check: test complexity

all: test run

doc:
	cd doc && latexmk -pdf -interaction=nonstopmode -halt-on-error architecture.tex

doc-clean:
	cd doc && latexmk -c
