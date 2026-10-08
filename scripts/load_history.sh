#!/usr/bin/env bash
# Fetch and extract every Backblaze ZIP, one after another, on Fargate.
# Safe to stop and run again: the fetcher and extractor skip work that is already done.
#
# Usage: scripts/load_history.sh
set -uo pipefail

BASE=https://f001.backblazeb2.com/file/Backblaze-Hard-Drive-Data

# 2013-2015 are one ZIP per year; from 2016 it is one per quarter.
NAMES=(data_2013.zip data_2014.zip data_2015.zip)
for year in $(seq 2016 2025); do
  for quarter in 1 2 3 4; do
    NAMES+=("data_Q${quarter}_${year}.zip")
  done
done
NAMES+=(data_Q1_2026.zip data_Q2_2026.zip)

echo "=== $(date '+%Y-%m-%d %H:%M:%S') starting: ${#NAMES[@]} ZIPs ==="

for name in "${NAMES[@]}"; do
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') $name ==="
  if ! scripts/run_task.sh fetcher.fetch "$BASE/$name"; then
    echo "!!! Could not start a task for $name. Stopping here."
    echo "!!! If your AWS session expired: run 'aws login --region ap-southeast-2', then run this script again."
    exit 1
  fi
  scripts/run_task.sh fetcher.extract "$name" || echo "!!! Could not start the extract for $name"
done

echo "=== $(date '+%Y-%m-%d %H:%M:%S') rebuilding the bookkeeping tables ==="
scripts/run_task.sh fetcher.bookkeeping

echo "=== $(date '+%Y-%m-%d %H:%M:%S') finished ==="
