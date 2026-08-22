---
title: "Upstream Provenance"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/dotnet-aws-ecs/UPSTREAM.md
format: md
---

:::info[Source]
This page is generated from [skills/dotnet-aws-ecs/UPSTREAM.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/dotnet-aws-ecs/UPSTREAM.md). Edit the source, not this page.
:::


:::caution[Third-party skill]
This skill is maintained by **adisimon217** under the MIT license. Upstream: [https://github.com/adisimon217/sample-appmod-skills](https://github.com/adisimon217/sample-appmod-skills)
:::

# Upstream Provenance

This skill is **vendored** from an upstream repo. Do not edit files here
directly — your changes will be overwritten by the next sync.

| Field | Value |
|---|---|
| Source repo | https://github.com/adisimon217/sample-appmod-skills.git |
| Source path | `dotnet-aws-ecs/` |
| Refresh command | `./misc/sync-dotnet-aws-ecs-skill.sh` |
| License | See `LICENSE` (copied verbatim from upstream repo root) |
| Last synced commit | See `.vendor-sha` in this directory |

## Local modifications applied at sync time

- `SKILL.md`: the `version:` top-level frontmatter line is removed at
  sync time (the APEX frontmatter policy allows only the
  name/description/license/metadata/allowed-tools top-level keys).

Everything else is byte-for-byte from upstream (`LICENSE` is copied
from the upstream repo root; `UPSTREAM.md` and `.vendor-sha` are
apex-side metadata, not upstream content).

## To propose changes

Open a PR against the upstream repo:
https://github.com/adisimon217/sample-appmod-skills.git

Then re-run the sync script here.
