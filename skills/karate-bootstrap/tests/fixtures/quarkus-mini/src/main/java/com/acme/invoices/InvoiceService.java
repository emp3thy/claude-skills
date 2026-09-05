package com.acme.invoices;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import jakarta.transaction.Transactional;
import org.eclipse.microprofile.reactive.messaging.Channel;
import org.eclipse.microprofile.reactive.messaging.Emitter;
import org.eclipse.microprofile.rest.client.inject.RestClient;

@ApplicationScoped
public class InvoiceService {
    @Inject
    @Channel("invoice-created")
    Emitter<InvoiceEvent> emitter;

    @Inject
    @RestClient
    OrdersClient ordersClient;

    @Transactional
    public Invoice create(InvoiceRequest request) {
        Order order = ordersClient.getOrder(request.orderId);
        if (order == null) {
            throw new NotFoundException("order " + request.orderId);
        }
        Invoice invoice = Invoice.from(request, order);
        invoice.persist();
        emitter.send(InvoiceEvent.of(invoice));
        return invoice;
    }

    public Invoice find(Long id) {
        return Invoice.findById(id);
    }
}
