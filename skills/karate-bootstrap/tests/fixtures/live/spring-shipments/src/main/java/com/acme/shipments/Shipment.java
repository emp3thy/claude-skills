package com.acme.shipments;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.util.UUID;

@Entity
@Table(name = "shipments")
public class Shipment {
    @Id
    @GeneratedValue
    private UUID id;
    @Column(name = "reference", nullable = false, unique = true)
    private String reference;
    @Column(name = "country_code", nullable = false)
    private String countryCode;
    @Column(name = "weight_kg", nullable = false)
    private double weightKg;
    @Column(name = "destination", nullable = false)
    private String destination;
    @Column(name = "status", nullable = false)
    private String status;
    @Column(name = "rate", nullable = false)
    private double rate;

    public UUID getId() {
        return id;
    }

    public String getReference() {
        return reference;
    }

    public void setReference(String reference) {
        this.reference = reference;
    }

    public String getCountryCode() {
        return countryCode;
    }

    public void setCountryCode(String countryCode) {
        this.countryCode = countryCode;
    }

    public double getWeightKg() {
        return weightKg;
    }

    public void setWeightKg(double weightKg) {
        this.weightKg = weightKg;
    }

    public String getDestination() {
        return destination;
    }

    public void setDestination(String destination) {
        this.destination = destination;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public double getRate() {
        return rate;
    }

    public void setRate(double rate) {
        this.rate = rate;
    }
}
