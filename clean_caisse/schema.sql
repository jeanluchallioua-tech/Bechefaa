CREATE TABLE IF NOT EXISTS caisse_clients (
    id TEXT PRIMARY KEY,
    first_name TEXT NOT NULL DEFAULT '',
    last_name TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    postal_code TEXT NOT NULL DEFAULT '',
    city TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS caisse_orders (
    id TEXT PRIMARY KEY,
    num BIGINT NOT NULL UNIQUE,
    customer_id TEXT NULL REFERENCES caisse_clients(id),
    customer_name TEXT NOT NULL DEFAULT 'Client comptoir',
    phone TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    postal_code TEXT NOT NULL DEFAULT '',
    city TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'CAISSE',
    payment TEXT NOT NULL DEFAULT 'À ENCAISSER',
    status TEXT NOT NULL DEFAULT 'À préparer',
    total NUMERIC(12,2) NOT NULL DEFAULT 0,
    modification_flag BOOLEAN NOT NULL DEFAULT FALSE,
    change_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL,
    modified_at BIGINT NULL
);

CREATE TABLE IF NOT EXISTS caisse_order_items (
    id BIGSERIAL PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES caisse_orders(id) ON DELETE CASCADE,
    line_id TEXT NOT NULL,
    product_id TEXT NULL,
    name TEXT NOT NULL,
    qty INTEGER NOT NULL CHECK (qty > 0),
    unit_price NUMERIC(12,2) NOT NULL DEFAULT 0,
    options_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    options_text TEXT NOT NULL DEFAULT '',
    prepared BOOLEAN NOT NULL DEFAULT FALSE,
    position INTEGER NOT NULL DEFAULT 0,
    UNIQUE(order_id, line_id)
);

CREATE INDEX IF NOT EXISTS idx_caisse_orders_created_at ON caisse_orders(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_caisse_orders_status ON caisse_orders(status);
CREATE INDEX IF NOT EXISTS idx_caisse_orders_customer_id ON caisse_orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_caisse_clients_phone ON caisse_clients(phone);
CREATE INDEX IF NOT EXISTS idx_caisse_order_items_order_id ON caisse_order_items(order_id);
