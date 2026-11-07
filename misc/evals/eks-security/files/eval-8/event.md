# Event notes (mock, for an offline eval)

- Reported: 2026-11-05T16:20:00Z by the build team.
- What: a dependency pulled into the `orders-api` image build was a malicious package version. It reads the
  AWS credentials available to the pod and sends them to an outside host.
- Affected image: `111122223333.dkr.ecr.us-west-2.amazonaws.com/orders-api@sha256:4f1c0e9a7b2d3c5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6`
- Built and pushed 2026-11-03; deployed to cluster `demo-prod` (us-west-2) on 2026-11-04.
- The team has not changed anything on the cluster yet.
