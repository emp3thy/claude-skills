package com.acme.shipments;

import jakarta.validation.constraints.*;
import java.math.BigDecimal;

public class ShipmentRequest {
    @NotBlank
    @Size(max = 50)
    private String reference;

    @NotNull
    @Positive
    private BigDecimal weightKg;

    @NotNull
    @Pattern(regexp = "^[A-Z]{2}$")
    private String countryCode;

    @Size(min = 3, max = 120)
    private String destination;
}
