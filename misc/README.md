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

### skill-creator  

Syncs from [anthropics/skills](https://github.com/anthropics/skills) — Anthropic's official skill-creator.  

```bash
chmod +x sync-skill-creator.sh  
./sync-skill-creator.sh
```  

After syncing, run `./update-skills-references.sh` to regenerate the skills README.
