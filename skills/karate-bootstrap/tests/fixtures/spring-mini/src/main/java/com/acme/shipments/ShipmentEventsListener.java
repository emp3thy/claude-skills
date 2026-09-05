package com.acme.shipments;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class ShipmentEventsListener {
    private final ShipmentRepository repository;

    public ShipmentEventsListener(ShipmentRepository repository) {
        this.repository = repository;
    }

    @JmsListener(destination = "shipment.requested")
    public void onRequested(ShipmentRequest request) {
        repository.save(Shipment.from(request, null));
    }
}
