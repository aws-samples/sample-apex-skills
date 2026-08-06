# CDK Template Guide (C#)

This reference defines the CDK project structure for provisioning ECS Fargate infrastructure.

## Project Structure

```
<project-root>/infra/EcsFargate.Cdk/
├── src/
│   ├── Program.cs
│   ├── EcsFargateCdkStack.cs
│   └── EcsFargateCdk.csproj
└── cdk.json
```

## cdk.json

```json
{
  "app": "dotnet run --project src/EcsFargateCdk.csproj"
}
```

## .csproj

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net8.0</TargetFramework>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Amazon.CDK.Lib" Version="2.*" />
    <PackageReference Include="Constructs" Version="10.*" />
  </ItemGroup>
</Project>
```

## Program.cs

```csharp
using Amazon.CDK;

var app = new App();
new EcsFargateCdkStack(app, "EcsFargateCdkStack", new StackProps
{
    Env = new Amazon.CDK.Environment
    {
        Region = "<region>"
    }
});
app.Synth();
```

## Stack Implementation

The stack must create all resources equivalent to the CloudFormation template. Key constructs:

```csharp
using Amazon.CDK;
using Amazon.CDK.AWS.EC2;
using Amazon.CDK.AWS.ECS;
using Amazon.CDK.AWS.ECS.Patterns;
using Amazon.CDK.AWS.ECR;
using Amazon.CDK.AWS.ElasticLoadBalancingV2;
using Amazon.CDK.AWS.IAM;
using Amazon.CDK.AWS.Logs;
using Constructs;

