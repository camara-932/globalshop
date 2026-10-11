"""Vérifie les invariants après un test de panne."""
import argparse
import json
import sys

import requests

ap = argparse.ArgumentParser()
ap.add_argument("--api", default="http://localhost:8000")
ap.add_argument("--file", default="stream_result.json")
a = ap.parse_args()

s = json.load(open(a.file))
v = requests.get(f"{a.api}/produits/{s['product_id']}/ventes", timeout=60).json()
db_orders, stock_final = v["commandes_confirmees"], v["stock"]
vendu = s["stock_initial"] - stock_final

print("============ VÉRIFICATION D'INTÉGRITÉ ============")
print(f"Commandes confirmées côté client  : {s['ok']}")
print(f"Requêtes d'issue inconnue         : {s['unknown']}  (timeout / erreur pendant la panne)")
print(f"Commandes présentes en base       : {db_orders}")
print(f"Stock initial - stock final       : {vendu}")
print(f"Plus longue interruption (s)      : {s['max_gap_s']}")

checks = {
    "stock jamais négatif": stock_final >= 0,
    "ventes = commandes en base (cohérence interne)": vendu == db_orders,
    "aucune commande confirmée perdue (base >= confirmées)": db_orders >= s["ok"],
    "aucune commande fantôme (base <= confirmées + inconnues)": db_orders <= s["ok"] + s["unknown"],
}
for k, ok in checks.items():
    print(f"  [{'OK' if ok else 'ÉCHEC'}] {k}")
all_ok = all(checks.values())
print("\nVERDICT :", "PASS" if all_ok else "FAIL")
sys.exit(0 if all_ok else 1)
