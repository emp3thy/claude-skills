# Legacy behaviour

<!-- drift-unverified: 1st notice, run 2026-01-02-4e1d, block 20d485bd. This describes the code but names nothing in it. Name what it describes, or add drift-ignore: <reason>. -->
Old reports listed findings in the order the files were read, so two runs over one tree could disagree.

The first versions wrote the report to standard error, which made it awkward to pipe.

Settings from the old configuration file still apply when no command line option overrides them.

A doc with no headings is treated as a single section.
