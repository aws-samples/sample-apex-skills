# Script rules

A Script skill runs its own scripts to do the task, and its output is a typed result.

- **script.output-schema**: The script's own output validates against the JSON Schema in this skill's `assets/`.
- **script.same-output**: The same input gives the same output on every run.
- **script.os-matrix**: The skill's scripts run on Linux, macOS and Windows.
