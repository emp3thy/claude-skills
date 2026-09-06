using Deals.Api.Data;
using Deals.Api.Services;
using Deals.Api.Validators;
using Microsoft.AspNetCore.Mvc;

namespace Deals.Api.Controllers;

[ApiController]
[Route("api/deals")]
public class DealsController : ControllerBase
{
    private readonly DealService _service;

    public DealsController(DealService service)
    {
        _service = service;
    }

    [HttpPost]
    public async Task<ActionResult<Deal>> Create([FromBody] DealRequest request)
    {
        var deal = await _service.CreateAsync(request);
        return StatusCode(StatusCodes.Status201Created, deal);
    }

    [HttpGet("{id:guid}")]
    public async Task<ActionResult<Deal>> Get(Guid id)
    {
        var deal = await _service.FindAsync(id);
        return deal is null ? NotFound() : Ok(deal);
    }
}
