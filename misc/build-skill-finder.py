#!/usr/bin/env python3
"""Build misc/website/static/manifests/skill-finder.json for the skill finder page.

Every field comes from a file in this repo, never from hand-written text:
  name, description   skills/<name>/SKILL.md frontmatter
  summary             first sentence of the description (cut at 160 chars)
  group               the same eks- / ecs- / general split as update-pages.sh classify_skill
  path                the generated docs page, /docs/skills/<group>/<name>
  upstream            true when a misc/sync-*.sh script sets LOCAL_SKILL_PATH="skills/<name>"
  devopsAgent         true when devops-agent/<name>/SKILL.md exists (a DevOps Agent port)
  eval                score and grade from misc/website/static/manifests/evals.json, else null

Usage (from the repo root):
  python3 misc/build-skill-finder.py          write the manifest
  python3 misc/build-skill-finder.py --check  exit 1 if the manifest is stale
"""

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
EVALS = ROOT / "misc/website/static/manifests/evals.json"
OUT = ROOT / "misc/website/static/manifests/skill-finder.json"
SUMMARY_MAX = 160


def frontmatter(skill_md: Path) -> dict:
    lines = skill_md.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].rstrip() != "---":
        raise SystemExit(f"{skill_md}: no frontmatter")
    for i, line in enumerate(lines[1:], start=1):
        if line.rstrip() == "---":
            data = yaml.safe_load("\n".join(lines[1:i]))
            if not isinstance(data, dict):
                raise SystemExit(f"{skill_md}: frontmatter is not a mapping")
            return data
    raise SystemExit(f"{skill_md}: unclosed frontmatter")


def classify(name: str) -> str:
    if name.startswith("eks-"):
        return "eks"
    if name.startswith("ecs-"):
        return "ecs"
    return "general"


def summary(description: str) -> str:
    text = " ".join(description.split())
    for i, ch in enumerate(text):
        if ch in ".!?" and (i + 1 == len(text) or text[i + 1] == " "):
            text = text[: i + 1]
            break
    if len(text) > SUMMARY_MAX:
        text = text[: SUMMARY_MAX - 3].rsplit(" ", 1)[0] + "..."
    return text


def synced_skills() -> set:
    found = set()
    for script in (ROOT / "misc").glob("sync-*.sh"):
        found.update(re.findall(r'^LOCAL_SKILL_PATH="skills/([^"/]+)"', script.read_text(encoding="utf-8"), re.M))
    return found


def load_evals() -> dict:
    if not EVALS.exists():
        return {}
    return {
        row["skill"]: {"score": row.get("score"), "grade": row.get("grade")}
        for row in json.loads(EVALS.read_text(encoding="utf-8"))
        if isinstance(row, dict) and "skill" in row
    }


def build() -> str:
    evals = load_evals()
    synced = synced_skills()
    skills = []
    for skill_md in sorted(SKILLS.glob("*/SKILL.md")):
        folder = skill_md.parent.name
        fm = frontmatter(skill_md)
        name = str(fm.get("name", folder))
        description = str(fm.get("description", ""))
        group = classify(folder)
        skills.append({
            "name": name,
            "summary": summary(description),
            "description": description,
            "group": group,
            "path": f"/docs/skills/{group}/{folder}",
            "upstream": folder in synced,
            "devopsAgent": (ROOT / "devops-agent" / folder / "SKILL.md").exists(),
            "eval": evals.get(folder),
        })
    return json.dumps(skills, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    check = sys.argv[1:] == ["--check"]
    if sys.argv[1:] not in ([], ["--check"]):
        print(__doc__, file=sys.stderr)
        return 2
    new = build()
    if check:
        old = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if old != new:
            print(f"{OUT.relative_to(ROOT)} is stale: run python3 misc/build-skill-finder.py", file=sys.stderr)
            return 1
        return 0
    OUT.write_text(new, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
