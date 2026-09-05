using System.Net.Http.Json;
using Apache.NMS;

namespace Deals.Api.Services;

public class DealService
{
    private readonly DealsDbContext _db;
    private readonly HttpClient _http;
    private readonly IMessageProducer _producer;

    public DealService(DealsDbContext db, HttpClient http, IMessageProducer producer)
    {
        _db = db;
        _http = http;
        _producer = producer;
    }

    public async Task<Deal> CreateAsync(DealRequest request)
    {
        if (request.Volume > 1_000_000)
        {
            throw new InvalidOperationException("volume exceeds desk limit");
        }
        var price = await _http.GetFromJsonAsync<Price>($"/prices/{request.Product}");
        var deal = Deal.From(request, price);
        _db.Deals.Add(deal);
        await _db.SaveChangesAsync();
        _producer.Send(_producer.CreateTextMessage(deal.ToEventJson()));
        return deal;
    }

    public Task<Deal?> FindAsync(Guid id) => _db.Deals.FindAsync(id).AsTask();
}
