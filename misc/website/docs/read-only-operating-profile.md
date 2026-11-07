---
sidebar_position: 4
title: Read-only operating profile
---

# Run APEX read-only

APEX skills such as `eks-recon`, `eks-upgrade-check` and `eks-operation-review` only need to read a cluster and an AWS account. This recipe gives the agent credentials that cannot write, so a wrong command fails at the Kubernetes API server or at AWS instead of changing anything. This limits what the handed credentials can do; your admin kubeconfig and AWS profile stay readable to the agent's shell, so run the agent as another OS user or in a container that has only these.

**Read-only is the default; write is opt-in.** Run assessments under this profile. When a task really needs to change something (`eks-build` applying Terraform, an upgrade), switch to your normal credentials for that task only, on purpose.

The profile has three layers. The first two are the guardrail; the third is a convenience.

| Layer | File | What it does |
|---|---|---|
| Kubernetes RBAC | [`misc/evals/setup/readonly-rbac.yaml`](https://github.com/aws-samples/sample-apex-skills/blob/main/misc/evals/setup/readonly-rbac.yaml) | A ServiceAccount whose ClusterRole grants only `get`, `list` and `watch`, and no Secrets |
| IAM session policy | [`misc/evals/setup/readonly-session-policy.json`](https://github.com/aws-samples/sample-apex-skills/blob/main/misc/evals/setup/readonly-session-policy.json) | Scopes a temporary STS session to read calls (`Describe*`, `List*`, `Get*` and log filtering) on EKS, EC2, CloudFormation, Auto Scaling, ELB, CloudWatch and Logs, plus Bedrock model invocation |
| Claude Code hook | [`misc/evals/setup/deny-write-hook.example.sh`](https://github.com/aws-samples/sample-apex-skills/blob/main/misc/evals/setup/deny-write-hook.example.sh) | Denies Bash commands such as `kubectl apply` or `aws ... delete-*` before they run |

The kit started as the read-only sandbox for the repo's live-cluster evals, and the eval runner still uses it.

## 1. Create the read-only kubeconfig

Point `kubectl` at the target cluster with credentials that can create RBAC objects, then run the bootstrap script from a clone of the repo:

```bash
./misc/evals/setup/bootstrap-readonly.sh
```

It applies `readonly-rbac.yaml` (ServiceAccount `kube-system/evals-readonly`, its ClusterRole and binding, and a token Secret), then writes `misc/evals/.secrets/kubeconfig.readonly` (gitignored, mode 600). Before it finishes, it checks that the new kubeconfig can list nodes, cannot create pods and cannot list Secrets, and that your AWS identity can mint a federation token (IAM-user credentials only).

Hand the agent that kubeconfig:

```bash
export KUBECONFIG="$PWD/misc/evals/.secrets/kubeconfig.readonly"
```

The EKS MCP server defaults to `EKS_AUTH_MODE=iam` and does not read `KUBECONFIG`: set `EKS_AUTH_MODE=kubeconfig` with this kubeconfig, or expect the agent to fall back to `kubectl`.

### What the ClusterRole can read

Kubernetes RBAC is purely additive and has no deny rules, so the role cannot say "everything except Secrets". It lists what it keeps:

- **Core group:** componentstatuses, configmaps, endpoints, events, limitranges, namespaces, nodes, persistentvolumeclaims, persistentvolumes, pods, `pods/log`, podtemplates, replicationcontrollers, resourcequotas, serviceaccounts, services.
- **Built-in groups**, every resource: admissionregistration, apiextensions, apiregistration, apps, autoscaling, batch, certificates, coordination, discovery, events, flowcontrol, metrics, networking, node, policy, rbac, scheduling, storage.
- **CRD groups the skills read**, every resource: for example `karpenter.sh`, `eks.amazonaws.com`, `elbv2.k8s.aws`, `argoproj.io`, `monitoring.coreos.com`, the Gatekeeper, Cilium and Velero groups `eks-recon` reads and `keda.sh` for `eks-operation-review`. The full list is in the YAML; add your own CRD groups to its third rule. A group not listed reads as Forbidden, and a skill that hides errors then reports 0 objects for it, not "unreadable".
- Non-resource URLs such as `/version` and `/healthz`, with `get` only.

Left out on purpose:

- `secrets`.
- `pods/exec`, `pods/attach`, `pods/portforward`, `nodes/proxy` and `services/proxy`. A `get` on these opens a websocket connection, which is not read-only.

**The trade-off:** Helm stores its release records in Secrets, so `helm list` returns nothing under this profile, and the `eks-recon` checks that read Secrets (the Helm release fallback, the Prometheus config secret) come back Forbidden, and a skill that hides errors then reports none, not unreadable (for example `eks-recon`'s Helm inventory: run `helm list -A` with normal credentials before you trust it). Also denied: `eks-recon`'s IRSA OIDC-provider and GuardDuty checks, and `eks-operation-review`'s Secret key-name scan and IAM role checks (reported UNKNOWN). AWS calls outside `readonly-session-policy.json` are denied; add the actions you need. Secret objects are not readable; credentials placed in ConfigMaps, env values, logs, EC2 user data or launch templates still are. EKS managed add-ons (`aws eks list-addons`) and Deployments are readable under the role as written; the RBAC has not been tested on a live cluster.

## 2. Mint a read-only AWS session

This recipe passes the session policy to `GetFederationToken`, which needs an IAM user's long-term credentials; from a role, `aws sts assume-role --policy file://...` takes the same file. Call `GetFederationToken`, then export the result for the agent:

```bash
aws sts get-federation-token \
  --name "apex-readonly-${USER}" \
  --policy file://misc/evals/.secrets/readonly-session-policy.json \
  --duration-seconds 3600
```

`--name` takes at most 32 characters, so keep `$USER` short or pick a shorter name. The session can do only what both your IAM user's policies and the session policy allow (plus any resource-based policy that names the session). Two limits from the STS API reference:

- Federation-token credentials cannot call any IAM operation, so the policy's `iam:Get*` and `iam:List*` lines have no effect.
- They cannot call STS operations other than `GetCallerIdentity`.

## 3. Attribute the session in CloudTrail

Calls made with these credentials show up in CloudTrail with `userIdentity.type` `FederatedUser`, and their ARN carries the name you passed: `arn:aws:sts::<account-id>:federated-user/apex-readonly-<user>`. Pick a `--name` that says who ran the agent and why.

To label sessions further, add session tags to the same command:

```bash
  --tags Key=apex-profile,Value=read-only Key=apex-run,Value="$(date -u +%Y%m%dT%H%MZ)"
```

Passing tags needs `sts:TagSession` in your IAM user's policy, besides `sts:GetFederationToken`. CloudTrail records the tags in the `requestParameters` of the GetFederationToken event. kubectl calls are not in CloudTrail: they are in the EKS audit log (if enabled), all as the one ServiceAccount.

## 4. Add the deny hook (optional)

The hook is a text match on the Bash command, so it is a second layer, not the guardrail: a command it misses still cannot write under the credentials above, though other credentials left on the host stay usable (step 1's note). It saves a round trip by stopping the agent before the API call, and tells it why.

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

The hook reads the tool call as JSON on stdin and, for common mutating verbs of `kubectl`, `helm`, `eksctl`, `terraform` and `aws` typed as a bare command, prints `permissionDecision: "deny"` with a reason. It misses others (for example `aws s3 cp`, `kubectl debug`, `terraform state rm`) and any command behind a path, quotes, `bash -c` or `$(...)`. It lets `kubectl auth can-i` and `aws eks update-kubeconfig` through. It needs `jq`. Without jq, or if the hook errors, Claude Code runs the command anyway. Edit its pattern list to fit your tools.

## Switching to write

Write is a deliberate step, never the default: unset `KUBECONFIG` and the session variables (or open a new shell with your normal credentials), and remove or disable the hook for that task. Switch back when the task is done. To remove the profile: `kubectl delete -f misc/evals/setup/readonly-rbac.yaml` and delete `misc/evals/.secrets/`.

## References

Accessed 2026-11-04.

- Kubernetes RBAC, "Permissions are purely additive (there are no "deny" rules)", and subresources such as `pods/log`: https://kubernetes.io/docs/reference/access-authn-authz/rbac/
- `get` on `nodes/proxy` is not read-only: https://kubernetes.io/docs/concepts/security/rbac-good-practices/
- `pods/exec` over GET and POST: https://kubernetes.io/docs/reference/kubernetes-api/workload-resources/pod-v1/
- GetFederationToken (IAM user credentials, no IAM calls, session tags, `--name` length, the `federated-user` ARN): https://docs.aws.amazon.com/STS/latest/APIReference/API_GetFederationToken.html
- Session tags and `sts:TagSession`: https://docs.aws.amazon.com/IAM/latest/UserGuide/id_session-tags.html
- CloudTrail `userIdentity` `FederatedUser`: https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-event-reference-user-identity.html
- Claude Code PreToolUse hooks: https://code.claude.com/docs/en/hooks.md
