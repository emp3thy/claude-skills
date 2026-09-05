package com.acme.shipments;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.util.UUID;

@Entity
@Table(name = "shipments")
public class Shipment {
    @Id
    private UUID id;
    private String reference;
    private String status;

    static Shipment from(ShipmentRequest request, Rate rate) {
        return new Shipment();
    }

    Object toEvent() {
        return this;
    }
}