public class EcsFargateCdkStack : Stack
{
    public EcsFargateCdkStack(Construct scope, string id, IStackProps props = null)
        : base(scope, id, props)
    {
        var envName = new CfnParameter(this, "EnvironmentName", new CfnParameterProps
        {
            Default = "dev"
        });

        var containerPort = new CfnParameter(this, "ContainerPort", new CfnParameterProps
        {
            Default = "8080"
        });

        // ============================================
        // NETWORKING
        // ============================================

        var vpc = new Vpc(this, "AppVpc", new VpcProps
        {
            MaxAzs = 2,
            NatGateways = 2,
            SubnetConfiguration = new[]
            {
                new SubnetConfiguration
                {
                    Name = "Public",
                    SubnetType = SubnetType.PUBLIC,
                    CidrMask = 24
                },
                new SubnetConfiguration
                {
                    Name = "Private",
                    SubnetType = SubnetType.PRIVATE_WITH_EGRESS,
                    CidrMask = 24
                }
            }
        });

        // ============================================
        // ECR REPOSITORY
        // ============================================

        var ecr = new Repository(this, "AppEcr", new RepositoryProps
        {
            RepositoryName = $"{envName.ValueAsString}-<app-name>",
            ImageScanOnPush = true,
            RemovalPolicy = RemovalPolicy.DESTROY
        });

        // ============================================
        // ECS CLUSTER
        // ============================================

        var cluster = new Cluster(this, "AppCluster", new ClusterProps
        {
            Vpc = vpc,
            ClusterName = $"{envName.ValueAsString}-cluster",
            ContainerInsights = true
        });

        // ============================================
        // LOG GROUP
        // ============================================

        var logGroup = new LogGroup(this, "AppLogGroup", new LogGroupProps
        {
            LogGroupName = $"/ecs/{envName.ValueAsString}-<app-name>",
            Retention = RetentionDays.ONE_MONTH,
            RemovalPolicy = RemovalPolicy.DESTROY
        });

        // ============================================
        // TASK DEFINITION
        // ============================================

        var taskDef = new FargateTaskDefinition(this, "AppTaskDef", new FargateTaskDefinitionProps
        {
            // Dev: 256 CPU / 512 MiB. For production consider 1024/2048
            Cpu = 256,
            MemoryLimitMiB = 512,
            RuntimePlatform = new RuntimePlatform
            {
                CpuArchitecture = CpuArchitecture.X86_64,
                OperatingSystemFamily = OperatingSystemFamily.LINUX
            }
        });

        var container = taskDef.AddContainer("AppContainer", new ContainerDefinitionOptions
        {
            // Image will be updated after first ECR push
            Image = ContainerImage.FromRegistry("amazon/amazon-ecs-sample"),
            Essential = true,
            Logging = LogDrivers.AwsLogs(new AwsLogDriverProps
            {
                LogGroup = logGroup,
                StreamPrefix = "ecs"
            }),
            Environment = new Dictionary<string, string>
            {
                ["ASPNETCORE_ENVIRONMENT"] = "Production",
                ["ASPNETCORE_URLS"] = $"http://+:{containerPort.ValueAsString}"
            }
        });

        container.AddPortMappings(new PortMapping
        {
            ContainerPort = int.Parse(containerPort.ValueAsString),
            Protocol = Amazon.CDK.AWS.ECS.Protocol.TCP
        });

        // ============================================
        // SECURITY GROUPS
        // ============================================

        var albSg = new SecurityGroup(this, "AlbSg", new SecurityGroupProps
        {
            Vpc = vpc,
            AllowAllOutbound = true,
            Description = "Allow HTTP/HTTPS to ALB"
        });
        albSg.AddIngressRule(Peer.AnyIpv4(), Port.Tcp(80), "HTTP");
        albSg.AddIngressRule(Peer.AnyIpv4(), Port.Tcp(443), "HTTPS");

        var ecsSg = new SecurityGroup(this, "EcsSg", new SecurityGroupProps
        {
            Vpc = vpc,
            AllowAllOutbound = true,
            Description = "Allow traffic from ALB only"
        });
        ecsSg.AddIngressRule(albSg, Port.Tcp(int.Parse(containerPort.ValueAsString)),
            "From ALB");

        // ============================================
        // LOAD BALANCER
        // ============================================

        var alb = new ApplicationLoadBalancer(this, "AppAlb", new ApplicationLoadBalancerProps
        {
            Vpc = vpc,
            InternetFacing = true,  // OR false for internal
            SecurityGroup = albSg,
            VpcSubnets = new SubnetSelection { SubnetType = SubnetType.PUBLIC }
        });

        var listener = alb.AddListener("HttpListener", new BaseApplicationListenerProps
        {
            Port = 80,
            Protocol = ApplicationProtocol.HTTP
        });

        // ============================================
        // ECS SERVICE
        // ============================================

        var service = new FargateService(this, "AppService", new FargateServiceProps
        {
            Cluster = cluster,
            TaskDefinition = taskDef,
            DesiredCount = 2,
            SecurityGroups = new[] { ecsSg },
            VpcSubnets = new SubnetSelection { SubnetType = SubnetType.PRIVATE_WITH_EGRESS },
            CircuitBreaker = new DeploymentCircuitBreaker { Rollback = true }
        });

        listener.AddTargets("EcsTarget", new AddApplicationTargetsProps
        {
            Port = int.Parse(containerPort.ValueAsString),
            Targets = new[] { service },
            HealthCheck = new Amazon.CDK.AWS.ElasticLoadBalancingV2.HealthCheck
            {
                Path = "/health",
                Interval = Duration.Seconds(30),
                Timeout = Duration.Seconds(5),
                HealthyThresholdCount = 2,
                UnhealthyThresholdCount = 3
            }
        });

        // ============================================
        // AUTO SCALING
        // ============================================

        var scaling = service.AutoScaleTaskCount(new EnableScalingProps
        {
            MinCapacity = 2,
            MaxCapacity = 4
        });

        scaling.ScaleOnCpuUtilization("CpuScaling", new CpuUtilizationScalingProps
        {
            TargetUtilizationPercent = 70,
            ScaleInCooldown = Duration.Seconds(300),
            ScaleOutCooldown = Duration.Seconds(60)
        });

        // ============================================
        // OUTPUTS
        // ============================================

        new CfnOutput(this, "ApplicationURL", new CfnOutputProps
        {
            Value = $"http://{alb.LoadBalancerDnsName}",
            Description = "Application URL (ALB DNS)"
        });

        new CfnOutput(this, "ECRRepositoryUri", new CfnOutputProps
        {
            Value = ecr.RepositoryUri,
            Description = "ECR repository URI"
        });

        new CfnOutput(this, "ClusterName", new CfnOutputProps
        {
            Value = cluster.ClusterName,
            Description = "ECS cluster name"
        });
    }
}
```

## Key Differences from CloudFormation

- CDK's `Vpc` construct creates subnets, route tables, NAT gateways, and IGW automatically.
- Security group rules are expressed as method calls (`AddIngressRule`).
- The task execution role is created implicitly by `FargateTaskDefinition`.
- Use `CfnOutput` for stack outputs.

## ALB Scheme

- For internet-facing: `InternetFacing = true`
- For internal: `InternetFacing = false`

When internal, also restrict the ALB security group ingress to the VPC CIDR or specific source ranges instead of `Peer.AnyIpv4()`.

## Existing VPC Mode

When the user chooses to deploy into an existing VPC, use `Vpc.FromLookup` instead of creating a new VPC.

### VPC Lookup by ID

Replace the VPC creation block with a lookup:

```csharp
// ============================================
// NETWORKING — Existing VPC
// ============================================

