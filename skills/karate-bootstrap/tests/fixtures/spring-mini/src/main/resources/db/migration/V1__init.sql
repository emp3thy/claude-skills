create table shipments (id uuid primary key, reference varchar(50) not null, weight_kg numeric not null, country_code char(2) not null, status varchar(20) not null);
