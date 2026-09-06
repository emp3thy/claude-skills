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
        // Yield before touching the broker: BackgroundService.StartAsync inspects whether this
        // task is already completed to decide whether it must be awaited, so any exception
        // thrown synchronously here (a connection attempt failing fast) would otherwise fault
        // that check and abort the whole host's startup before Kestrel ever binds.
        await Task.Yield();
        var mode = AcknowledgementMode.AutoAcknowledge;
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
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
            catch (Exception) when (!stoppingToken.IsCancellationRequested)
            {
                // The broker may not be reachable yet (container start ordering); retry rather
                // than let BackgroundServiceExceptionBehavior.StopHost tear down the app.
                await Task.Delay(TimeSpan.FromSeconds(2), stoppingToken);
            }
        }
    }
}