var vpcId = new CfnParameter(this, "VpcId", new CfnParameterProps
{
    Type = "AWS::EC2::VPC::Id",
    Description = "ID of the existing VPC to deploy into"
});

var vpc = Vpc.FromLookup(this, "ExistingVpc", new VpcLookupOptions
{
    VpcId = "<vpc-id>"  // Replace with the actual VPC ID at generation time
});
```

**Important:** `Vpc.FromLookup` resolves at synth-time (not deploy-time), so the actual VPC ID must be known when generating the CDK code. The agent should substitute the user-provided VPC ID directly into the lookup.

### Subnet Selection

When using an existing VPC, CDK's `Vpc.FromLookup` automatically discovers the VPC's subnets. Use subnet type selectors as normal:

```csharp
// ALB in public subnets
var alb = new ApplicationLoadBalancer(this, "AppAlb", new ApplicationLoadBalancerProps
{
    Vpc = vpc,
    InternetFacing = true,
    SecurityGroup = albSg,
    VpcSubnets = new SubnetSelection { SubnetType = SubnetType.PUBLIC }
});

// ECS tasks in private subnets
var service = new FargateService(this, "AppService", new FargateServiceProps
{
    Cluster = cluster,
    TaskDefinition = taskDef,
    DesiredCount = 2,
    SecurityGroups = new[] { ecsSg },
    VpcSubnets = new SubnetSelection { SubnetType = SubnetType.PRIVATE_WITH_EGRESS },
    CircuitBreaker = new DeploymentCircuitBreaker { Rollback = true }
});
```

If the existing VPC uses non-standard subnet tagging, the user can specify subnets explicitly:

```csharp
var vpc = Vpc.FromVpcAttributes(this, "ExistingVpc", new VpcAttributes
{
    VpcId = "<vpc-id>",
    AvailabilityZones = new[] { "<az-1>", "<az-2>" },
    PublicSubnetIds = new[] { "<public-subnet-1>", "<public-subnet-2>" },
    PrivateSubnetIds = new[] { "<private-subnet-1>", "<private-subnet-2>" }
});
```

### What Changes

- Remove the `new Vpc(...)` construct (no VPC, subnets, NAT gateways, or IGW are created)
- Replace with `Vpc.FromLookup` or `Vpc.FromVpcAttributes`
- All other resources (security groups, ALB, ECS, ECR, IAM, auto-scaling) remain the same
- The `vpc` variable is still passed to downstream constructs identically

### Existing VPC Requirements

The existing VPC must have:
- At least 2 public subnets in different AZs (for the ALB)
- At least 2 private subnets with NAT egress (for ECS tasks to pull images from ECR)
- An Internet Gateway attached

Add a comment in the generated code noting these prerequisites.

### Cost Note

When using an existing VPC, NAT Gateway costs are not part of this stack. Adjust the cost estimation accordingly.

## Notes

- Replace `<app-name>` with the actual application name.
- Replace `<region>` with the target region.
- The container image is a placeholder — update after first ECR push.
- Add comments in the code noting production sizing options.
- Consider using `ApplicationLoadBalancedFargateService` from `aws-ecs-patterns` for a higher-level abstraction, but only if the generated template doesn't need fine-grained control.
