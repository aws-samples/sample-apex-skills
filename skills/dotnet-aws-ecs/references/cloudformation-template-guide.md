# CloudFormation Template Guide

This reference defines the complete structure for the single CloudFormation template that provisions all infrastructure for an ECS Fargate deployment.

## Template Skeleton

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: 'ECS Fargate deployment for <AppName>'

Parameters:
  EnvironmentName:
    Type: String
    Default: dev
    Description: Environment name prefix for resources

  ContainerPort:
    Type: Number
    Default: 8080
    Description: Port the container listens on

  DesiredCount:
    Type: Number
    Default: 2
    Description: Number of ECS tasks to run

  HealthCheckPath:
    Type: String
    Default: /health
    Description: ALB health check path

  ContainerImage:
    Type: String
    Description: ECR image URI (update after first push)
    Default: ''

Resources:
  # ============================================
  # NETWORKING
  # ============================================
  # ... (VPC, subnets, gateways, routes)

  # ============================================
  # SECURITY GROUPS
  # ============================================
  # ... (ALB SG, ECS Task SG)

  # ============================================
  # IAM ROLES
  # ============================================
  # ... (Task Execution Role, Task Role)

  # ============================================
  # LOAD BALANCER
  # ============================================
  # ... (ALB, Target Group, Listener)

  # ============================================
  # ECS
  # ============================================
  # ... (ECR, Cluster, Log Group, Task Definition, Service, Auto-Scaling)

Outputs:
  # ...
```

## Networking Section

### VPC

```yaml
VPC:
  Type: AWS::EC2::VPC
  Properties:
    CidrBlock: 10.0.0.0/16
    EnableDnsHostnames: true
    EnableDnsSupport: true
    Tags:
      - Key: Name
        Value: !Sub ${EnvironmentName}-vpc
```

### Internet Gateway

```yaml
InternetGateway:
  Type: AWS::EC2::InternetGateway
  Properties:
    Tags:
      - Key: Name
        Value: !Sub ${EnvironmentName}-igw

InternetGatewayAttachment:
  Type: AWS::EC2::VPCGatewayAttachment
  Properties:
    InternetGatewayId: !Ref InternetGateway
    VpcId: !Ref VPC
```

### Subnets (2 AZs)

```yaml
PublicSubnet1:
  Type: AWS::EC2::Subnet
  Properties:
    VpcId: !Ref VPC
    AvailabilityZone: !Select [0, !GetAZs '']
    CidrBlock: 10.0.1.0/24
    MapPublicIpOnLaunch: true
    Tags:
      - Key: Name
        Value: !Sub ${EnvironmentName}-public-1

PublicSubnet2:
  Type: AWS::EC2::Subnet
  Properties:
    VpcId: !Ref VPC
    AvailabilityZone: !Select [1, !GetAZs '']
    CidrBlock: 10.0.2.0/24
    MapPublicIpOnLaunch: true
    Tags:
      - Key: Name
        Value: !Sub ${EnvironmentName}-public-2

PrivateSubnet1:
  Type: AWS::EC2::Subnet
  Properties:
    VpcId: !Ref VPC
    AvailabilityZone: !Select [0, !GetAZs '']
    CidrBlock: 10.0.11.0/24
    Tags:
      - Key: Name
        Value: !Sub ${EnvironmentName}-private-1

PrivateSubnet2:
  Type: AWS::EC2::Subnet
  Properties:
    VpcId: !Ref VPC
    AvailabilityZone: !Select [1, !GetAZs '']
    CidrBlock: 10.0.12.0/24
    Tags:
      - Key: Name
        Value: !Sub ${EnvironmentName}-private-2
```

### NAT Gateways

```yaml
NatGateway1EIP:
  Type: AWS::EC2::EIP
  DependsOn: InternetGatewayAttachment
  Properties:
    Domain: vpc

NatGateway1:
  Type: AWS::EC2::NatGateway
  Properties:
    AllocationId: !GetAtt NatGateway1EIP.AllocationId
    SubnetId: !Ref PublicSubnet1

NatGateway2EIP:
  Type: AWS::EC2::EIP
  DependsOn: InternetGatewayAttachment
  Properties:
    Domain: vpc

NatGateway2:
  Type: AWS::EC2::NatGateway
  Properties:
    AllocationId: !GetAtt NatGateway2EIP.AllocationId
    SubnetId: !Ref PublicSubnet2
