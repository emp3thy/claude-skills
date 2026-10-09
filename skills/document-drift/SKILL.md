---
name: document-drift
description: Find and fix documentation drift in a repository's markdown docs - references to files, anchors, scripts and versions that no longer exist or have moved - and commit provable fixes on a branch. Use when asked to check docs for staleness, broken references or drift.
triggers:
  - /document-drift
---

# document-drift

Scans a repository's markdown documentation for references that have drifted from the code (renamed or deleted paths, dead anchors, missing scripts, stale versions), applies only provable fixes and commits them on a branch. The full procedure is filled in by a later task.
