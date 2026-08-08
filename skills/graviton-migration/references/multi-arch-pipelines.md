# Multi-Arch Container Build Pipelines

> **Part of:** [graviton-migration](../SKILL.md)

A Graviton migration only stays migrated if the CI pipeline keeps producing images that run on arm64. This reference shows how to make each major CI system publish a **multi-arch image** — one tag, two architectures — on every build, so a workload can move to arm64 (and back, or straddle both) without anyone re-tagging anything. Read the section for the user's CI system and generate the config from it; do not produce a pipeline block from memory. The action and image versions pinned below (e.g. `actions/checkout`, `docker/*-action`, the `docker:` image tag, and the `tonistiigi/binfmt` tag) will drift over time, so verify the current stable version of each referenced action and image live before emitting it into a user's pipeline.

## Contents

- [Manifest lists: the concept](#manifest-lists-the-concept)
- [Native runners vs. QEMU emulation](#native-runners-vs-qemu-emulation)
- [GitHub Actions](#github-actions)
- [AWS CodeBuild](#aws-codebuild)
- [GitLab CI](#gitlab-ci)
- [Jenkins](#jenkins)

---

## Manifest lists: the concept

A **manifest list** (an OCI image index) is a single image tag that points at multiple per-architecture images. When a node pulls `myrepo/app:1.4.0`, the container runtime reads the manifest list and fetches the entry matching the node's architecture — the arm64 image on a Graviton node, the amd64 image on an x86 node. Same tag, right binary, automatically.

This is why the [cutover runbook](./karpenter-migration.md) tells you never to bake an `-arm64` suffix into a Kubernetes manifest: the manifest list already does arch selection. Your CI job's deliverable is therefore "push a manifest list covering `linux/amd64,linux/arm64`", not "build an arm64 image."

## Native runners vs. QEMU emulation

There are two ways to produce the arm64 half of the image:

- **QEMU emulation** — a single amd64 builder emulates arm64 via `binfmt`/QEMU (this is what `docker buildx` does by default when you ask for a foreign platform). It works anywhere with zero extra infrastructure, but emulated compilation is slow — often several times slower than native, and worst for compile-heavy languages (C/C++/Rust) and native-extension installs (Python wheels, node-gyp).
- **Native arm64 runners** — build the arm64 image on an actual Graviton machine. Much faster and avoids emulation edge cases (some toolchains misbehave under QEMU). The common pattern is to build each arch on its own native runner in parallel, then join them into one manifest list.

**Prefer native arm64 runners for anything compile-heavy.** Reach for QEMU only when arm64 build capacity is not readily available or the build is light (interpreted code, no native deps). The per-CI sections below note how to get native arm64 capacity in each system.

## GitHub Actions

Use Docker's Buildx actions. Simplest form (QEMU, single job):

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: docker/setup-qemu-action@v4      # enables arm64 emulation
      - uses: docker/setup-buildx-action@v4
      - uses: docker/login-action@v4
        with:
          registry: <account>.dkr.ecr.<region>.amazonaws.com
          username: ${{ ... }}
          password: ${{ ... }}
      - uses: docker/build-push-action@v7
        with:
          platforms: linux/amd64,linux/arm64
          push: true
          tags: <account>.dkr.ecr.<region>.amazonaws.com/app:${{ github.sha }}
```

`platforms: linux/amd64,linux/arm64` is what turns this into a manifest-list build. Drop `docker/setup-qemu-action` and buildx will only be able to build the host arch — keep it for the emulated path.

**Native (faster):** GitHub offers arm64-hosted runners; run two jobs — `runs-on: ubuntu-latest` for amd64 and an arm64 runner label for arm64 — each building and pushing a per-arch image by digest, then a final job runs `docker buildx imagetools create -t app:tag <amd64-digest> <arm64-digest>` to assemble the manifest list. This avoids QEMU entirely.

## AWS CodeBuild

CodeBuild can run the build fleet itself on Graviton (`ARM_CONTAINER` environment type on an arm64 compute image), which gives you native arm64 builds without emulation. Two viable patterns:

- **Two native builds + join.** One CodeBuild project on an `ARM_CONTAINER` (Graviton) fleet builds the arm64 image; one on a `LINUX_CONTAINER` fleet builds amd64; a final step runs `docker manifest create` / `buildx imagetools create` to publish the manifest list. Fastest, fully native.
- **Single buildx build with QEMU.** One project runs `docker buildx build --platform linux/amd64,linux/arm64 --push`. Simpler, but the foreign arch is emulated.

Minimal `buildspec.yml` for the buildx path:

```yaml
version: 0.2
phases:
  pre_build:
    commands:
      - aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR
      # Runs privileged: registers QEMU handlers in the kernel via binfmt_misc, so pin a specific, trusted tag (verify a current one on Docker Hub), never :latest.
      - docker run --privileged --rm tonistiigi/binfmt:qemu-v9.2.2 --install all   # QEMU (skip on native fleet)
      - docker buildx create --use
  build:
    commands:
      - docker buildx build --platform linux/amd64,linux/arm64 -t $ECR/app:$CODEBUILD_RESOLVED_SOURCE_VERSION --push .
```

On a Graviton fleet, prefer building the arm64 half natively and skip the `binfmt` install for that half.

## GitLab CI

GitLab uses buildx inside a `docker:dind` service, or native arm64 runners. Emulated single-job form:

```yaml
build:
  image: docker:29
  services:
    - docker:29-dind
  script:
    # Runs privileged: registers QEMU handlers in the kernel via binfmt_misc, so pin a specific, trusted tag (verify a current one on Docker Hub), never :latest.
    - docker run --privileged --rm tonistiigi/binfmt:qemu-v9.2.2 --install all
    - docker buildx create --use
    - echo "$CI_REGISTRY_PASSWORD" | docker login -u "$CI_REGISTRY_USER" --password-stdin "$CI_REGISTRY"
    - docker buildx build --platform linux/amd64,linux/arm64 -t "$CI_REGISTRY_IMAGE:$CI_COMMIT_SHA" --push .
```

**Native (faster):** register an arm64 GitLab Runner (on a Graviton instance) and use runner **tags** to route an `arm64` build job to it and an `amd64` build job to an x86 runner. Each job builds and pushes its arch; a final job joins them with `docker buildx imagetools create`. This matches the multi-node native pattern and avoids QEMU's compile penalty.

## Jenkins

Two established patterns:

- **Single agent + buildx (emulated).** On one agent with buildx and `binfmt`/QEMU installed, a pipeline stage runs `docker buildx build --platform linux/amd64,linux/arm64 --push`. Straightforward; slow for the emulated arch.
- **Multi-node native.** Label an arm64 (Graviton) agent and an amd64 agent. A parallel stage builds each arch on its matching agent (`agent { label 'arm64' }` / `label 'amd64' }`), pushes per-arch images, and a final stage runs `docker buildx imagetools create -t repo/app:tag <amd64> <arm64>` to publish the manifest list.

Declarative sketch of the native pattern:

```groovy
pipeline {
  agent none
  stages {
    stage('build') {
      parallel {
        stage('amd64') { agent { label 'amd64' } steps { sh 'docker build -t repo/app:amd64-$GIT_COMMIT . && docker push repo/app:amd64-$GIT_COMMIT' } }
        stage('arm64') { agent { label 'arm64' } steps { sh 'docker build -t repo/app:arm64-$GIT_COMMIT . && docker push repo/app:arm64-$GIT_COMMIT' } }
      }
    }
    stage('manifest') {
      agent { label 'amd64' }
      steps { sh 'docker buildx imagetools create -t repo/app:$GIT_COMMIT repo/app:amd64-$GIT_COMMIT repo/app:arm64-$GIT_COMMIT' }
    }
  }
}
```

Whichever CI system you use, the acceptance test is the same: after the pipeline runs, inspect the pushed tag (`docker buildx imagetools inspect repo/app:tag`) and confirm it lists both `linux/amd64` and `linux/arm64`. That manifest list is what lets the [Karpenter cutover](./karpenter-migration.md) reference a single tag and get the right binary on every node.
