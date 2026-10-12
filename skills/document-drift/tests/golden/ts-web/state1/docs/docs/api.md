# API

## Routes

| Route | Returns |
|---|---|
| `GET /api/items` | One page of items. |
| `GET /api/items/{id}` | One item. |

## Client

The client asks for 50 items per page by default (`PAGE_SIZE`).

`fetchItems` loads one page of items, and `fetchItem` loads one item by its id.
