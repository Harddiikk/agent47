.PHONY: install run web test clean scan

# Override with: make web PORT=9000
PORT ?= 8001
PY := .venv/bin/python
PIP := .venv/bin/pip
ADK := .venv/bin/adk
PYTEST := .venv/bin/pytest

install:
	$(PIP) install -r requirements.txt

# PYTHONPATH=. puts the project root on sys.path so ADK can resolve
# `from agents.onboarding import onboarding` etc. when it loads agents.
run:
	PYTHONPATH=. $(ADK) run agents/sdr_agent

web:
	PYTHONPATH=. $(ADK) web agents --port $(PORT)

test:
	$(PYTEST) tests/ -v

# Headless end-to-end demo: scan the customer book → research → draft → Slack
scan:
	PYTHONPATH=. $(PY) -m scripts.scan

# SDR pipeline: leads CSV → resolve → research → verify → offers → Slack cards
sdr-scan:
	PYTHONPATH=. $(PY) -m scripts.sdr_scan $(FILE)

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
