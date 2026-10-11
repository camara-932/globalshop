#!/usr/bin/env bash
# Démo automatisée de bout en bout.
# Usage : bash demo.sh           -> fonctionnalités + test de charge
#         bash demo.sh --chaos   -> idem + test de panne
set -euo pipefail
cd "$(dirname "$0")"
API="${API:-http://localhost:8000}"

echo ">> Attente de l'API ($API)..."
for i in $(seq 1 60); do
  curl -sf "$API/health" >/dev/null && break
  sleep 2
  [ "$i" = 60 ] && { echo "API injoignable : docker compose logs init api1"; exit 1; }
done
echo ">> API prête."

echo; echo "################ 1. FONCTIONNALITÉS ################"
python3 tests/demo_functional.py --api "$API"

echo; echo "################ 2. TEST DE CHARGE (100 achats simultanés) ################"
python3 tests/load_test.py --api "$API" --clients 100 --stock 50

if [ "${1:-}" = "--chaos" ]; then
  echo; echo "################ 3. TEST DE PANNE ################"
  API="$API" bash tests/chaos_test.sh roach2
fi
echo; echo ">> Démo terminée."
