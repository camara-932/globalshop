CREATE DATABASE IF NOT EXISTS globalshop;
USE globalshop;

-- Réplication explicite : 3 copies par plage (quorum Raft = 2)
ALTER DATABASE globalshop CONFIGURE ZONE USING num_replicas = 3;

CREATE TABLE IF NOT EXISTS clients (
  region      STRING NOT NULL CHECK (region IN ('afrique','europe','amerique','asie')),
  client_id   UUID   NOT NULL DEFAULT gen_random_uuid(),
  nom         STRING NOT NULL,
  email       STRING NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (region, client_id)
);

CREATE TABLE IF NOT EXISTS produits (
  product_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nom         STRING NOT NULL,
  prix        DECIMAL(10,2) NOT NULL CHECK (prix >= 0)
);

CREATE TABLE IF NOT EXISTS stock (
  product_id  UUID PRIMARY KEY REFERENCES produits (product_id),
  qty         INT NOT NULL CHECK (qty >= 0)   -- filet de sécurité anti-survente
);

CREATE TABLE IF NOT EXISTS commandes (
  region      STRING NOT NULL,
  client_id   UUID   NOT NULL,
  order_id    UUID   NOT NULL DEFAULT gen_random_uuid(),
  product_id  UUID   NOT NULL REFERENCES produits (product_id),
  quantite    INT    NOT NULL CHECK (quantite > 0),
  statut      STRING NOT NULL DEFAULT 'confirmee',
  request_id  UUID   UNIQUE,                   -- clé d'idempotence (évite les doublons en cas de retry)
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (region, client_id, order_id),
  FOREIGN KEY (region, client_id) REFERENCES clients (region, client_id)
);
CREATE INDEX IF NOT EXISTS commandes_product_idx ON commandes (product_id);

CREATE TABLE IF NOT EXISTS factures (
  region      STRING NOT NULL,
  client_id   UUID   NOT NULL,
  order_id    UUID   NOT NULL,
  facture_id  UUID   NOT NULL DEFAULT gen_random_uuid(),
  montant     DECIMAL(12,2) NOT NULL,
  PRIMARY KEY (region, client_id, order_id, facture_id)
);
