# Command line

The package's command line is `web`, defined in `src/cli.ts`.

| Command | What it does |
|---|---|
| `build` | Bundle the app into a directory. |
| `serve` | Serve the bundle locally. |

## `web build`

| Flag | Meaning |
|---|---|
| `--out-dir` | Directory to write the bundle to (default dist). |
| `--watch` | Rebuild when a source file changes. |
| `--sourcemap` | Write source maps next to the bundle. |
