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
    client.BaseAddress = new Uri(builder.Configuration["Pricing:BaseUrl"]!));
builder.Services.AddSingleton<DealPublisher>();
builder.Services.AddScoped<DealService>();
builder.Services.AddHostedService<DealRequestedConsumer>();

var app = builder.Build();
app.MapControllers();
app.MapHealthChecks("/health/ready");
app.Run();
