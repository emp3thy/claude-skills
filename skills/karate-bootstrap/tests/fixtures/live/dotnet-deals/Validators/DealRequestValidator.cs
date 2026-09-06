using FluentValidation;

namespace Deals.Api.Validators;

public class DealRequestValidator : AbstractValidator<DealRequest>
{
    public DealRequestValidator()
    {
        RuleFor(r => r.ExternalId).NotEmpty().WithMessage("externalId is required");
        RuleFor(r => r.ExternalId).MaximumLength(64).WithMessage("externalId must be at most 64");
        RuleFor(r => r.Currency).Matches("^[A-Z]{3}$").WithMessage("currency must match [A-Z]{3}");
        RuleFor(r => r.Quantity).GreaterThan(0).WithMessage("quantity must be positive");
    }
}
