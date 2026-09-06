using Deals.Api.Data;
using Deals.Api.Messaging;
using Deals.Api.Services;
using Deals.Api.Validators;
using FluentValidation;
using FluentValidation.AspNetCore;
using Microsoft.EntityFrameworkCore;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddControllers();
builder.Services.AddHealthChecks();
builder.Services.AddFluentValidationAutoValidation();
builder.Services.AddScoped<IValidator<DealRequest>, DealRequestValidator>();
builder.Services.AddDbContext<DealsDbContext>(options =>
    options.UseNpgsql(builder.Configuration.GetConnectionString("Deals")));
builder.Services.AddHttpClient<PricingClient>(client =>
{
    // A trailing slash is required: HttpClient resolves a relative request URI against
    // BaseAddress by RFC 3986 reference resolution, which drops the whole BaseAddress path
    // (not just its last segment) once the relative URI itself starts with "/" (see
    // PricingClient.PriceAsync, which uses a path with no leading slash to match).
    var baseUrl = builder.Configuration["Pricing:BaseUrl"]!;
    client.BaseAddress = new Uri(baseUrl.EndsWith('/') ? baseUrl : baseUrl + "/");
});
builder.Services.AddSingleton<DealPublisher>();
builder.Services.AddScoped<DealService>();
builder.Services.AddHostedService<DealRequestedConsumer>();

var app = builder.Build();
app.MapControllers();
app.MapHealthChecks("/health/ready");
app.Run();
