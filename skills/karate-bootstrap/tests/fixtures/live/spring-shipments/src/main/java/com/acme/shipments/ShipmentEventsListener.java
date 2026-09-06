package com.acme.shipments;

import java.util.Map;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class ShipmentEventsListener {
    private final ShipmentRepository repository;

    public ShipmentEventsListener(ShipmentRepository repository) {
        this.repository = repository;
    }

    @JmsListener(destination = "shipment.requested")
    public void onRequested(Map<String, Object> message) {
        Shipment shipment = new Shipment();
        shipment.setReference(String.valueOf(message.get("reference")));
        shipment.setCountryCode(String.valueOf(message.getOrDefault("countryCode", "GB")));
        shipment.setWeightKg(Double.parseDouble(String.valueOf(
            message.getOrDefault("weightKg", "1"))));
        shipment.setDestination(String.valueOf(message.getOrDefault("destination", "queued")));
        shipment.setStatus("QUEUED");
        shipment.setRate(0d);
        repository.save(shipment);
    }
}
