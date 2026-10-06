# ACaaS Platform & Experiment Automation Makefile (P1.1 / P6)

PYTHON ?= .venv/bin/python
PYTEST ?= .venv/bin/pytest

.PHONY: help up down soak-up soak-down experiments-up experiments-down test test-conformance test-security demo demo-py \
        e1 e2 e3 e4 e5 e6 e7 e8 e9 e10 e11 e12 all-quick all-full check-params figures clean

help:
	@echo "ACaaS Execution Targets:"
	@echo "  make up               - Start standard Docker Compose stack"
	@echo "  make down             - Stop standard Docker Compose stack"
	@echo "  make soak-up          - Start 3-site soak Docker Compose stack"
	@echo "  make soak-down        - Stop 3-site soak Docker Compose stack"
	@echo "  make test             - Run all unit, blockchain, cross, security, integration tests"
	@echo "  make test-conformance - Run canonical 33-test Conformance Suite"
	@echo "  make test-security    - Run 21 Security Assertions on live stack"
	@echo "  make e1 .. e12        - Run individual experiment (quick mode)"
	@echo "  make all-quick        - Run all E1-E12 experiments (quick mode, ~15 min)"
	@echo "  make all-full         - Run all E1-E12 experiments (full paper scale)"
	@echo "  make check-params     - Validate experiment results against experience_parameter.md"
	@echo "  make figures          - Generate publication plots (PNG & PDF)"
	@echo "  make clean            - Clean cache, temp files, and results"

up:
	docker compose -f docker-compose.yml -f docker-compose.experiments.yml up -d

down:
	docker compose -f docker-compose.yml -f docker-compose.experiments.yml down

soak-up:
	docker compose -f docker-compose.yml -f docker-compose.experiments.yml -f docker-compose.soak.yml --profile soak up -d

soak-down:
	docker compose -f docker-compose.yml -f docker-compose.experiments.yml -f docker-compose.soak.yml --profile soak down

experiments-up:
	docker compose -f docker-compose.yml -f docker-compose.experiments.yml up -d

experiments-down:
	docker compose -f docker-compose.yml -f docker-compose.experiments.yml down

test:
	$(PYTEST) tests/ -v

test-conformance:
	$(PYTEST) tests/unit tests/blockchain tests/cross -v

test-security:
	$(PYTEST) -m security tests/security/ -v

demo:
	bash scripts/demo.sh

demo-py:
	$(PYTHON) scripts/run_demo.py

e1:
	$(PYTHON) experiments/e01_latency.py --quick

e2:
	$(PYTHON) experiments/e02_throughput.py --quick

e3:
	$(PYTHON) experiments/e03_sync.py --quick

e4:
	$(PYTHON) experiments/e04_ledger.py --quick

e5:
	$(PYTHON) experiments/e05_offline.py --quick

e6:
	$(PYTHON) experiments/e06_conformance.py

e7:
	$(PYTHON) experiments/e07_hitrate.py --quick

e8:
	$(PYTHON) experiments/e08_minimizer.py --quick

e9:
	$(PYTHON) experiments/e09_attack.py --quick

e10:
	$(PYTHON) experiments/e10_ablation.py --quick

e11:
	$(PYTHON) experiments/e11_byzantine.py --quick

e12:
	$(PYTHON) experiments/e12_soak.py --quick

all-quick:
	bash experiments/run_all.sh --quick
	$(PYTHON) experiments/check_params.py
	$(PYTHON) experiments/plots/generate_plots.py

all-full:
	bash experiments/run_all.sh --full
	$(PYTHON) experiments/check_params.py
	$(PYTHON) experiments/plots/generate_plots.py

check-params:
	$(PYTHON) experiments/check_params.py

figures:
	$(PYTHON) experiments/plots/generate_plots.py

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache
