using Deals.Api.Data;
using Deals.Api.Messaging;
using Deals.Api.Validators;

namespace Deals.Api.Services;

public class DealService
{
    private readonly DealsDbContext _db;
    private readonly PricingClient _pricing;
    private readonly DealPublisher _publisher;

    public DealService(DealsDbContext db, PricingClient pricing, DealPublisher publisher)
    {
        _db = db;
        _pricing = pricing;
        _publisher = publisher;
    }

    public async Task<Deal> CreateAsync(DealRequest request)
    {
        if (request.Quantity > 10000)
        {
            throw new InvalidOperationException("quantity exceeds the 10000 limit");
        }
        var price = await _pricing.PriceAsync(request.Currency);
        var deal = new Deal
        {
            ExternalId = request.ExternalId,
            Currency = request.Currency,
            Quantity = request.Quantity,
            Price = price,
        };
        _db.Deals.Add(deal);
        await _db.SaveChangesAsync();
        _publisher.Send("deal.created", new { id = deal.Id, externalId = deal.ExternalId,
                                              status = deal.Status });
        return deal;
    }

    public Task<Deal?> FindAsync(Guid id) =>
        Task.FromResult(_db.Deals.FirstOrDefault(d => d.Id == id));
}
