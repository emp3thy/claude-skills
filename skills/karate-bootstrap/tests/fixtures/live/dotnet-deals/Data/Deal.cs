namespace Deals.Api.Data;

public class Deal
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public string ExternalId { get; set; } = string.Empty;
    public string Currency { get; set; } = string.Empty;
    public int Quantity { get; set; }
    public string Status { get; set; } = "PENDING";
    public decimal Price { get; set; }
}
