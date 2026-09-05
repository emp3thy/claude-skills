using System.ComponentModel.DataAnnotations.Schema;

namespace Deals.Api.Data;

[Table("deals")]
public class Deal
{
    public Guid Id { get; set; }
    public string CounterpartyId { get; set; } = "";
    public decimal Volume { get; set; }
    public string Product { get; set; } = "";
    public string ExternalId { get; set; } = "";

    public static Deal From(DealRequest request, Price? price) => new();
    public static Deal FromMessage(Apache.NMS.IMessage message) => new();
    public string ToEventJson() => "{}";
}
