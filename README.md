# GlobalShop - base de données distribuée résiliente

Cluster CockroachDB (4 nœuds) + 2 API FastAPI (routage par région, retry, failover) + HAProxy.

## Prérequis
Docker + Docker Compose, Python 3.9+ (pour les scripts de test) : `pip install -r tests/requirements.txt`

## Démarrage (une commande)
```bash
docker compose up -d --build
```
Le service `init` initialise le cluster et charge `db/schema.sql`. Compter ~30-60 s.
- API : http://localhost:8000/docs
- Console CockroachDB : http://localhost:8080 (état des nœuds, plages, leaseholders)

## Démo automatisée
```bash
bash demo.sh            # fonctionnalités + test de charge (100 achats simultanés)
bash demo.sh --chaos    # + test de panne (docker kill d'un nœud)
```

## Tests séparés
```bash
python3 tests/load_test.py --clients 100 --stock 50     # critère : exactement 50 ventes, stock final 0
bash tests/chaos_test.sh roach2                         # kill brutal pendant un flux d'achats
```
Pour viser le nœud *leaseholder* du stock : console 8080 → Databases → globalshop → stock → Range, puis tuer ce nœud.

## Endpoints
| Méthode | Route | Rôle |
|---|---|---|
| POST | /clients | inscription (fragment = région) |
| POST | /produits | création produit + stock |
| GET | /produits | catalogue (lecture distribuée) |
| POST | /commandes | commande : transaction distribuée anti-survente |
| GET | /stock/{id} | stock courant |
| GET | /produits/{id}/ventes | commandes confirmées + stock (vérifications) |
| GET | /commandes/{region}/{client_id} | commandes d'un client |

## Commandes utiles
```bash
docker kill roach2 && docker start roach2     # panne manuelle
docker compose logs -f api1                   # logs API
docker compose down -v                        # tout supprimer
```

## Dépannage
- `init` échoue / boucle : `docker compose logs init`. Si le tag d'image `cockroachdb/cockroach:v24.3.0` n'existe pas, changez-le dans `docker-compose.yml` (ligne `image:`).
- Un nœud tué n'est re-répliqué qu'après ~5 min (réglage CockroachDB) : ne tuez pas un 2ᵉ nœud avant son retour, sinon des plages perdent leur quorum (comportement CP attendu).
- Mode `--insecure` : prototype local uniquement.
