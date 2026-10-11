"""Démonstration fonctionnelle : inscription, produit, catalogue, commande."""
import argparse
import requests
from common import REGIONS, creer_client, creer_produit

ap = argparse.ArgumentParser()
ap.add_argument("--api", default="http://localhost:8000")
api = ap.parse_args().api

print("== 1. Inscription d'un client par région ==")
clients = {}
for reg in REGIONS:
    clients[reg] = creer_client(api, reg)
    print(f"  client {reg:9s} -> {clients[reg]}")

print("\n== 2. Création de produits (avec stock initial) ==")
pids = [creer_produit(api, n, p, s) for n, p, s in [("Clavier", 25.0, 10), ("Souris", 12.5, 5), ("Écran", 180.0, 2)]]
print("  produits :", pids)

print("\n== 3. Catalogue (lecture distribuée) ==")
cat = requests.get(f"{api}/produits", timeout=30).json()
for p in cat["produits"]:
    print(f"  {p['nom']:10s} prix={p['prix']}  stock={p['stock']}")

print("\n== 4. Commande : stock mis à jour + commande + facture (transaction distribuée) ==")
r = requests.post(f"{api}/commandes", json={"region": "afrique", "client_id": clients["afrique"],
                                             "product_id": pids[0], "quantite": 3}, timeout=30)
print("  ", r.status_code, r.json())
print("   stock Clavier :", requests.get(f"{api}/stock/{pids[0]}", timeout=30).json()["stock"], "(attendu 7)")

print("\n== 5. Tentative d'achat supérieure au stock (doit être refusée) ==")
r = requests.post(f"{api}/commandes", json={"region": "europe", "client_id": clients["europe"],
                                             "product_id": pids[2], "quantite": 5}, timeout=30)
print("  ", r.status_code, r.json(), "(attendu 409)")

print("\n== 6. Commandes d'un client (lecture locale à son fragment) ==")
print("  ", requests.get(f"{api}/commandes/afrique/{clients['afrique']}", timeout=30).json())
