# web

The browser front end and build tool for the item service; the landing page is [index.md](index.md).

## Configuration

The environment variables are listed in [docs/configuration.md](docs/configuration.md).

Set `FEATURE_FLAGS` to a comma-separated list to turn on experimental features.

## API

The server registers two routes in `src/server.ts`; [docs/api.md](docs/api.md) lists them.

## Command line

Run `web build` to bundle the app; [docs/cli.md](docs/cli.md) lists its flags.
