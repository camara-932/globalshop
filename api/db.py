"""Accès aux nœuds CockroachDB : routage par région, retry sur conflit, basculement."""
import os
import random
import threading
import time

import psycopg
from psycopg import errors
from psycopg_pool import ConnectionPool, PoolTimeout


def _parse_nodes() -> dict:
    raw = os.getenv("NODES", "afrique=roach1,europe=roach2,amerique=roach3,asie=roach4")
    return dict(item.split("=") for item in raw.split(","))


# Table de routage : région -> nœud d'entrée le plus proche
NODES = _parse_nodes()
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "12"))

_pools: dict = {}
_lock = threading.Lock()


class NodeUnavailable(Exception):
    """Aucun nœud n'a pu répondre."""


class TooManyConflicts(Exception):
    """Trop de conflits de sérialisation (40001) successifs."""


def _pool(host: str) -> ConnectionPool:
    with _lock:
        if host not in _pools:
            conninfo = (f"host={host} port=26257 dbname=globalshop user=root "
                        f"sslmode=disable connect_timeout=3")
            pool = ConnectionPool(
                conninfo, min_size=1, max_size=int(os.getenv("POOL_MAX", "20")),
                timeout=4, max_lifetime=300,
                kwargs={"autocommit": True},          # BEGIN/COMMIT gérés par conn.transaction()
                check=ConnectionPool.check_connection,  # écarte les connexions mortes (nœud tué)
                open=False,
            )
            pool.open(wait=False)
            _pools[host] = pool
        return _pools[host]


def candidate_hosts(region):
    """Nœud de la région en premier, puis les autres dans un ordre aléatoire (failover)."""
    hosts = list(NODES.values())
    random.shuffle(hosts)
    pref = NODES.get(region) if region else None
    if pref:
        hosts.remove(pref)
        hosts.insert(0, pref)
    return hosts


def run_tx(fn, region=None):
    """Exécute fn(conn) dans une transaction SERIALIZABLE.

    - erreur 40001 (conflit)  -> ROLLBACK + nouvel essai (backoff exponentiel + jitter)
    - nœud injoignable        -> bascule sur le nœud suivant
    Retourne (résultat, nb_retries, nœud_utilisé).
    """
    retries = 0
    for host in candidate_hosts(region):
        attempt = 0
        while True:
            try:
                with _pool(host).connection() as conn:
                    with conn.transaction():
                        result = fn(conn)
                return result, retries, host
            except errors.SerializationFailure:
                retries += 1
                attempt += 1
                if attempt > MAX_RETRIES:
                    raise TooManyConflicts()
                time.sleep(min(1.0, 0.02 * 2 ** attempt) * random.uniform(0.5, 1.5))
            except (psycopg.OperationalError, PoolTimeout):
                break  # nœud indisponible : on essaie le suivant
    raise NodeUnavailable()
