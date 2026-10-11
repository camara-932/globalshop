"""Flux continu d'achats (utilisé par le test de panne). Écrit un fichier JSON de résultats."""
import argparse
import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import requests
from common import REGIONS, creer_client, creer_produit

ap = argparse.ArgumentParser()
ap.add_argument("--api", default="http://localhost:8000")
ap.add_argument("--rate", type=float, default=5, help="achats par seconde")
ap.add_argument("--duration", type=int, default=60)
ap.add_argument("--stock", type=int, default=100000)
ap.add_argument("--out", default="stream_result.json")
a = ap.parse_args()

pid = creer_produit(a.api, "Produit chaos", 5.0, a.stock)
clients = [(r, creer_client(a.api, r, i)) for i, r in enumerate(REGIONS)]
print(f"[stream] product_id={pid} stock_initial={a.stock}", flush=True)

records, lock = [], threading.Lock()
t0 = time.time()


def acheter(i):
    region, cid = clients[i % 4]
    body = {"region": region, "client_id": cid, "product_id": pid, "quantite": 1, "request_id": str(uuid.uuid4())}
    outcome = "unknown"
    for _ in range(3):                      # même request_id => rejouer ne crée jamais de doublon
        try:
            r = requests.post(f"{a.api}/commandes", json=body, timeout=10)
            if r.status_code in (200, 201):
                outcome = "ok"; break
            if r.status_code == 409:
                outcome = "rupture"; break
        except Exception:
            pass
        time.sleep(1)
    with lock:
        records.append({"t": round(time.time() - t0, 2), "outcome": outcome})


with ThreadPoolExecutor(64) as ex:
    n = 0
    while time.time() - t0 < a.duration:
        ex.submit(acheter, n); n += 1
        time.sleep(1.0 / a.rate)

records.sort(key=lambda r: r["t"])
oks = [r["t"] for r in records if r["outcome"] == "ok"]
gap = max((b - a_ for a_, b in zip(oks, oks[1:])), default=0)
res = {"product_id": pid, "stock_initial": a.stock, "records": records,
       "ok": len(oks), "unknown": sum(r["outcome"] == "unknown" for r in records),
       "rupture": sum(r["outcome"] == "rupture" for r in records), "max_gap_s": round(gap, 2)}
json.dump(res, open(a.out, "w"))
print(f"[stream] terminé : ok={res['ok']} inconnus={res['unknown']} rupture={res['rupture']} "
      f"plus longue interruption sans succès={res['max_gap_s']}s", flush=True)