```

### Route Tables

```yaml
PublicRouteTable:
  Type: AWS::EC2::RouteTable
  Properties:
    VpcId: !Ref VPC
    Tags:
      - Key: Name
        Value: !Sub ${EnvironmentName}-public-routes

DefaultPublicRoute:
  Type: AWS::EC2::Route
  DependsOn: InternetGatewayAttachment
  Properties:
    RouteTableId: !Ref PublicRouteTable
    DestinationCidrBlock: 0.0.0.0/0
    GatewayId: !Ref InternetGateway

PublicSubnet1RouteTableAssociation:
  Type: AWS::EC2::SubnetRouteTableAssociation
  Properties:
    RouteTableId: !Ref PublicRouteTable
    SubnetId: !Ref PublicSubnet1

PublicSubnet2RouteTableAssociation:
  Type: AWS::EC2::SubnetRouteTableAssociation
  Properties:
    RouteTableId: !Ref PublicRouteTable
    SubnetId: !Ref PublicSubnet2

PrivateRouteTable1:
  Type: AWS::EC2::RouteTable
  Properties:
    VpcId: !Ref VPC
    Tags:
      - Key: Name
        Value: !Sub ${EnvironmentName}-private-routes-1

DefaultPrivateRoute1:
  Type: AWS::EC2::Route
  Properties:
    RouteTableId: !Ref PrivateRouteTable1
    DestinationCidrBlock: 0.0.0.0/0
    NatGatewayId: !Ref NatGateway1

PrivateSubnet1RouteTableAssociation:
  Type: AWS::EC2::SubnetRouteTableAssociation
  Properties:
    RouteTableId: !Ref PrivateRouteTable1
    SubnetId: !Ref PrivateSubnet1

PrivateRouteTable2:
  Type: AWS::EC2::RouteTable
  Properties:
    VpcId: !Ref VPC
    Tags:
      - Key: Name
        Value: !Sub ${EnvironmentName}-private-routes-2

DefaultPrivateRoute2:
  Type: AWS::EC2::Route
  Properties:
    RouteTableId: !Ref PrivateRouteTable2
    DestinationCidrBlock: 0.0.0.0/0
    NatGatewayId: !Ref NatGateway2

PrivateSubnet2RouteTableAssociation:
  Type: AWS::EC2::SubnetRouteTableAssociation
  Properties:
    RouteTableId: !Ref PrivateRouteTable2
    SubnetId: !Ref PrivateSubnet2
```

## Security Groups Section

```yaml
ALBSecurityGroup:
  Type: AWS::EC2::SecurityGroup
  Properties:
    GroupDescription: Allow HTTP/HTTPS to ALB
    VpcId: !Ref VPC
    SecurityGroupIngress:
      - IpProtocol: tcp
        FromPort: 80
        ToPort: 80
        CidrIp: 0.0.0.0/0
      - IpProtocol: tcp
        FromPort: 443
        ToPort: 443
        CidrIp: 0.0.0.0/0
    Tags:
      - Key: Name
        Value: !Sub ${EnvironmentName}-alb-sg

ECSTaskSecurityGroup:
  Type: AWS::EC2::SecurityGroup
  Properties:
    GroupDescription: Allow traffic from ALB only
    VpcId: !Ref VPC
    SecurityGroupIngress:
      - IpProtocol: tcp
        FromPort: !Ref ContainerPort
        ToPort: !Ref ContainerPort
        SourceSecurityGroupId: !Ref ALBSecurityGroup
    Tags:
      - Key: Name
        Value: !Sub ${EnvironmentName}-ecs-sg
```

**Note for internal ALB:** If the user chooses an internal ALB, change the `ALBSecurityGroup` ingress to restrict `CidrIp` to the VPC CIDR (`10.0.0.0/16`) or a specific source CIDR instead of `0.0.0.0/0`.

## IAM Roles Section

```yaml
ECSTaskExecutionRole:
  Type: AWS::IAM::Role
  Properties:
    AssumeRolePolicyDocument:
      Version: '2012-10-17'
      Statement:
        - Effect: Allow
          Principal:
            Service: ecs-tasks.amazonaws.com
          Action: sts:AssumeRole
    ManagedPolicyArns:
      - arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
    Tags:
      - Key: Name
        Value: !Sub ${EnvironmentName}-ecs-execution-role

