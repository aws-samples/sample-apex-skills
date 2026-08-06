# Deployment Guide Template

This defines the structure the agent should follow when generating the `DEPLOYMENT.md` file.

## Required Sections

### Header

```markdown
# Deployment Guide — <Application Name>

Deploys <AppName> to Amazon ECS Fargate behind an Application Load Balancer.
```

### Prerequisites

```markdown
## Prerequisites

- AWS CLI v2 installed and configured (`aws configure`)
- Docker installed and running
- AWS account with permissions to create VPC, ECS, ECR, IAM, ELB resources
- .NET SDK <version> (for local builds/testing)
```

### Deploy the Stack

#### New VPC (default)

```markdown
## Step 1: Deploy Infrastructure

```bash
aws cloudformation create-stack \
  --stack-name <env>-<app-name> \
  --template-body file://infra/ecs-fargate.yaml \
  --parameters \
    ParameterKey=EnvironmentName,ParameterValue=<env> \
    ParameterKey=ContainerPort,ParameterValue=<port> \
    ParameterKey=HealthCheckPath,ParameterValue=<path> \
  --capabilities CAPABILITY_IAM \
  --region <region>
```

Wait for completion (~5-7 minutes):

```bash
aws cloudformation wait stack-create-complete \
  --stack-name <env>-<app-name> \
  --region <region>
```
```

#### Existing VPC

When the template uses an existing VPC, include the VPC and subnet parameters:

```markdown
## Step 1: Deploy Infrastructure

```bash
aws cloudformation create-stack \
  --stack-name <env>-<app-name> \
  --template-body file://infra/ecs-fargate.yaml \
  --parameters \
    ParameterKey=EnvironmentName,ParameterValue=<env> \
    ParameterKey=ContainerPort,ParameterValue=<port> \
    ParameterKey=HealthCheckPath,ParameterValue=<path> \
    ParameterKey=VpcId,ParameterValue=<vpc-id> \
    ParameterKey=PublicSubnet1Id,ParameterValue=<public-subnet-1-id> \
    ParameterKey=PublicSubnet2Id,ParameterValue=<public-subnet-2-id> \
    ParameterKey=PrivateSubnet1Id,ParameterValue=<private-subnet-1-id> \
    ParameterKey=PrivateSubnet2Id,ParameterValue=<private-subnet-2-id> \
  --capabilities CAPABILITY_IAM \
  --region <region>
```

Wait for completion (~3-5 minutes, faster since no VPC/NAT creation):

```bash
aws cloudformation wait stack-create-complete \
  --stack-name <env>-<app-name> \
  --region <region>
```

> **Note:** The existing VPC must have NAT Gateways (or equivalent egress) in private subnets for ECS tasks to pull images from ECR.
```

### Build and Push Image

```markdown
## Step 2: Build and Push Container Image

Get the ECR repository URI:

```bash
aws cloudformation describe-stacks \
  --stack-name <env>-<app-name> \
  --query 'Stacks[0].Outputs[?OutputKey==`ECRRepositoryUri`].OutputValue' \
  --output text \
  --region <region>
```

Authenticate Docker with ECR:

```bash
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com
```

Build and push:

```bash
docker build -t <app-name> -f <WebProject>/Dockerfile <WebProject>/
docker tag <app-name>:latest <ecr-uri>:latest
docker push <ecr-uri>:latest
```
```

### Update Service with Image

```markdown
## Step 3: Update ECS Service

Update the stack with the image URI:

```bash
aws cloudformation update-stack \
  --stack-name <env>-<app-name> \
  --template-body file://infra/ecs-fargate.yaml \
  --parameters \
    ParameterKey=EnvironmentName,ParameterValue=<env> \
    ParameterKey=ContainerPort,ParameterValue=<port> \
    ParameterKey=HealthCheckPath,ParameterValue=<path> \
    ParameterKey=ContainerImage,ParameterValue=<ecr-uri>:latest \
  --capabilities CAPABILITY_IAM \
  --region <region>
```

Or force a new deployment if just re-pushing the `latest` tag:

```bash
aws ecs update-service \
  --cluster <env>-cluster \
  --service <env>-<app-name>-service \
  --force-new-deployment \
  --region <region>
```
```

### Verification

```markdown
## Step 4: Verify Deployment

Get the application URL:

```bash
aws cloudformation describe-stacks \
  --stack-name <env>-<app-name> \
  --query 'Stacks[0].Outputs[?OutputKey==`ApplicationURL`].OutputValue' \
  --output text \
  --region <region>
```

Check ECS service status:

```bash
aws ecs describe-services \
  --cluster <env>-cluster \
  --services <env>-<app-name>-service \
  --query 'services[0].{Status:status,Running:runningCount,Desired:desiredCount}' \
  --region <region>
