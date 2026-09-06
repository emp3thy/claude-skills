CREATE TABLE deals (
    id uuid PRIMARY KEY,
    external_id varchar(64) NOT NULL UNIQUE,
    currency varchar(3) NOT NULL,
    quantity integer NOT NULL,
    status varchar(20) NOT NULL,
    price numeric(12, 2) NOT NULL DEFAULT 0
);
