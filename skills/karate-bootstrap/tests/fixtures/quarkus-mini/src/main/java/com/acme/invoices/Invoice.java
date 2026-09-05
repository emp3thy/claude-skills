package com.acme.invoices;

import io.quarkus.hibernate.orm.panache.PanacheEntity;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "invoices")
public class Invoice extends PanacheEntity {
    public Long orderId;
    public String currency;

    static Invoice from(InvoiceRequest request, Order order) {
        return new Invoice();
    }
}
