# Miscellaneous Scripts  


This folder contains miscellaneous scripts to help maintain this repo.  

## Evaluate Skills

Per-skill evaluation inputs live under [`evals/`](./evals/). The eval framework uses a 5-layer architecture (triggering → process → artifact → knowledge → quality) with composite scoring and letter grades. Evals are maintainer-run — see [`evals/README.md`](./evals/README.md) for the manual update workflow.

## Update README - Skills and Steering  

Various READMEs references Skills and Steering files. We do not want to have to manually edit everytime some change is made to either folder. Thus, created scripts to read the frontmatter of both and update the READMEs accordingly:  

**For Skills**  

```bash
chmod +x update-skills-references.sh  
./update-skills-references.sh
```  

**For Steering**  

```bash
chmod +x update-steering-references.sh  
./update-steering-references.sh
```

**For Examples**  

```bash
chmod +x update-examples-references.sh  
./update-examples-references.sh
```

## Sync External Skills  

Some skills are sourced from external upstream repos and treated as the source of truth. These sync scripts clone the upstream repo into a temp directory, wipe the local copy, and replace it entirely with the upstream version. They are idempotent — run them anytime to pull the latest.  

> **Important:** We only sync — we do not modify third-party content. See [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) for license details and downstream redistribution obligations.

### skill-creator  

Syncs from [anthropics/skills](https://github.com/anthropics/skills) — Anthropic's official skill-creator.  

```bash
chmod +x sync-skill-creator.sh  
./sync-skill-creator.sh
```  

After syncing, run `./update-skills-references.sh` to regenerate the skills README.

### terraform-skill  

Syncs from [antonbabenko/terraform-skill](https://github.com/antonbabenko/terraform-skill) — Comprehensive Terraform and OpenTofu best practices skill by Anton Babenko. Licensed under Apache 2.0.  

```bash
chmod +x sync-terraform-skill.sh  
./sync-terraform-skill.sh
```  

After syncing, run `./update-skills-references.sh` to regenerate the skills README.

**What gets synced:** Core skill components only — `SKILL.md`, `LICENSE`, `references/*.md`  
**What gets excluded:** Everything else (README, CLAUDE.md, CONTRIBUTING.md, CHANGELOG.md, tests/, `.github/`, `.claude-plugin/`)

## Validate Frontmatter

`validate-frontmatter.py` strict-parses the YAML frontmatter of every `skills/*/SKILL.md` and `devops-agent/*/SKILL.md` (valid mapping, `name` + `description` present, description ≤ 1024 chars; for `skills/` the description must also be in sync with the generated `skills.json` manifest — `devops-agent/` is exempt, and a missing manifest entry is only a warning). CI runs it in the `docs-sync` job; run it locally with `python3 misc/validate-frontmatter.py` (requires PyYAML).

## Docs site

The Docusaurus site lives at `misc/website/`. Key commands:

- Preview: `cd misc/website && npm install && npm run start`
- Build: `cd misc/website && npm run build && npm run serve`
- Regenerate wrappers + manifest: `./misc/update-pages.sh`
- Check freshness: `./misc/update-pages.sh --check`
