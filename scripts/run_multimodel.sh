#!/usr/bin/env bash
# Run all 3 systems × 4 repeats for each model IN PARALLEL, with gpt-5.2 as judge.
#
# Each model runs as a separate background process with its own log file.
# Results go to results/<timestamp>_comparison/ per model.
#
# Usage:
#   bash scripts/run_multimodel.sh
#   bash scripts/run_multimodel.sh 2   # override repeat count

set -euo pipefail
cd "$(dirname "$0")/.."

REPEAT="${1:-4}"
JUDGE="openai/gpt-5.2-chat"
LOG_DIR="logs/multimodel_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOG_DIR"

MODELS=(
  "openai/gpt-5.2-chat"
  "minimax/minimax-m2.5:nitro"
  "qwen/qwen3-32b:nitro"
  "z-ai/glm-4.7:nitro"
  "x-ai/grok-4.1-fast"
  "meta-llama/llama-3.3-70b-instruct:nitro"
  "anthropic/claude-sonnet-4.6"
  "openai/gpt-oss-120b:nitro"
)

echo "═══════════════════════════════════════════════════"
echo "  Multi-model benchmark (PARALLEL)"
echo "  Models:  ${#MODELS[@]}"
echo "  Repeats: ${REPEAT}"
echo "  Judge:   ${JUDGE}"
echo "  Logs:    ${LOG_DIR}/"
echo "═══════════════════════════════════════════════════"
echo ""

MAX_PARALLEL=8
PIDS=()
NAMES=()

echo "Max parallel models: ${MAX_PARALLEL}"
echo ""

for model in "${MODELS[@]}"; do
  # Wait if we've hit the concurrency limit
  while [ "${#PIDS[@]}" -ge "$MAX_PARALLEL" ]; do
    NEW_PIDS=()
    NEW_NAMES=()
    for i in "${!PIDS[@]}"; do
      if kill -0 "${PIDS[$i]}" 2>/dev/null; then
        NEW_PIDS+=("${PIDS[$i]}")
        NEW_NAMES+=("${NAMES[$i]}")
      else
        wait "${PIDS[$i]}" && echo "✓ Done: ${NAMES[$i]}" || echo "✗ FAILED: ${NAMES[$i]}"
      fi
    done
    PIDS=("${NEW_PIDS[@]}")
    NAMES=("${NEW_NAMES[@]}")
    [ "${#PIDS[@]}" -ge "$MAX_PARALLEL" ] && sleep 5
  done

  # Create a safe filename from model name
  safe_name="${model//\//_}"
  log_file="${LOG_DIR}/${safe_name}.log"

  echo "▶ Launching: ${model}  →  ${log_file}"

  PYTHONUNBUFFERED=1 python3 scripts/run_all.py \
    --model "$model" \
    --judge-model "$JUDGE" \
    --judge-provider openrouter \
    --repeat "$REPEAT" \
    > "$log_file" 2>&1 &

  PIDS+=($!)
  NAMES+=("$model")
done

echo ""
echo "All models launched. Waiting for remaining..."
echo "  Monitor with: tail -f ${LOG_DIR}/*.log"
echo ""

# Wait for remaining
FAILED=0
for i in "${!PIDS[@]}"; do
  pid="${PIDS[$i]}"
  name="${NAMES[$i]}"
  if wait "$pid"; then
    echo "✓ Done: ${name}"
  else
    echo "✗ FAILED: ${name}  (check ${LOG_DIR}/${name//\//_}.log)"
    FAILED=$((FAILED + 1))
  fi
done

echo ""
echo "═══════════════════════════════════════════════════"
if [ "$FAILED" -eq 0 ]; then
  echo "  All ${#MODELS[@]} models complete. Results in results/"
else
  echo "  ${FAILED}/${#MODELS[@]} models failed. Check logs in ${LOG_DIR}/"
fi
echo "═══════════════════════════════════════════════════"
