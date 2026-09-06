using System.Text.Json;
using Apache.NMS;
using Apache.NMS.AMQP;

namespace Deals.Api.Messaging;

/// <summary>
/// AMQP 1.0 to Artemis, the protocol the harness listens on. The connection is established
/// lazily on first use rather than in the constructor: this type is a singleton resolved as
/// soon as anything needs it, including <see cref="DealRequestedConsumer"/>'s hosted-service
/// constructor, which the generic host resolves synchronously before Kestrel starts listening.
/// A connection made eagerly there would block the whole host on the broker handshake and
/// could starve the readiness probe; connecting on first use keeps host startup off that path.
/// </summary>
public class DealPublisher : IDisposable
{
    private readonly IConfiguration _configuration;
    private readonly object _gate = new();
    private IConnection? _connection;

    public DealPublisher(IConfiguration configuration)
    {
        _configuration = configuration;
    }

    public IConnection Connection
    {
        get
        {
            lock (_gate)
            {
                if (_connection is null)
                {
                    var factory = new NmsConnectionFactory(_configuration["Amq:Url"]);
                    var connection = factory.CreateConnection(_configuration["Amq:User"],
                                                              _configuration["Amq:Password"]);
                    connection.Start();
                    _connection = connection;
                }
                return _connection;
            }
        }
    }

    public void Send(string destination, object body)
    {
        using var session = Connection.CreateSession(AcknowledgementMode.AutoAcknowledge);
        using var producer = session.CreateProducer(session.GetQueue(destination));
        producer.Send(session.CreateTextMessage(JsonSerializer.Serialize(body)));
    }

    public void Dispose()
    {
        _connection?.Dispose();
        GC.SuppressFinalize(this);
    }
}
