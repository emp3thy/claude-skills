using Microsoft.AspNetCore.Mvc;

namespace Deals.Api.Controllers;

[ApiController]
[Route("api/[controller]")]
public class DealsController : ControllerBase
{
    private readonly DealService _service;

    public DealsController(DealService service) => _service = service;

    [HttpPost]
    public async Task<ActionResult<Deal>> Create(DealRequest request)
    {
        var deal = await _service.CreateAsync(request);
        return CreatedAtAction(nameof(Get), new { id = deal.Id }, deal);
    }

    [HttpGet("{id:guid}")]
    public async Task<ActionResult<Deal>> Get(Guid id)
    {
        var deal = await _service.FindAsync(id);
        return deal is null ? NotFound() : Ok(deal);
    }
}
