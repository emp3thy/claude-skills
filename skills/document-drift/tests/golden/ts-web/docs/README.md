# web

The browser front end for the service.

Requires Node >= 18.

## Source map

- `src/main.tsx` mounts the app
- `src/api/httpClient.ts` wraps fetch with retries
- `src/App.tsx` lays out the page

Shared helpers live in `src/helpers/`.

## Background jobs

- `src/workers/sync_worker.ts` syncs drafts while offline

## Scripts

```bash
npm install
npm run dev
npm run build
```

The front-end guide is in [docs/frontend.md](docs/frontend.md).
