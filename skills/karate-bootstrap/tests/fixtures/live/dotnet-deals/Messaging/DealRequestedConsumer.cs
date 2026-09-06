using System.Text.Json;
using Apache.NMS;
using Deals.Api.Data;

namespace Deals.Api.Messaging;

public class DealRequestedConsumer : BackgroundService
{
    private readonly DealPublisher _publisher;
    private readonly IServiceScopeFactory _scopes;

    public DealRequestedConsumer(DealPublisher publisher, IServiceScopeFactory scopes)
    {
        _publisher = publisher;
        _scopes = scopes;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var mode = AcknowledgementMode.AutoAcknowledge;
        using var session = _publisher.Connection.CreateSession(mode);
        using var consumer = session.CreateConsumer(session.GetQueue("deal.requested"));
        while (!stoppingToken.IsCancellationRequested)
        {
            if (consumer.Receive(TimeSpan.FromSeconds(1)) is not ITextMessage message)
            {
                continue;
            }
            var body = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(message.Text);
            using var scope = _scopes.CreateScope();
            var db = scope.ServiceProvider.GetRequiredService<DealsDbContext>();
            db.Deals.Add(new Deal
            {
                ExternalId = body!["externalId"].GetString() ?? string.Empty,
                Currency = "GBP",
                Quantity = 1,
                Status = "QUEUED",
            });
            await db.SaveChangesAsync(stoppingToken);
        }
    }
}
