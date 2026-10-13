# Usage

## Options

The command line options are parsed in `options.go`.

The environment is read in `env.go`.

## Behaviour

- A run reads every tracked markdown file.
- Files outside the repository are not read.
- Each doc is compared with the code it describes.
- Lines inside code fences are skipped.
- A doc that names nothing is reported as unverifiable.
- Findings are sorted by file and line.
- Each finding carries the line it came from.
- The report lists the files it could not read.
- An empty repository gives an empty report.
- A repository without docs exits with a message.
- Symbolic links are followed once.
- Hidden directories are skipped.
- Binary files are skipped.
- Files over one megabyte are skipped.
- The report ends with a count of findings.
- Colours are used only on a terminal.
- A second run over an unchanged tree prints the same report.
- Interrupting a run leaves no partial report.
- The exit code is zero when nothing drifted.
- The exit code is one when a finding was reported.
