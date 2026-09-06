namespace Deals.Api.Validators;

public class DealRequest
{
    public string ExternalId { get; set; } = string.Empty;
    public string Currency { get; set; } = string.Empty;
    public int Quantity { get; set; }
}
