# RE3 Makefile - Fallback for systems without 'just'
# Usage: make <target>

.PHONY: help setup run run-all status smoke test progress

help:
	@echo "RE3 Experiment Commands"
	@echo ""
	@echo "  make setup     - Install dependencies"
	@echo "  make run       - Run one experiment slice"
	@echo "  make run-all   - Run until complete"
	@echo "  make status    - Check setup status"
	@echo "  make smoke     - Quick test (5 items)"
	@echo "  make progress  - Show experiment progress"
	@echo ""
	@echo "Or just use: python bootstrap.py [setup|run|run-all]"

setup:
	pip install datasets

run:
	python bootstrap.py run

run-all:
	python bootstrap.py run-all

status:
	python bootstrap.py status

smoke:
	python harness/run_tests.py --smoke --data-dir ./data

progress:
	python harness/progress.py status

init:
	python harness/progress.py init
