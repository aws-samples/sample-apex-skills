---
title: "Advisory sources"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-security/references/advisory-sources.md
format: md
---

:::info[Source]
This page is generated from [devops-agent/eks-security/references/advisory-sources.md](https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-security/references/advisory-sources.md). Edit the source, not this page.
:::

# Advisory sources

The feeds C1 reads during a run. No version numbers are stored in this skill: every finding carries the URL it came from and the time it was read. The same list as the Claude Code skill's `assets/components.json` `feeds`.

Checked 2026-11-05.

| Feed id | URL | Format | What it covers | Maps to catalog components |
|---|---|---|---|---|
| `aws-bulletins-rss` | `https://aws.amazon.com/security/security-bulletins/rss/feed/` | RSS 2.0; each item links to a bulletin page | AWS security bulletins across all services, including EKS add-ons, agents and AMIs | Any: an item is relevant when its title or text names a catalog alias. Each bulletin page is free text, so it is read and extracted (C1 extraction step) |
| `k8s-cve` | `https://kubernetes.io/docs/reference/issues-security/official-cve-feed/index.json` | JSON Feed; each item has `id`, `summary`, `date_published`, `status`, `url` and a `content_text` with CVSS and "Affected Versions" / "Fixed Versions" lists | Upstream Kubernetes CVEs (kubelet, kube-apiserver, kubectl and other upstream parts) | `node:kubelet`; `k8s:control-plane` as a note only, since AWS runs the control plane (compare the platform version and say so) |
| `alas-al2023` | `https://alas.aws.amazon.com/AL2023/alas.rss` | RSS; item title `ALAS2023-YYYY-N (severity): package`, description lists CVE ids, link to the advisory page | Amazon Linux 2023 package advisories | `node-os:*` nodes running Amazon Linux 2023 |
| `alas-al2` | `https://alas.aws.amazon.com/AL2/alas.rss` | RSS, same shape; also carries extras repositories (for example container runtime packages) | Amazon Linux 2 package advisories | `node-os:*` nodes running Amazon Linux 2 |
| `bottlerocket` | `https://advisories.bottlerocket.aws/updateinfo.xml.gz` | gzip updateinfo XML; each `update` has an id, severity, issued date, references (CVE, GHSA) and a package list | Bottlerocket OS advisories | `node-os:*` nodes running Bottlerocket |
| `github-repo-advisory` | `https://api.github.com/repos/{owner}/{repo}/security-advisories/{ghsa}` | JSON; `severity`, `cve_id`, `vulnerabilities[]` with package names and version ranges | A repository's own published advisory, for components whose source is on GitHub (VPC CNI, network policy agent, other AWS open-source agents) | The catalog alias that matches the package name (for example `github.com/aws/amazon-vpc-cni-k8s` to `addon:vpc-cni`) |

Notes per feed:
- **Bulletins** are the authoritative AWS statement for AWS-owned components, including the severity word and whether a workaround exists. The page has no machine-readable range, which is why the extracted record is checked line by line against the page text.
- **Repository advisories** are read by repository path, not from the global advisory database: an AWS repository advisory can be published there while the global API returns not found for the same id. GitHub rate-limits unauthenticated API calls; a sweep reads only the advisories it is given.
- **Kubernetes feed**: a CVE may list several fixed lines (one per minor version); these become several ranges, ORed. Many items concern components AWS runs for you (the API server) or node types the cluster may not have (Windows); the report says so instead of dropping them.
- **ALAS** gives package names and CVE ids. A node's OS package versions are not in the cluster API, so for a node-OS advisory the verdict depends on whether the record can name the fixed node image release; when it cannot, the finding is `unknown` and the action is to compare the node group's AMI release with the latest one for its Kubernetes version.
- **Bottlerocket** advisories sometimes state that an issue does not apply to the default configuration. That is a note on the finding, not a verdict change.
- **Inspector findings** are not a feed here: they are read for the images the cluster runs (where Inspector is on), and they appear in the same report.

## Freshness

Each run reads the feeds live and records `read_at` per source. Where the feed carries its own timestamp (the Kubernetes feed's `updated_at`, RSS `lastBuildDate` or item `pubDate`) the report prints it beside the read time. A sweep reports the newest item date it saw per feed, which is where the next sweep should start. Nothing in this skill is a cache of a feed.

## When a feed is unreachable

Whether the Agent Space can reach these public hosts depends on its configuration. A feed or page that cannot be read is reported as not read, by id and reason. It never reads as "no advisories". Then:
1. If the run targets one advisory, the team supplies the page text (pasted or attached) or a record written on a host that can reach it (for example by the Claude Code skill). The agent checks the record's quotes against the supplied page text, and the sources line says "from file, not live".
2. For a sweep, records for the unreachable feeds can be written on a connected host and supplied. Records keep their original `read_at`.
3. If neither is possible, the report lists the feed under "not checked", and the overall verdict cannot be `not_exposed` for components only that feed covers.