ECSTaskRole:
  Type: AWS::IAM::Role
  Properties:
    AssumeRolePolicyDocument:
      Version: '2012-10-17'
      Statement:
        - Effect: Allow
          Principal:
            Service: ecs-tasks.amazonaws.com
          Action: sts:AssumeRole
    Policies:
      - PolicyName: CloudWatchLogs
        PolicyDocument:
          Version: '2012-10-17'
          Statement:
            - Effect: Allow
              Action:
                - logs:CreateLogStream
                - logs:PutLogEvents
              Resource: !Sub arn:aws:logs:${AWS::Region}:${AWS::AccountId}:log-group:/ecs/${EnvironmentName}-*
    Tags:
      - Key: Name
        Value: !Sub ${EnvironmentName}-ecs-task-role
```

## Load Balancer Section

```yaml
ALB:
  Type: AWS::ElasticLoadBalancingV2::LoadBalancer
  Properties:
    Name: !Sub ${EnvironmentName}-alb
    Scheme: internet-facing    # OR 'internal' based on user choice
    Type: application
    Subnets:
      - !Ref PublicSubnet1
      - !Ref PublicSubnet2
    SecurityGroups:
      - !Ref ALBSecurityGroup

TargetGroup:
  Type: AWS::ElasticLoadBalancingV2::TargetGroup
  Properties:
    Name: !Sub ${EnvironmentName}-tg
    Port: !Ref ContainerPort
    Protocol: HTTP
    VpcId: !Ref VPC
    TargetType: ip
    HealthCheckPath: !Ref HealthCheckPath
    HealthCheckIntervalSeconds: 30
    HealthCheckTimeoutSeconds: 5
    HealthyThresholdCount: 2
    UnhealthyThresholdCount: 3
    Matcher:
      HttpCode: '200'

HTTPListener:
  Type: AWS::ElasticLoadBalancingV2::Listener
  Properties:
    LoadBalancerArn: !Ref ALB
    Port: 80
    Protocol: HTTP
    DefaultActions:
      - Type: forward
        TargetGroupArn: !Ref TargetGroup
```

**ALB Scheme:**
- `internet-facing` — accessible from the internet (public)
- `internal` — accessible only from within the VPC or peered networks

## ECS Section

### ECR Repository

```yaml
ECRRepository:
  Type: AWS::ECR::Repository
  Properties:
    RepositoryName: !Sub ${EnvironmentName}-<app-name>
    ImageScanningConfiguration:
      ScanOnPush: true
    LifecyclePolicy:
      LifecyclePolicyText: |
        {
          "rules": [{
            "rulePriority": 1,
            "description": "Keep last 10 images",
            "selection": {
              "tagStatus": "any",
              "countType": "imageCountMoreThan",
              "countNumber": 10
            },
            "action": { "type": "expire" }
          }]
        }
```

### ECS Cluster

```yaml
ECSCluster:
  Type: AWS::ECS::Cluster
  Properties:
    ClusterName: !Sub ${EnvironmentName}-cluster
    ClusterSettings:
      - Name: containerInsights
        Value: enabled
```

### CloudWatch Log Group

```yaml
LogGroup:
  Type: AWS::Logs::LogGroup
  Properties:
    LogGroupName: !Sub /ecs/${EnvironmentName}-<app-name>
    RetentionInDays: 30
```

### Task Definition

```yaml
TaskDefinition:
  Type: AWS::ECS::TaskDefinition
  Properties:
    Family: !Sub ${EnvironmentName}-<app-name>
    NetworkMode: awsvpc
    RequiresCompatibilities:
      - FARGATE
    Cpu: '256'
    Memory: '512'
    RuntimePlatform:
      CpuArchitecture: X86_64
      OperatingSystemFamily: LINUX
    ExecutionRoleArn: !GetAtt ECSTaskExecutionRole.Arn
    TaskRoleArn: !GetAtt ECSTaskRole.Arn
    ContainerDefinitions:
      - Name: <app-name>
        Image: !Ref ContainerImage
        Essential: true
        PortMappings:
          - ContainerPort: !Ref ContainerPort
            Protocol: tcp
        Environment:
          - Name: ASPNETCORE_ENVIRONMENT
            Value: Production
          - Name: ASPNETCORE_URLS
            Value: !Sub http://+:${ContainerPort}
        LogConfiguration:
          LogDriver: awslogs
          Options:
            awslogs-group: !Ref LogGroup
            awslogs-region: !Ref AWS::Region
            awslogs-stream-prefix: ecs
