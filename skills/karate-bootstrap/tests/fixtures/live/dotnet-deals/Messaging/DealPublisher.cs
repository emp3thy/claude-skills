using System.Text.Json;
using Apache.NMS;
using Apache.NMS.AMQP;

namespace Deals.Api.Messaging;

/// <summary>AMQP 1.0 to Artemis, the protocol the harness listens on.</summary>
public class DealPublisher : IDisposable
{
    private readonly IConnection _connection;

    public DealPublisher(IConfiguration configuration)
    {
        var factory = new NmsConnectionFactory(configuration["Amq:Url"]);
        _connection = factory.CreateConnection(configuration["Amq:User"],
                                               configuration["Amq:Password"]);
        _connection.Start();
    }

    public void Send(string destination, object body)
    {
        using var session = _connection.CreateSession(AcknowledgementMode.AutoAcknowledge);
        using var producer = session.CreateProducer(session.GetQueue(destination));
        producer.Send(session.CreateTextMessage(JsonSerializer.Serialize(body)));
    }

    public IConnection Connection => _connection;

    public void Dispose()
    {
        _connection.Dispose();
        GC.SuppressFinalize(this);
    }
}
