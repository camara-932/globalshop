"""Test de charge : N achats simultanés d'un même produit (stock limité)."""
import argparse
import statistics
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import requests
from common import REGIONS, creer_client, creer_produit

ap = argparse.ArgumentParser()
ap.add_argument("--api", default="http://localhost:8000")
ap.add_argument("--clients", type=int, default=100, help="nombre d'acheteurs simultanés")
ap.add_argument("--stock", type=int, default=50, help="stock initial")
args = ap.parse_args()
N, STOCK, API = args.clients, args.stock, args.api

print(f"[setup] produit avec stock={STOCK}, {N} clients répartis sur 4 régions...")
pid = creer_produit(API, "Produit test charge", 9.99, STOCK)
with ThreadPoolExecutor(20) as ex:
    acheteurs = list(ex.map(lambda i: (REGIONS[i % 4], creer_client(API, REGIONS[i % 4], i)), range(N)))

barrier = threading.Barrier(N)
results = []


def acheter(i):
    region, cid = acheteurs[i]
    body = {"region": region, "client_id": cid, "product_id": pid, "quantite": 1, "request_id": str(uuid.uuid4())}
    barrier.wait()                       # départ simultané
    t0 = time.time()
    try:
        r = requests.post(f"{API}/commandes", json=body, timeout=120)
        status, retries = r.status_code, r.json().get("retries", 0)
    except Exception:
        status, retries = -1, 0
    return status, retries, (time.time() - t0) * 1000


print(f"[go] {N} requêtes d'achat simultanées...")
t_start = time.time()
with ThreadPoolExecutor(N) as ex:
    results = list(ex.map(acheter, range(N)))
duree = time.time() - t_start

ok = sum(1 for s, _, _ in results if s == 201)
rupture = sum(1 for s, _, _ in results if s == 409)
autres = N - ok - rupture
retries = sum(r for _, r, _ in results)
lat = sorted(l for _, _, l in results)
p50 = statistics.median(lat)
p95 = lat[int(0.95 * (len(lat) - 1))]

v = requests.get(f"{API}/produits/{pid}/ventes", timeout=60).json()
attendu_ok = min(STOCK, N)

print("\n================ RÉSULTATS ================")
print(f"Commandes confirmées (201)     : {ok}   (attendu {attendu_ok})")
print(f"Refus rupture de stock (409)   : {rupture}   (attendu {N - attendu_ok})")
print(f"Échecs techniques              : {autres}   (attendu 0)")
print(f"Stock final                    : {v['stock']}   (attendu {max(STOCK - N, 0)})")
print(f"Commandes en base              : {v['commandes_confirmees']}   (attendu = {ok})")
print(f"Retries (40001) cumulés        : {retries}")
print(f"Latence p50 / p95 (ms)         : {p50:.0f} / {p95:.0f}")
print(f"Durée totale (s)               : {duree:.2f}")

passed = (ok == attendu_ok and autres == 0 and v["stock"] == max(STOCK - N, 0)
          and v["commandes_confirmees"] == ok and v["stock"] >= 0)
print("\nVERDICT :", "PASS — aucune survente" if passed else "FAIL — voir ci-dessus")
sys.exit(0 if passed else 1)
