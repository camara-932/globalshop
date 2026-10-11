#!/usr/bin/env bash
# Test de panne : arrêt brutal (SIGKILL) d'un nœud pendant un flux d'achats.
# Usage : bash tests/chaos_test.sh [conteneur_victime]   (défaut : roach2)
set -euo pipefail
API="${API:-http://localhost:8000}"
VICTIM="${1:-roach2}"
OUT="${OUT:-/tmp/stream_result.json}"

python3 tests/purchase_stream.py --api "$API" --rate 5 --duration 60 --out "$OUT" &
STREAM=$!

sleep 15
echo "[chaos] $(date +%T) — docker kill $VICTIM (arrêt brutal)"
docker kill "$VICTIM"

sleep 25
echo "[chaos] $(date +%T) — redémarrage de $VICTIM"
docker start "$VICTIM"

wait "$STREAM"
sleep 5
python3 tests/verify_integrity.py --api "$API" --file "$OUT"
