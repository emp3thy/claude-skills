package com.acme.invoices;

import jakarta.inject.Inject;
import jakarta.validation.Valid;
import jakarta.ws.rs.*;
import jakarta.ws.rs.core.Response;

@Path("/api/invoices")
public class InvoiceResource {
    @Inject
    InvoiceService service;

    @POST
    public Response create(@Valid InvoiceRequest request) {
        return Response.status(201).entity(service.create(request)).build();
    }

    @GET
    @Path("/{id}")
    public Invoice get(@PathParam("id") Long id) {
        return service.find(id);
    }
}
