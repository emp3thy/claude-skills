"""Per-stack source markers shared by discover.py, flow_map.py and rules.py.

Each stack has one or more ``Marker`` per kind:

  entry-http   route declarations (group 1 = method, group 2 = path where the
               framework puts it on the same line; Quarkus paths come from a
               separate ``@Path`` line that discover.py resolves)
  entry-amq    message-listener declarations (group 1.. = destination)
  db-write     ORM or SQL write calls
  amq-publish  message-send calls
  http-out     outbound HTTP client use
  validation   declarative validation constraints

``tokens`` are plain substrings ``flow_map.py verify-refs`` accepts on or near
a ``via: file:line`` reference. They are deliberately looser than the regex so
a subagent's exit reference survives small formatting differences.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from kb_common import EXIT_UNSUPPORTED_STACK, KbError

STACKS: Final[tuple[str, ...]] = ("spring", "quarkus", "aspnetcore", "python")
KINDS: Final[tuple[str, ...]] = (
    "entry-http",
    "entry-amq",
    "db-write",
    "amq-publish",
    "http-out",
    "validation",
)

SOURCE_SUFFIXES: Final[dict[str, tuple[str, ...]]] = {
    "spring": (".java", ".kt"),
    "quarkus": (".java", ".kt"),
    "aspnetcore": (".cs",),
    "python": (".py",),
}

CHEAT_SHEET: Final[dict[str, str]] = {
    "spring": "reference/stack-spring.md",
    "quarkus": "reference/stack-quarkus.md",
    "aspnetcore": "reference/stack-aspnetcore.md",
    "python": "reference/stack-python.md",
}


@dataclass(frozen=True)
class Marker:
    kind: str
    pattern: re.Pattern[str]
    tokens: tuple[str, ...]


def _m(kind: str, pattern: str, *tokens: str) -> Marker:
    return Marker(kind, re.compile(pattern), tokens)


_BEAN_VALIDATION = (
    r"@(NotNull|NotBlank|NotEmpty|Size|Min|Max|DecimalMin|DecimalMax|Pattern|Email|"
    r"Positive|PositiveOrZero|Negative|NegativeOrZero|Past|Future|Digits|AssertTrue)\b"
)
_BEAN_TOKENS = (
    "@NotNull", "@NotBlank", "@NotEmpty", "@Size", "@Min", "@Max", "@DecimalMin",
    "@DecimalMax", "@Pattern", "@Email", "@Positive", "@Negative", "@Past", "@Future",
    "@Digits", "@AssertTrue",
)

MARKERS: Final[dict[str, tuple[Marker, ...]]] = {
    "spring": (
        _m(
            "entry-http",
            r'@(Get|Post|Put|Delete|Patch)Mapping\b'
            r'(?:\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?"([^"]*)")?',
            "Mapping",
        ),
        _m("entry-amq", r'@JmsListener\s*\(\s*destination\s*=\s*"([^"]+)"', "@JmsListener"),
        _m(
            "db-write",
            r"\.(save|saveAll|saveAndFlush|delete|deleteById|deleteAll|deleteAllById|persist|"
            r"merge|remove)\s*\(|@Modifying|jdbcTemplate\.(update|batchUpdate)\s*\(",
            ".save(", ".saveAll(", ".saveAndFlush(", ".delete", ".persist(", ".merge(",
            ".remove(", "@Modifying", "jdbcTemplate.update(", "jdbcTemplate.batchUpdate(",
        ),
        _m(
            "amq-publish",
            r"\.(convertAndSend|send)\s*\(",
            "convertAndSend(", ".send(",
        ),
        _m(
            "http-out",
            r"restTemplate\.|\bRestTemplate\b|\bWebClient\b|webClient\.|@FeignClient|\bRestClient\b",
            "restTemplate.", "RestTemplate", "WebClient", "webClient.", "@FeignClient",
            "RestClient",
        ),
        _m("validation", _BEAN_VALIDATION, *_BEAN_TOKENS),
    ),
    "quarkus": (
        _m("entry-http", r"@(GET|POST|PUT|DELETE|PATCH)\b", "@GET", "@POST", "@PUT",
           "@DELETE", "@PATCH"),
        _m("entry-amq", r'@Incoming\s*\(\s*"([^"]+)"', "@Incoming"),
        _m(
            "db-write",
            r"\.(persist|persistAndFlush|delete|deleteById|deleteAll|merge|remove)\s*\(|"
            r"\.update\s*\(\s*\"",
            ".persist(", ".persistAndFlush(", ".delete(", ".deleteById(", ".deleteAll(",
            ".merge(", ".remove(", ".update(",
        ),
        _m("amq-publish", r"\.send\s*\(|@Outgoing\s*\(", ".send(", "@Outgoing("),
        _m(
            "http-out",
            r"@RestClient\b|RestClientBuilder|\bWebClient\b|Client\.\w+\s*\(",
            "@RestClient", "RestClientBuilder", "WebClient", "Client.",
        ),
        _m("validation", _BEAN_VALIDATION, *_BEAN_TOKENS),
    ),
    "aspnetcore": (
        _m(
            "entry-http",
            r'\[Http(Get|Post|Put|Delete|Patch)(?:\s*\(\s*"([^"]*)"\s*\))?\]|'
            r'\.Map(Get|Post|Put|Delete|Patch)\s*\(\s*"([^"]+)"',
            "[Http", ".Map",
        ),
        _m(
            "entry-amq",
            r'GetQueue\s*\(\s*"([^"]+)"|GetTopic\s*\(\s*"([^"]+)"|'
            r'ReceiveEndpoint\s*\(\s*"([^"]+)"|IConsumer<(\w+)>',
            "GetQueue(", "GetTopic(", "ReceiveEndpoint(", "IConsumer<", "Listener +=",
        ),
        _m(
            "db-write",
            r"SaveChanges(Async)?\s*\(|\.(Add|AddAsync|AddRange|AddRangeAsync|Update|"
            r"UpdateRange|Remove|RemoveRange)\s*\(|ExecuteSql(Raw|Interpolated)|"
            r"ExecuteUpdate|ExecuteDelete",
            "SaveChanges", ".Add(", ".AddAsync(", ".AddRange(", ".Update(", ".Remove(",
            ".RemoveRange(", "ExecuteSql", "ExecuteUpdate", "ExecuteDelete",
        ),
        _m(
            "amq-publish",
            r"\.(Send|SendAsync|Publish|PublishAsync)\s*\(|CreateProducer\s*\(",
            ".Send(", ".SendAsync(", ".Publish(", ".PublishAsync(", "CreateProducer(",
        ),
        _m(
            "http-out",
            r"\bHttpClient\b|\.(GetAsync|PostAsync|PutAsync|DeleteAsync|SendAsync|"
            r"GetFromJsonAsync|PostAsJsonAsync|PutAsJsonAsync|GetStringAsync)\s*[<(]",
            "HttpClient", ".GetAsync(", ".PostAsync(", ".PutAsync(", ".DeleteAsync(",
            ".SendAsync(", "FromJsonAsync", "AsJsonAsync", "GetStringAsync(",
        ),
        _m(
            "validation",
            r"RuleFor\s*\(|\[(Required|StringLength|Range|RegularExpression|MaxLength|"
            r"MinLength|EmailAddress|Url|Phone|Compare)\b",
            "RuleFor(", "[Required", "[StringLength", "[Range", "[RegularExpression",
            "[MaxLength", "[MinLength", "[EmailAddress", "[Url", "[Phone", "[Compare",
        ),
    ),
    "python": (
        _m(
            "entry-http",
            r"@\w+\.(get|post|put|delete|patch)\s*\(\s*[\"']([^\"']+)[\"']|"
            r"@\w+\.route\s*\(\s*[\"']([^\"']+)[\"']",
            "@app.", "@router.", ".route(",
        ),
        _m(
            "entry-amq",
            r"create_receiver\s*\([^,]+,\s*[\"']([^\"']+)[\"']|"
            r"\.subscribe\s*\(\s*destination\s*=\s*[\"']([^\"']+)[\"']",
            "create_receiver(", ".subscribe(",
        ),
        _m(
            "db-write",
            r"session\.(add|add_all|delete|merge|commit|flush)\s*\(|"
            r"\.execute\s*\(\s*[\"'](INSERT|UPDATE|DELETE)|\.commit\s*\(",
            "session.add(", "session.add_all(", "session.delete(", "session.merge(",
            ".commit(", ".flush(", ".execute(",
        ),
        _m("amq-publish", r"\.send\s*\(|\.publish\s*\(", ".send(", ".publish("),
        _m(
            "http-out",
            r"\b(httpx|requests|aiohttp)\.|\bhttpx\.(Async)?Client\b",
            "httpx.", "requests.", "aiohttp.",
        ),
        _m(
            "validation",
            r"\bField\s*\(|@(field_)?validator\b|\b(constr|conint|confloat|conlist|condecimal)\s*\(",
            "Field(", "validator", "constr(", "conint(", "confloat(", "conlist(", "condecimal(",
        ),
    ),
}


def markers_for(stack: str) -> tuple[Marker, ...]:
    try:
        return MARKERS[stack]
    except KeyError as err:
        raise KbError(
            f"unsupported stack {stack!r}; expected one of {', '.join(STACKS)}",
            EXIT_UNSUPPORTED_STACK,
        ) from err


def markers_of_kind(stack: str, kind: str) -> tuple[Marker, ...]:
    return tuple(m for m in markers_for(stack) if m.kind == kind)


def tokens_for(stack: str, kind: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for marker in markers_of_kind(stack, kind):
        tokens.extend(marker.tokens)
    return tuple(tokens)
