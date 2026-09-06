CREATE TABLE orders (
    id uuid PRIMARY KEY,
    reference varchar(50) NOT NULL UNIQUE,
    sku varchar(20) NOT NULL,
    quantity integer NOT NULL,
    status varchar(20) NOT NULL,
    unit_price numeric(12, 2) NOT NULL DEFAULT 0
);
