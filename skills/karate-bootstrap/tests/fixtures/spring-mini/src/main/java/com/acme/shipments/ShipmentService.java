package com.acme.shipments;

import java.math.BigDecimal;
import java.util.Optional;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

@Service
public class ShipmentService {
    private final ShipmentRepository repository;
    private final JmsTemplate jmsTemplate;
    private final RestTemplate restTemplate;

    @Value("${pricing.base-url}")
    private String pricingBaseUrl;

    public ShipmentService(ShipmentRepository repository, JmsTemplate jmsTemplate, RestTemplate restTemplate) {
        this.repository = repository;
        this.jmsTemplate = jmsTemplate;
        this.restTemplate = restTemplate;
    }

    public Shipment create(ShipmentRequest request) {
        if (request.getWeightKg().compareTo(new BigDecimal("1000")) > 0) {
            throw new IllegalArgumentException("weight exceeds 1000kg");
        }
        Rate rate = restTemplate.getForObject(pricingBaseUrl + "/rates/" + request.getCountryCode(), Rate.class);
        Shipment shipment = Shipment.from(request, rate);
        repository.save(shipment);
        jmsTemplate.convertAndSend("shipment.created", shipment.toEvent());
        return shipment;
    }

    public Optional<Shipment> find(UUID id) {
        return repository.findById(id);
    }
}
