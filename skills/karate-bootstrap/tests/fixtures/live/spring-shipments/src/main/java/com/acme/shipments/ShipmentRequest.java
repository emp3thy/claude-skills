package com.acme.shipments;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

public class ShipmentRequest {
    @NotBlank(message = "reference is required")
    @Size(max = 50, message = "reference must be at most 50")
    private String reference;
    @Positive(message = "weight must be positive")
    private double weightKg;
    @NotBlank(message = "countryCode is required")
    @Pattern(regexp = "[A-Z]{2}", message = "countryCode must match [A-Z]{2}")
    private String countryCode;
    @NotBlank(message = "destination is required")
    @Size(min = 3, max = 120, message = "destination must be 3 to 120 characters")
    private String destination;

    public String getReference() {
        return reference;
    }

    public void setReference(String reference) {
        this.reference = reference;
    }

    public double getWeightKg() {
        return weightKg;
    }

    public void setWeightKg(double weightKg) {
        this.weightKg = weightKg;
    }

    public String getCountryCode() {
        return countryCode;
    }

    public void setCountryCode(String countryCode) {
        this.countryCode = countryCode;
    }

    public String getDestination() {
        return destination;
    }

    public void setDestination(String destination) {
        this.destination = destination;
    }
}
