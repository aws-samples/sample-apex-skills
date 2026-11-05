> **Candidate README for comparison; not the repo's README.**

# APEX Skills

[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://aws-samples.github.io/sample-apex-skills/) [![License: MIT-0](https://img.shields.io/badge/license-MIT--0-green)](../../LICENSE)

28 agent skills for AWS platform engineering on Amazon EKS and Amazon ECS: design, build, review, upgrade, secure and modernize. They follow the [Agent Skills standard](https://agentskills.io/) and run in Claude Code, Kiro CLI, Codex and other harnesses. Type `/apex` (in Codex, `$apex`) with your request and the router picks the right skill.

```bash
npx apex-skills@1.3.0
```

For v2 and its `/apex` router, use the Manual Install (from `main`) in [Getting started](https://aws-samples.github.io/sample-apex-skills/docs/getting-started#manual-install).

Needs Node.js 18+ and git. Every install option, the full skill catalog and the hands-on examples live on the docs site:

- [Getting started](https://aws-samples.github.io/sample-apex-skills/docs/getting-started)
- [Skill catalog](https://aws-samples.github.io/sample-apex-skills/docs/skills/)
- [Examples](https://aws-samples.github.io/sample-apex-skills/docs/examples/)

5 skills are vendored from upstream projects under their own licenses: 3 are listed in [THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md); eks-operation-review and eks-upgrade-check come from aws-samples repos (see each skill's UPSTREAM.md). To contribute, see [CONTRIBUTING.md](../../CONTRIBUTING.md).

Sample code for educational and demonstration purposes only. It is not intended for direct production use without proper review, testing, and validation. Test generated infrastructure in non-production environments first.

MIT-0. See [LICENSE](../../LICENSE).