```

View logs:

```bash
aws logs tail /ecs/<env>-<app-name> --follow --region <region>
```
```

### Cleanup

```markdown
## Cleanup

Delete the stack and ECR images:

```bash
# Delete all images in ECR first
aws ecr delete-repository \
  --repository-name <env>-<app-name> \
  --force \
  --region <region>

# Delete the CloudFormation stack
aws cloudformation delete-stack \
  --stack-name <env>-<app-name> \
  --region <region>

aws cloudformation wait stack-delete-complete \
  --stack-name <env>-<app-name> \
  --region <region>
```
```

### Cost Estimation

```markdown
## Cost Estimation (Dev Environment)

### New VPC

| Resource | Estimated Monthly Cost |
|----------|----------------------|
| NAT Gateways (2x) | ~$65 |
| ECS Fargate (256 CPU / 512 MiB, 2 tasks, 24/7) | ~$18 |
| Application Load Balancer | ~$16 |
| CloudWatch Logs (5 GB) | ~$3 |
| ECR Storage | ~$1 |
| **Total** | **~$103** |

### Existing VPC

| Resource | Estimated Monthly Cost |
|----------|----------------------|
| ECS Fargate (256 CPU / 512 MiB, 2 tasks, 24/7) | ~$18 |
| Application Load Balancer | ~$16 |
| CloudWatch Logs (5 GB) | ~$3 |
| ECR Storage | ~$1 |
| **Total** | **~$38** |

*NAT Gateway costs are borne by the existing VPC and not included above.*

*Costs approximate for us-east-1. Actual varies by usage and data transfer.*

**Cost reduction tip (new VPC only):** For non-production, consider using a single NAT Gateway (saves ~$32/month) by modifying both private route tables to use the same NAT Gateway.
```

### Next Steps

```markdown
## Next Steps

- [ ] **HTTPS**: Add an ACM certificate and HTTPS listener (port 443) with HTTP→HTTPS redirect
- [ ] **Custom domain**: Create a Route 53 hosted zone and alias record pointing to the ALB
- [ ] **CI/CD**: Set up CodePipeline or GitHub Actions to automate builds and deployments
- [ ] **Monitoring**: Add CloudWatch alarms for CPU, memory, 5xx errors
- [ ] **Secrets**: Use AWS Secrets Manager for connection strings and API keys
```

### Troubleshooting

```markdown
## Troubleshooting

### Tasks keep stopping
```bash
# Check stopped reason
aws ecs describe-tasks \
  --cluster <cluster> \
  --tasks $(aws ecs list-tasks --cluster <cluster> --desired-status STOPPED --query 'taskArns[0]' --output text --region <region>) \
  --query 'tasks[0].stoppedReason' \
  --region <region>
```

### Health check failing
- Verify the health check path returns HTTP 200
- Check container logs for startup errors
- Ensure container port matches the target group port

### Cannot pull image
- Re-run `aws ecr get-login-password` (tokens expire after 12 hours)
- Verify the image URI in the task definition is correct
- Ensure NAT Gateways are working (tasks in private subnets need NAT for ECR access)
```

## Style Guidelines

- Copy-paste ready commands — user only fills in their specific values
- Include wait times for long operations
- Use consistent placeholders: `<region>`, `<account-id>`, `<env>`, `<app-name>`, `<ecr-uri>`, `<port>`
- Keep it linear — no branching paths
- Adapt the deployment steps based on IaC choice:
  - **CloudFormation**: `aws cloudformation create-stack` / `update-stack`
  - **CDK**: `cdk deploy` / `cdk destroy`

## CDK Deployment Variant

When the user chose CDK, replace the CloudFormation commands with CDK equivalents:

### Deploy

```markdown
## Step 1: Deploy Infrastructure

​```bash
cd infra/EcsFargate.Cdk
cdk bootstrap aws://<account-id>/<region>  # First time only
cdk deploy --parameters EnvironmentName=<env> --parameters ContainerPort=<port>
​```
```

### Update

```markdown
## Step 3: Update ECS Service

After pushing a new image, force a new deployment:

​```bash
aws ecs update-service \
  --cluster <env>-cluster \
  --service <env>-<app-name>-service \
  --force-new-deployment \
  --region <region>
​```
```

### Cleanup

```markdown
## Cleanup

​```bash
# Delete ECR images first
aws ecr delete-repository \
  --repository-name <env>-<app-name> \
  --force \
  --region <region>

# Destroy the CDK stack
cd infra/EcsFargate.Cdk
cdk destroy
​```
```
