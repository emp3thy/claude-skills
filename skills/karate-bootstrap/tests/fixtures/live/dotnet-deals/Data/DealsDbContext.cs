using Microsoft.EntityFrameworkCore;

namespace Deals.Api.Data;

public class DealsDbContext : DbContext
{
    public DealsDbContext(DbContextOptions<DealsDbContext> options) : base(options)
    {
    }

    public DbSet<Deal> Deals => Set<Deal>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<Deal>().ToTable("deals");
        modelBuilder.Entity<Deal>().Property(d => d.ExternalId).HasColumnName("external_id");
        modelBuilder.Entity<Deal>().Property(d => d.Currency).HasColumnName("currency");
        modelBuilder.Entity<Deal>().Property(d => d.Quantity).HasColumnName("quantity");
        modelBuilder.Entity<Deal>().Property(d => d.Status).HasColumnName("status");
        modelBuilder.Entity<Deal>().Property(d => d.Price).HasColumnName("price");
        modelBuilder.Entity<Deal>().Property(d => d.Id).HasColumnName("id");
    }
}
