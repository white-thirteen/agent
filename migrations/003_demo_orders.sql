CREATE TABLE demo_orders (
    order_id text PRIMARY KEY CHECK (char_length(order_id) BETWEEN 1 AND 128),
    owner_id text NOT NULL CHECK (char_length(owner_id) BETWEEN 1 AND 128),
    amount numeric(12,2) NOT NULL CHECK (amount > 0),
    currency text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    payment_status text NOT NULL CHECK (payment_status IN ('unpaid', 'paid')),
    is_refunded boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL,
    CHECK (NOT is_refunded OR payment_status = 'paid')
);
CREATE INDEX demo_orders_owner_created ON demo_orders
    (owner_id, created_at DESC, order_id DESC);