```

### CPU/Memory Combinations (Fargate)

Use 256/512 as the default for dev. Add a comment in the template:

```yaml
# Dev: 256 CPU / 512 MiB. For production consider:
#   512 CPU / 1024 MiB (small-medium)
#   1024 CPU / 2048 MiB (standard web apps)
#   2048 CPU / 4096 MiB (compute-heavy)
```

### ECS Service

```yaml
ECSService:
  Type: AWS::ECS::Service
  DependsOn: HTTPListener
  Properties:
    ServiceName: !Sub ${EnvironmentName}-<app-name>-service
    Cluster: !Ref ECSCluster
    TaskDefinition: !Ref TaskDefinition
    DesiredCount: !Ref DesiredCount
    LaunchType: FARGATE
    NetworkConfiguration:
      AwsvpcConfiguration:
        AssignPublicIp: DISABLED
        Subnets:
          - !Ref PrivateSubnet1
          - !Ref PrivateSubnet2
        SecurityGroups:
          - !Ref ECSTaskSecurityGroup
    LoadBalancers:
      - ContainerName: <app-name>
        ContainerPort: !Ref ContainerPort
        TargetGroupArn: !Ref TargetGroup
    DeploymentConfiguration:
      MaximumPercent: 200
      MinimumHealthyPercent: 100
      DeploymentCircuitBreaker:
        Enable: true
        Rollback: true
```

### Auto Scaling

```yaml
ScalableTarget:
  Type: AWS::ApplicationAutoScaling::ScalableTarget
  Properties:
    MaxCapacity: 4
    MinCapacity: 2
    ResourceId: !Sub service/${ECSCluster}/${ECSService.Name}
    ScalableDimension: ecs:service:DesiredCount
    ServiceNamespace: ecs
    RoleARN: !Sub arn:aws:iam::${AWS::AccountId}:role/aws-service-role/ecs.application-autoscaling.amazonaws.com/AWSServiceRoleForApplicationAutoScaling_ECSService

ScalingPolicy:
  Type: AWS::ApplicationAutoScaling::ScalingPolicy
  Properties:
    PolicyName: !Sub ${EnvironmentName}-cpu-scaling
    PolicyType: TargetTrackingScaling
    ScalingTargetId: !Ref ScalableTarget
    TargetTrackingScalingPolicyConfiguration:
      PredefinedMetricSpecification:
        PredefinedMetricType: ECSServiceAverageCPUUtilization
      TargetValue: 70.0
      ScaleInCooldown: 300
      ScaleOutCooldown: 60
```

## Outputs Section

```yaml
Outputs:
  ApplicationURL:
    Value: !Sub http://${ALB.DNSName}
    Description: Application URL (ALB DNS)

  ECRRepositoryUri:
    Value: !GetAtt ECRRepository.RepositoryUri
    Description: ECR repository URI for pushing images

  ECSClusterName:
    Value: !Ref ECSCluster
    Description: ECS cluster name

  ECSServiceName:
    Value: !GetAtt ECSService.Name
    Description: ECS service name

  VPCId:
    Value: !Ref VPC
    Description: VPC ID
```

## Existing VPC Mode

When the user chooses to deploy into an existing VPC, the template must be modified to accept VPC and subnet IDs as parameters and skip creating networking resources.

### Additional Parameters (Existing VPC)

Add these parameters to the `Parameters` section. They are used only when deploying into an existing VPC:

```yaml
Parameters:
  # ... keep existing parameters ...

  VpcId:
    Type: AWS::EC2::VPC::Id
    Description: ID of the existing VPC to deploy into

  PublicSubnet1Id:
    Type: AWS::EC2::Subnet::Id
    Description: ID of the first public subnet (for ALB)

  PublicSubnet2Id:
    Type: AWS::EC2::Subnet::Id
    Description: ID of the second public subnet (for ALB)

  PrivateSubnet1Id:
    Type: AWS::EC2::Subnet::Id
    Description: ID of the first private subnet (for ECS tasks)

  PrivateSubnet2Id:
    Type: AWS::EC2::Subnet::Id
    Description: ID of the second private subnet (for ECS tasks)
