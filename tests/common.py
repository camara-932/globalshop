"""Fonctions partagées par les scripts de test."""
import uuid
import requests

REGIONS = ["afrique", "europe", "amerique", "asie"]


def creer_produit(api, nom, prix, stock):
    r = requests.post(f"{api}/produits", json={"nom": nom, "prix": prix, "stock": stock}, timeout=60)
    r.raise_for_status()
    return r.json()["product_id"]


def creer_client(api, region, i=0):
    r = requests.post(f"{api}/clients",
                      json={"nom": f"Client {region} {i}", "email": f"c{i}-{uuid.uuid4().hex[:6]}@{region}.test", "region": region},
                      timeout=60)
    r.raise_for_status()
    return r.json()["client_id"]
