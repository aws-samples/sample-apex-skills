# Health Check Endpoint Guide

This reference defines patterns for verifying and configuring a health check endpoint in .NET applications targeting ECS Fargate with an Application Load Balancer.

## Why Health Checks Are Required

Both the **ALB target group** and the **ECS service** rely on health checks to determine whether a container is healthy:

- **ALB target group** sends periodic HTTP requests to the health check path. If a target fails consecutive checks, the ALB removes it from rotation.
- **ECS deployment circuit breaker** uses health check status to decide whether a rolling deployment succeeded or should roll back.

Without a working health check endpoint, the ALB will mark all targets as unhealthy and the service will never stabilize.

## Check First

Before adding anything, check if the application already exposes a health check:

1. Search `Program.cs` (or `Startup.cs` for older patterns) for:
   - `MapHealthChecks`
   - `UseHealthChecks`
   - Any custom middleware mapped to `/health`, `/hc`, `/healthz`, or `/status`
2. Check if `Microsoft.Extensions.Diagnostics.HealthChecks` or `Microsoft.AspNetCore.Diagnostics.HealthChecks` is already referenced in the `.csproj`.

If a health check endpoint already exists, note its path (e.g., `/hc`) and skip to the "Wire Into IaC" section.

## Adding the Health Check Endpoint

### Step 1: Add the NuGet Package (if not present)

The base health check infrastructure is included in the `Microsoft.AspNetCore.App` shared framework, so no extra package is needed for a basic liveness endpoint.

Only add packages if you need specific health check providers (database, Redis, etc.) — which is out of scope for this skill.

### Step 2: Register Health Check Services

In `Program.cs`, add the service registration **before** `var app = builder.Build();`:

```csharp
builder.Services.AddHealthChecks();
```

### Step 3: Map the Health Check Endpoint

After `var app = builder.Build();`, map the endpoint:

```csharp
app.MapHealthChecks("/hc");
```

### Recommended Path

Use `/hc` as the default health check path. It is:
- Short and conventional in .NET applications
- Unlikely to conflict with application routes
- Easy to remember when configuring ALB target groups

If the application already uses a different path (e.g., `/health` or `/healthz`), keep the existing path — just ensure the IaC health check configuration matches.

## Full Example (Minimal API / ASP.NET Core 8+)

```csharp
var builder = WebApplication.CreateBuilder(args);

// ... existing service registrations ...

builder.Services.AddHealthChecks();

var app = builder.Build();

// ... existing middleware pipeline ...

app.MapHealthChecks("/hc");

// ... existing endpoint mappings (MapControllers, MapRazorPages, etc.) ...

app.Run();
```

## Older Patterns (Startup.cs)

For applications still using the `Startup.cs` pattern:

**ConfigureServices:**
```csharp
public void ConfigureServices(IServiceCollection services)
{
    // ... existing registrations ...
    services.AddHealthChecks();
}
```

**Configure:**
```csharp
public void Configure(IApplicationBuilder app, IWebHostEnvironment env)
{
    // ... existing middleware ...
    app.UseEndpoints(endpoints =>
    {
        endpoints.MapHealthChecks("/hc");
        // ... existing endpoints ...
    });
}
```

## Wire Into IaC

The health check path must be configured in two places in the generated IaC:

### ALB Target Group

```yaml
# CloudFormation
TargetGroup:
  Type: AWS::ElasticLoadBalancingV2::TargetGroup
  Properties:
    HealthCheckPath: /hc
    HealthCheckIntervalSeconds: 30
    HealthCheckTimeoutSeconds: 5
    HealthyThresholdCount: 2
    UnhealthyThresholdCount: 3
    Matcher:
      HttpCode: "200"
```

```csharp
// CDK
var targetGroup = new ApplicationTargetGroup(this, "TargetGroup", new ApplicationTargetGroupProps
{
    HealthCheck = new Amazon.CDK.AWS.ElasticLoadBalancingV2.HealthCheck
    {
        Path = "/hc",
        Interval = Duration.Seconds(30),
        Timeout = Duration.Seconds(5),
        HealthyThresholdCount = 2,
        UnhealthyThresholdCount = 3
    }
});
```

### ECS Task Definition (Container Health Check)

Optionally, add a container-level health check in the task definition. This lets ECS itself monitor the container independently of the ALB:

```yaml
# CloudFormation
ContainerDefinitions:
  - Name: !Sub "${EnvironmentName}-app"
    HealthCheck:
      Command:
        - "CMD-SHELL"
        - "curl -f http://localhost:8080/hc || exit 1"
      Interval: 30
      Timeout: 5
      Retries: 3
      StartPeriod: 60
```

**Note on chiseled images:** Ubuntu Chiseled runtime images do not include `curl` or a shell. For chiseled images, rely on the ALB health check alone and omit the container-level `HealthCheck`. The ALB health check is sufficient for ECS deployment monitoring when using the deployment circuit breaker.

## Validation

After adding the health check, verify it works locally:

```bash
dotnet run
# In another terminal:
curl http://localhost:<port>/hc
```

Expected response:
- HTTP 200 with body `Healthy`

If the application isn't runnable locally (e.g., missing database), the health check will still return 200 by default since a basic `AddHealthChecks()` with no registered checks always reports healthy.

## Summary of Decisions

| Decision | Default | Notes |
|---|---|---|
| Health check path | `/hc` | Keep existing path if one is already configured |
| Container-level health check | Omit for chiseled images | No curl/shell available |
| ALB health check interval | 30s | Good balance for dev environments |
| Unhealthy threshold | 3 | Allows brief startup delays |
| Start period (container) | 60s | Only relevant if container health check is used |