```

### What to Remove

When generating the template for an existing VPC, **omit the entire Networking section**:
- VPC
- InternetGateway, InternetGatewayAttachment
- PublicSubnet1, PublicSubnet2, PrivateSubnet1, PrivateSubnet2
- NatGateway1, NatGateway2 and their EIPs
- All RouteTables, Routes, and RouteTableAssociations

### What to Change

Replace all `!Ref VPC` with `!Ref VpcId`, and replace subnet references:

| New VPC template | Existing VPC template |
|------------------|-----------------------|
| `!Ref VPC` | `!Ref VpcId` |
| `!Ref PublicSubnet1` | `!Ref PublicSubnet1Id` |
| `!Ref PublicSubnet2` | `!Ref PublicSubnet2Id` |
| `!Ref PrivateSubnet1` | `!Ref PrivateSubnet1Id` |
| `!Ref PrivateSubnet2` | `!Ref PrivateSubnet2Id` |

### Existing VPC Requirements

The existing VPC must have:
- At least 2 public subnets in different AZs (for the ALB)
- At least 2 private subnets in different AZs (for ECS tasks)
- NAT Gateways or equivalent egress path from private subnets (required for pulling ECR images)
- An Internet Gateway attached (for the ALB in public subnets)

Include a note in the generated template reminding the user of these prerequisites.

### Outputs (Existing VPC)

When using an existing VPC, replace the VPC output:

```yaml
Outputs:
  # ... other outputs remain the same ...

  VPCId:
    Value: !Ref VpcId
    Description: VPC ID (existing)
```

### Cost Note

When using an existing VPC, the NAT Gateway cost (~$65/month) does not apply since the VPC already has its own networking infrastructure. Adjust the cost estimation accordingly.

## Container Port Selection

Determine the port from the application:
1. Check `ASPNETCORE_URLS` in `launchSettings.json` or `Program.cs`
2. Check `Kestrel` configuration in `appsettings.json`
3. .NET 8+ default: `8080`
4. .NET 6/7 default: `5000`

Always set `ASPNETCORE_URLS` explicitly in the task definition.

## Health Check Path

1. If the app registers `AddHealthChecks()` and maps a health endpoint, use that path (commonly `/health` or `/healthz`)
2. If no health check endpoint exists, use `/`
3. Set the `HealthCheckPath` parameter accordingly

## Container Health Check

ECS supports two types of health checks:

1. **ALB Target Group Health Check** — always configured via `HealthCheckPath` on the target group. The ALB uses this to route traffic only to healthy targets and to trigger task replacement for unhealthy ones. This is sufficient for most workloads.

2. **ECS Container Health Check** — an optional `HealthCheck` property on the container definition. This runs a command inside the container (e.g., `curl`) and reports status in the ECS console. Without this, the ECS console shows container health as "Unknown."

### Default Behavior (Chiseled Image — No Container Health Check)

When using the recommended Ubuntu Chiseled runtime image, the container has no shell and no `curl` binary. This means `CMD-SHELL` health checks cannot execute. The ECS console will display container health as **"Unknown"** — this is expected and does not affect application availability. The ALB health check still protects against unhealthy tasks.

**Inform the user:** After deployment, mention that the "Unknown" container health status in the ECS console is expected when using chiseled images, and that the ALB health check is handling health evaluation.

### Alternative: Container Health Check with Non-Chiseled Image

If the user wants the ECS console to show explicit container health status (e.g., "Healthy"), offer to switch to a non-chiseled runtime image and add a container-level health check to the task definition.

When the user opts for a container health check:

1. **Switch the Dockerfile** to use the standard (non-chiseled) runtime image: `aspnet:<version>-noble`
2. **Add a `HealthCheck`** to the container definition in the task definition:

```yaml
ContainerDefinitions:
  - Name: <app-name>
    Image: !Ref ContainerImage
    Essential: true
    HealthCheck:
      Command:
        - CMD-SHELL
        - curl -f http://localhost:<port>/health || exit 1
      Interval: 30
      Timeout: 5
      Retries: 3
      StartPeriod: 60
    PortMappings:
      # ...
```

**Trade-offs to communicate to the user:**
- Non-chiseled images are larger (~220 MB vs ~100 MB) and have a larger attack surface (shell, package manager)
- Container health check adds visibility in the ECS console but does not change ALB routing behavior
- The `StartPeriod` (60s) gives the .NET app time to start before the first health check runs
