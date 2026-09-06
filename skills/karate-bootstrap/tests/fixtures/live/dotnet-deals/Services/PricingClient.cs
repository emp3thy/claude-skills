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
        // No leading slash: BaseAddress carries the downstream's "/pricing" path (kb_scaffold's
        // downstream env value), and only a relative path without a leading slash resolves
        // against it rather than replacing it (see the comment in Program.cs).
        var quote = await _client.GetFromJsonAsync<Quote>($"quotes/{currency}");
        return quote?.Price ?? 0m;
    }

    private sealed record Quote(decimal Price);
}
