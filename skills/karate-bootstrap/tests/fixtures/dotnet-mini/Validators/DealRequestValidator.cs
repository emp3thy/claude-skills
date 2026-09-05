using FluentValidation;

namespace Deals.Api.Validators;

public class DealRequestValidator : AbstractValidator<DealRequest>
{
    public DealRequestValidator()
    {
        RuleFor(x => x.CounterpartyId).NotEmpty();
        RuleFor(x => x.Volume).GreaterThan(0);
        RuleFor(x => x.Product).NotEmpty().MaximumLength(20);
        RuleFor(x => x.ExternalId).Matches("^EXT-[0-9]{6}$");
    }
}
