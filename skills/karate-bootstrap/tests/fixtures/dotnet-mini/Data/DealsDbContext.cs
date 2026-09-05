using Microsoft.EntityFrameworkCore;

namespace Deals.Api.Data;

public class DealsDbContext : DbContext
{
    public DealsDbContext(DbContextOptions<DealsDbContext> options) : base(options) { }

    public DbSet<Deal> Deals => Set<Deal>();
}
