package com.acme.invoices;

import jakarta.validation.constraints.*;
import java.math.BigDecimal;

public class InvoiceRequest {
    @NotNull
    public Long orderId;

    @NotNull
    @DecimalMin("0.01")
    public BigDecimal amount;

    @NotBlank
    @Size(max = 3)
    public String currency;
}
