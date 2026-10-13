# MCP tools

The service registers these tools with its MCP server:

- `store.put` saves a value.
- `store.get` reads a value.
- `store.delete` removes a value.

## `store.put`

Takes `key` and `value` and saves the value under the key.

## `store.get`

Takes `key` and returns the value saved under it, or nothing.

## Examples

- `store.get` with the key `greeting` returns the greeting saved earlier.
