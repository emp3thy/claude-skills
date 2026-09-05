var builder = WebApplication.CreateBuilder(args);
builder.Services.AddControllers();
builder.Services.AddDbContext<DealsDbContext>(o => o.UseNpgsql(builder.Configuration.GetConnectionString("Deals")));
if (builder.Configuration.GetValue<bool>("Auth:Enabled"))
{
    builder.Services.AddAuthentication().AddJwtBearer(o => o.Authority = builder.Configuration["Auth:Authority"]);
}
var app = builder.Build();
app.MapHealthChecks("/health/ready");
app.MapControllers();
app.Run();
