package com.acme.invoices;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.transaction.Transactional;
import org.eclipse.microprofile.reactive.messaging.Incoming;

@ApplicationScoped
public class OrderEventsConsumer {
    @Incoming("order-completed")
    @Transactional
    public void onOrderCompleted(OrderCompleted event) {
        Invoice invoice = Invoice.findById(event.invoiceId);
        invoice.currency = event.currency;
        invoice.persist();
    }
}
