using Apache.NMS;

namespace Deals.Api.Messaging;

public class DealRequestedConsumer : BackgroundService
{
    private readonly ISession _session;
    private readonly DealsDbContext _db;

    public DealRequestedConsumer(ISession session, DealsDbContext db)
    {
        _session = session;
        _db = db;
    }

    protected override Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var queue = _session.GetQueue("deal.requested");
        var consumer = _session.CreateConsumer(queue);
        consumer.Listener += OnMessage;
        return Task.CompletedTask;
    }

    private void OnMessage(IMessage message)
    {
        var deal = Deal.FromMessage(message);
        _db.Deals.Update(deal);
        _db.SaveChanges();
    }
}
