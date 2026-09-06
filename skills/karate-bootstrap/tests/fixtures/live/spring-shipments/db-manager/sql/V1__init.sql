CREATE TABLE shipments (
    id uuid PRIMARY KEY,
    reference varchar(50) NOT NULL UNIQUE,
    country_code varchar(2) NOT NULL,
    weight_kg double precision NOT NULL,
    destination varchar(120) NOT NULL,
    status varchar(20) NOT NULL,
    rate double precision NOT NULL DEFAULT 0
);
