---
sidebar_position: 4
title: Read-only operating profile
---

# Run APEX read-only

APEX skills such as `eks-recon`, `eks-upgrade-check` and `eks-operation-review` only need to read a cluster and an AWS account. This recipe gives the agent credentials that cannot write, so a wrong command fails at the Kubernetes API server or at AWS instead of changing anything.

**Read-only is the default; write is opt-in.** Run assessments under this profile. When a task really needs to change something (`eks-build` applying Terraform, an upgrade), switch to your normal credentials for that task only, on purpose.

The profile has three layers. The first two are the guardrail; the third is a convenience.

| Layer | File | What it does |
|---|---|---|
| Kubernetes RBAC | [`misc/evals/setup/readonly-rbac.yaml`](https://github.com/aws-samples/sample-apex-skills/blob/main/misc/evals/setup/readonly-rbac.yaml) | A ServiceAccount whose ClusterRole grants only `get`, `list` and `watch`, and no Secrets |
| IAM session policy | [`misc/evals/setup/readonly-session-policy.json`](https://github.com/aws-samples/sample-apex-skills/blob/main/misc/evals/setup/readonly-session-policy.json) | Scopes a temporary STS session to `Describe*`, `List*` and `Get*` calls, plus Bedrock model invocation |
| Claude Code hook | [`misc/evals/setup/deny-write-hook.example.sh`](https://github.com/aws-samples/sample-apex-skills/blob/main/misc/evals/setup/deny-write-hook.example.sh) | Denies Bash commands such as `kubectl apply` or `aws ... delete-*` before they run |

The kit started as the read-only sandbox for the repo's live-cluster evals, and the eval runner still uses it.

## 1. Create the read-only kubeconfig

Point `kubectl` at the target cluster with credentials that can create RBAC objects, then run the bootstrap script from a clone of the repo:

```bash
./misc/evals/setup/bootstrap-readonly.sh
```

It applies `readonly-rbac.yaml` (ServiceAccount `kube-system/evals-readonly`, its ClusterRole and binding, and a token Secret), then writes `misc/evals/.secrets/kubeconfig.readonly` (gitignored, mode 600). Before it finishes, it checks that the new kubeconfig can list nodes, cannot create pods and cannot list Secrets, and that your AWS identity can mint a federation token.

Hand the agent that kubeconfig:

```bash
export KUBECONFIG="$PWD/misc/evals/.secrets/kubeconfig.readonly"
```

### What the ClusterRole can read

Kubernetes RBAC is purely additive and has no deny rules, so the role cannot say "everything except Secrets". It lists what it keeps:

- **Core group:** componentstatuses, configmaps, endpoints, events, limitranges, namespaces, nodes, persistentvolumeclaims, persistentvolumes, pods, `pods/log`, podtemplates, replicationcontrollers, resourcequotas, serviceaccounts, services.
- **Built-in groups**, every resource: admissionregistration, apiextensions, apiregistration, apps, autoscaling, batch, certificates, coordination, discovery, events, flowcontrol, metrics, networking, node, policy, rbac, scheduling, storage.
- **CRD groups `eks-recon` reads**, every resource: for example `karpenter.sh`, `eks.amazonaws.com`, `elbv2.k8s.aws`, `argoproj.io`, `monitoring.coreos.com`. The full list is in the YAML; add your own CRD groups to its last rule.
- Non-resource URLs such as `/version` and `/healthz`, with `get` only.

Left out on purpose:

- `secrets`.
- `pods/exec`, `pods/attach`, `pods/portforward`, `nodes/proxy` and `services/proxy`. A `get` on these opens a websocket connection, which is not read-only.

**The trade-off:** Helm stores its release records in Secrets, so `helm list` returns nothing under this profile, and the `eks-recon` checks that read Secrets (the Helm release fallback, the Prometheus config secret) come back empty. EKS managed add-ons (`aws eks list-addons`) and Deployments are still readable.

## 2. Mint a read-only AWS session

The session policy only takes effect inside an STS federation token. Call `GetFederationToken` with the long-term credentials of an IAM user, then export the result for the agent:

```bash
aws sts get-federation-token \
  --name "apex-readonly-${USER}" \
  --policy file://misc/evals/.secrets/readonly-session-policy.json \
  --duration-seconds 3600
```

The session can do only what both your IAM user's policies and the session policy allow. Two limits from the STS API reference:

- Federation-token credentials cannot call any IAM operation, so the policy's `iam:Get*` and `iam:List*` lines have no effect.
- They cannot call STS operations other than `GetCallerIdentity`.

## 3. Attribute the session in CloudTrail

Calls made with these credentials show up in CloudTrail with `userIdentity.type` `FederatedUser`, and their ARN carries the name you passed: `arn:aws:sts::<account-id>:federated-user/apex-readonly-<user>`. Pick a `--name` that says who ran the agent and why.

To label sessions further, pass session tags:

```bash
aws sts get-federation-token \
  --name "apex-readonly-${USER}" \
  --policy file://misc/evals/.secrets/readonly-session-policy.json \
  --duration-seconds 3600 \
  --tags Key=apex-profile,Value=read-only Key=apex-run,Value="$(date -u +%Y%m%dT%H%MZ)"
```

Passing tags needs `sts:TagSession` in your IAM user's policy, besides `sts:GetFederationToken`. The limit is 50 tags, keys up to 128 characters and values up to 256. CloudTrail records the principal tags for the federated user session.

## 4. Add the deny hook (optional)

The hook is a text match on the Bash command, so it is a second layer, not the guardrail: a command it misses still cannot write under the credentials above. It saves a round trip by stopping the agent before the API call, and tells it why.

Copy the example into your project and register it in `.claude/settings.json`:

```bash
mkdir -p .claude/hooks
cp misc/evals/setup/deny-write-hook.example.sh .claude/hooks/deny-write-hook.sh
chmod +x .claude/hooks/deny-write-hook.sh
```

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/deny-write-hook.sh" }
        ]
      }
    ]
  }
}
```

The hook reads the tool call as JSON on stdin and, for a mutating `kubectl`, `helm`, `eksctl`, `terraform` or `aws` command, prints `permissionDecision: "deny"` with a reason. It needs `jq`. Edit its pattern list to fit your tools.

## Switching to write

Write is a deliberate step, never the default: unset `KUBECONFIG` and the session variables (or open a new shell with your normal credentials), and remove or disable the hook for that task. Switch back when the task is done.

## References

Accessed 2026-11-04.

- Kubernetes RBAC, "Permissions are purely additive (there are no "deny" rules)", and subresources such as `pods/log`: https://kubernetes.io/docs/reference/access-authn-authz/rbac/
- `get` on `nodes/proxy` is not read-only: https://kubernetes.io/docs/concepts/security/rbac-good-practices/
- `pods/exec` over GET and POST: https://kubernetes.io/docs/reference/kubernetes-api/workload-resources/pod-v1/
- GetFederationToken (IAM user credentials, no IAM calls, session tags): https://docs.aws.amazon.com/STS/latest/APIReference/API_GetFederationToken.html
- Session tags and `sts:TagSession`: https://docs.aws.amazon.com/IAM/latest/UserGuide/id_session-tags.html
- CloudTrail `userIdentity` `FederatedUser`: https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-event-reference-user-identity.html
- Claude Code PreToolUse hooks: https://code.claude.com/docs/en/hooks.md
