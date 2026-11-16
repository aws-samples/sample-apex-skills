# Service rules

Service is the parent of the per-service classes, service-eks and then service-ecs. It holds what EKS and ECS skills share.

- **service.credentials-check**: Before you conclude that AWS credentials are missing, run `aws sts get-caller-identity`. Credentials can come from `~/.aws/credentials`, `~/.aws/config`, instance metadata or a task role, and none of these shows in the `AWS_` environment variables.
