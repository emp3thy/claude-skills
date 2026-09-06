using System.Net.Http.Json;

namespace Deals.Api.Services;

public class PricingClient
{
    private readonly HttpClient _client;

    public PricingClient(HttpClient client)
    {
        _client = client;
    }

    public async Task<decimal> PriceAsync(string currency)
    {
        var quote = await _client.GetFromJsonAsync<Quote>($"/quotes/{currency}");
        return quote?.Price ?? 0m;
    }

    private sealed record Quote(decimal Price);
}
