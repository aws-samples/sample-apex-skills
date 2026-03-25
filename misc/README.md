# Miscellaneous Scripts  


This folder contains miscellaneous scripts to help maintain this repo.  

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
