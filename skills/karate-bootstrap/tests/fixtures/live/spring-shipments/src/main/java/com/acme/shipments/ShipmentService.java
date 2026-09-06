package com.acme.shipments;

import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

@Service
public class ShipmentService {
    private final ShipmentRepository repository;
    private final RestTemplate restTemplate;
    private final JmsTemplate jmsTemplate;
    private final String pricingBaseUrl;

    public ShipmentService(ShipmentRepository repository, RestTemplate restTemplate,
                           JmsTemplate jmsTemplate,
                           @Value("${pricing.base-url}") String pricingBaseUrl) {
        this.repository = repository;
        this.restTemplate = restTemplate;
        this.jmsTemplate = jmsTemplate;
        this.pricingBaseUrl = pricingBaseUrl;
    }

    public Optional<Shipment> find(UUID id) {
        return repository.findById(id);
    }

    @SuppressWarnings("unchecked")
    public Shipment create(ShipmentRequest request) {
        if (request.getWeightKg() > 1000) {
            throw new IllegalArgumentException("weight exceeds 1000kg");
        }
        Map<String, Object> rate = restTemplate.getForObject(
            pricingBaseUrl + "/rates/" + request.getCountryCode(), Map.class);
        Shipment shipment = new Shipment();
        shipment.setReference(request.getReference());
        shipment.setCountryCode(request.getCountryCode());
        shipment.setWeightKg(request.getWeightKg());
        shipment.setDestination(request.getDestination());
        shipment.setStatus("PENDING");
        shipment.setRate(rate == null ? 0d : ((Number) rate.getOrDefault("rate", 0)).doubleValue());
        Shipment saved = repository.save(shipment);
        jmsTemplate.convertAndSend("shipment.created", Map.of(
            "id", saved.getId().toString(), "reference", saved.getReference(),
            "status", saved.getStatus()));
        return saved;
    }
}
