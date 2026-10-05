#!/usr/bin/env bash
# ACaaS Experiment Runner (P1.1)
# Executes all experiments E1 through E12 sequentially.
# Usage:
#   bash experiments/run_all.sh --quick    # Smoke test (reduced samples)
#   bash experiments/run_all.sh --full     # Full scale experiments per paper parameters
set -euo pipefail

MODE="--quick"
if [ "${1:-}" = "--full" ]; then
  MODE=""
  echo "=== Running FULL SCALE Experiments (E1 - E12) ==="
else
  echo "=== Running QUICK SMOKE TEST Experiments (E1 - E12) ==="
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON="${ROOT_DIR}/.venv/bin/python"
if [ ! -f "$PYTHON" ]; then
  PYTHON="python3"
fi

echo "Using Python: $PYTHON"
echo "Results destination: ${ROOT_DIR}/results/"
echo ""

EXPERIMENTS=(
  "experiments/e01_latency.py"
  "experiments/e02_throughput.py"
  "experiments/e03_sync.py"
  "experiments/e04_ledger.py"
  "experiments/e05_offline.py"
  "experiments/e06_conformance.py"
  "experiments/e07_hitrate.py"
  "experiments/e08_minimizer.py"
  "experiments/e09_attack.py"
  "experiments/e10_ablation.py"
  "experiments/e11_byzantine.py"
  "experiments/e12_soak.py"
)

TOTAL=${#EXPERIMENTS[@]}
SUCCESS_COUNT=0

for i in "${!EXPERIMENTS[@]}"; do
  EXP="${EXPERIMENTS[$i]}"
  IDX=$((i + 1))
  echo "=========================================================="
  echo "[$IDX/$TOTAL] Running $EXP..."
  echo "=========================================================="

  if [ -n "$MODE" ]; then
    "$PYTHON" "$EXP" "$MODE"
  else
    "$PYTHON" "$EXP"
  fi

  SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
  echo ""
done

echo "=========================================================="
echo "All $SUCCESS_COUNT/$TOTAL experiments completed successfully!"
echo "Results saved in results/E*/"
echo "=========================================================="
