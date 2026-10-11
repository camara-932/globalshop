"""API GlobalShop : routeur applicatif devant le cluster CockroachDB."""
from typing import Literal, Optional
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from psycopg import errors
from pydantic import BaseModel, Field

from db import NodeUnavailable, TooManyConflicts, run_tx

app = FastAPI(title="GlobalShop API")
Region = Literal["afrique", "europe", "amerique", "asie"]


class ClientIn(BaseModel):
    nom: str
    email: str
    region: Region


class ProduitIn(BaseModel):
    nom: str
    prix: float = Field(ge=0)
    stock: int = Field(ge=0)


class CommandeIn(BaseModel):
    region: Region
    client_id: UUID
    product_id: UUID
    quantite: int = Field(default=1, ge=1)
    request_id: Optional[UUID] = None   # clé d'idempotence (fournie par le client)


@app.exception_handler(NodeUnavailable)
def _unavailable(request, exc):
    return JSONResponse(status_code=503, content={"detail": "cluster indisponible (aucun nœud joignable ou pas de quorum)"})


@app.exception_handler(TooManyConflicts)
def _conflicts(request, exc):
    return JSONResponse(status_code=503, content={"detail": "trop de conflits de concurrence, réessayez"})


@app.get("/health")
def health():
    _, _, node = run_tx(lambda c: c.execute("SELECT 1").fetchone())
    return {"status": "ok", "node": node}


# ---------- Inscription d'un client (fragment = région) ----------
@app.post("/clients", status_code=201)
def creer_client(c: ClientIn):
    def tx(conn):
        return conn.execute(
            "INSERT INTO clients (region, nom, email) VALUES (%s, %s, %s) RETURNING client_id",
            (c.region, c.nom, c.email)).fetchone()[0]
    client_id, _, node = run_tx(tx, region=c.region)   # routé vers le nœud de la région
    return {"client_id": client_id, "region": c.region, "node": node}


# ---------- Création d'un produit + stock initial (une seule transaction) ----------
@app.post("/produits", status_code=201)
def creer_produit(p: ProduitIn):
    def tx(conn):
        pid = conn.execute("INSERT INTO produits (nom, prix) VALUES (%s, %s) RETURNING product_id",
                           (p.nom, p.prix)).fetchone()[0]
        conn.execute("INSERT INTO stock (product_id, qty) VALUES (%s, %s)", (pid, p.stock))
        return pid
    pid, _, node = run_tx(tx)
    return {"product_id": pid, "node": node}


# ---------- Catalogue : lecture distribuée ----------
@app.get("/produits")
def catalogue(limit: int = 100):
    def tx(conn):
        rows = conn.execute(
            "SELECT p.product_id, p.nom, p.prix, s.qty FROM produits p "
            "JOIN stock s USING (product_id) ORDER BY p.nom LIMIT %s", (limit,)).fetchall()
        return [{"product_id": r[0], "nom": r[1], "prix": r[2], "stock": r[3]} for r in rows]
    res, _, node = run_tx(tx)
    return {"node": node, "produits": res}


@app.get("/stock/{product_id}")
def lire_stock(product_id: UUID):
    r, _, node = run_tx(lambda c: c.execute("SELECT qty FROM stock WHERE product_id = %s", (product_id,)).fetchone())
    if r is None:
        return JSONResponse(status_code=404, content={"detail": "produit inconnu"})
    return {"product_id": product_id, "stock": r[0], "node": node}


@app.get("/produits/{product_id}/ventes")
def ventes(product_id: UUID):
    """Nombre de commandes confirmées + stock courant (sert aux vérifications d'intégrité)."""
    def tx(conn):
        n = conn.execute("SELECT count(*) FROM commandes WHERE product_id = %s AND statut = 'confirmee'",
                         (product_id,)).fetchone()[0]
        q = conn.execute("SELECT qty FROM stock WHERE product_id = %s", (product_id,)).fetchone()
        return n, (q[0] if q else None)
    (n, q), _, node = run_tx(tx)
    return {"commandes_confirmees": n, "stock": q, "node": node}


@app.get("/commandes/{region}/{client_id}")
def mes_commandes(region: Region, client_id: UUID):
    """Lecture locale à un fragment : toutes les commandes d'un client."""
    def tx(conn):
        rows = conn.execute("SELECT order_id, product_id, quantite, statut, created_at FROM commandes "
                            "WHERE region = %s AND client_id = %s ORDER BY created_at DESC LIMIT 100",
                            (region, client_id)).fetchall()
        return [{"order_id": r[0], "product_id": r[1], "quantite": r[2], "statut": r[3], "created_at": r[4]} for r in rows]
    res, _, node = run_tx(tx, region=region)
    return {"node": node, "commandes": res}


# ---------- Passage d'une commande : transaction distribuée anti-survente ----------
@app.post("/commandes")
def passer_commande(c: CommandeIn):
    req_id = c.request_id or uuid4()

    def tx(conn):
        # 1) idempotence : une commande déjà enregistrée avec cette clé n'est pas rejouée
        row = conn.execute("SELECT order_id FROM commandes WHERE request_id = %s", (req_id,)).fetchone()
        if row:
            return "DUPLICATE", row[0]
        prod = conn.execute("SELECT prix FROM produits WHERE product_id = %s", (c.product_id,)).fetchone()
        if prod is None:
            return "NO_PRODUCT", None
        # 2) décrément conditionnel ATOMIQUE : la condition qty >= n empêche toute survente
        cur = conn.execute("UPDATE stock SET qty = qty - %s WHERE product_id = %s AND qty >= %s",
                           (c.quantite, c.product_id, c.quantite))
        if cur.rowcount == 0:
            return "RUPTURE", None
        # 3) commande + facture dans la même transaction (tout ou rien)
        oid = conn.execute(
            "INSERT INTO commandes (region, client_id, product_id, quantite, request_id) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING order_id",
            (c.region, c.client_id, c.product_id, c.quantite, req_id)).fetchone()[0]
        conn.execute("INSERT INTO factures (region, client_id, order_id, montant) VALUES (%s, %s, %s, %s)",
                     (c.region, c.client_id, oid, prod[0] * c.quantite))
        return "OK", oid

    try:
        (status, oid), retries, node = run_tx(tx, region=c.region)
    except errors.ForeignKeyViolation:
        return JSONResponse(status_code=404, content={"detail": "client inconnu"})
    except errors.UniqueViolation:   # même request_id exécuté en parallèle : déjà pris en compte
        return JSONResponse(status_code=200, content={"status": "duplicate", "retries": 0})

    body = {"retries": retries, "node": node}
    if status == "OK":
        return JSONResponse(status_code=201, content={**body, "status": "ok", "order_id": str(oid)})
    if status == "DUPLICATE":
        return JSONResponse(status_code=200, content={**body, "status": "duplicate", "order_id": str(oid)})
    if status == "RUPTURE":
        return JSONResponse(status_code=409, content={**body, "status": "rupture", "detail": "rupture de stock"})
    return JSONResponse(status_code=404, content={**body, "detail": "produit inconnu"})
