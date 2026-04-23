#!/bin/bash
# Run D17 materializer in 50k-source chunks to keep postings_tokens tractable.
# Produces per-chunk CSVs under reports/.
# Total eligible: 664,442 sources -> ceil(664442/50000) = 14 chunks.

set -euo pipefail
cd "$(dirname "$0")/.."

CHUNK_SIZE=50000
TOTAL=664442
START_AT="${1:-0}"
END_AT="${2:-$TOTAL}"

mkdir -p reports/_d17_chunk_logs

idx=0
offset=0
while [ $offset -lt $TOTAL ]; do
  chunk_tag=$(printf "chunk_%03d" "$idx")
  if [ $offset -lt "$START_AT" ] || [ $offset -ge "$END_AT" ]; then
    echo "[SKIP] $chunk_tag offset=$offset"
    idx=$((idx + 1))
    offset=$((offset + CHUNK_SIZE))
    continue
  fi
  log_file="reports/_d17_chunk_logs/${chunk_tag}.log"
  csv_file="reports/tail_d17_alias_candidates_2026-04-16_${chunk_tag}.csv.gz"
  if [ -f "$csv_file" ]; then
    echo "[SKIP_EXISTS] $chunk_tag already has $csv_file"
    idx=$((idx + 1))
    offset=$((offset + CHUNK_SIZE))
    continue
  fi
  echo "[START] $chunk_tag offset=$offset limit=$CHUNK_SIZE $(date +%H:%M:%S)"
  python scripts/build_d17_alias_candidates.py \
    --offset "$offset" \
    --limit "$CHUNK_SIZE" \
    --suffix "$chunk_tag" 2>&1 | tee "$log_file"
  echo "[DONE]  $chunk_tag $(date +%H:%M:%S)"
  idx=$((idx + 1))
  offset=$((offset + CHUNK_SIZE))
done

echo "[ALL_CHUNKS_DONE] $(date +%H:%M:%S)"
