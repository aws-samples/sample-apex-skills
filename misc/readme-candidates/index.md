# README candidates (pause row 5.6)

Four candidate root READMEs to compare side by side. Each one is a full README of the real repo content at origin/main 7965ae3a4a80740f8c271d9c89932f2eaffb4463, and the four follow Options 1 to 4 of the README direction research. Open each file on GitHub to see it rendered. None of them changes the real `README.md`.

| File | What it shows |
|---|---|
| [option-1.md](option-1.md) | Today's README with only the fixes checked at 7965ae3: the doubled "open standard" phrase, a pointer to the 5 vendored skills, and punctuation. Same structure and length (162 lines by `wc -l`). |
| [option-2.md](option-2.md) | A hub README: logo hero, badge and nav rows, three-bullet "what APEX is", one install command, two screenshots of a real run, a small Mermaid flow, a catalog with a one-line summary per skill, provenance. Facts sit in marker blocks a generator would own. |
| [option-3.md](option-3.md) | A fully generated README: an "at a glance" table, an install matrix per harness, and one flat table of all 28 skills with their source. Uniform tables, little prose. |
| [option-4.md](option-4.md) | A pointer-only README: one paragraph, one install line, links to the docs site for everything else. |

## How to read them

- Links and images use paths relative to this folder (`../../`), so they render here. In the root README they would drop the `../../` prefix.
- Marker comments in option 2 (`INSTALL_SNIPPET`, `VENDORED`) and option 3's header name generators that do not exist yet. The one-line skill summaries in options 2 and 3 are short hand-written versions of each skill's `description`; in option 2 they would come from one shared short-description field.
- Option 1 keeps the generated Skills and Examples blocks as `misc/update-skills-references.sh` and `misc/update-examples-references.sh` write them, except that the generated Liberty example text has its dash punctuation changed. That text comes from the example's own README, so the real fix goes there.

## Facts used (all at 7965ae3)

- 28 skills: 13 EKS, 9 ECS, 6 general (the three skill tables, `README.md:108-130`; the `misc/website/docs/skills/<group>/` directories).
- 5 vendored skills (`skills/*/.vendor-sha`): skill-creator, terraform-skill and dotnet-aws-ecs (`THIRD_PARTY_NOTICES.md:9-31`, with their upstream repos and licenses); eks-operation-review and eks-upgrade-check (upstream named in `misc/sync-eks-operation-review-skill.sh:5` and `misc/sync-eks-upgrade-skill.sh:5`; each skill's `LICENSE` reads MIT No Attribution).
- 6 DevOps Agent ports (the `devops-agent/` skill directories).
- Installer `apex-skills` 1.3.0 (`misc/installer/package.json:2-3`; README install text `README.md:30-42`).
- Usage lines for Claude Code, Kiro CLI and Codex (`README.md:67`, `:79`, `:91`).
- 2 examples (`README.md:142-143`); screenshots under `examples/eks-upgrades/in-place-karpenter-check/static/cc/`.
- Logo `misc/website/static/img/logo.svg`; license MIT-0 (`LICENSE:1`).
