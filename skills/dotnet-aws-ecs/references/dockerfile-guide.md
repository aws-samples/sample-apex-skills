# Dockerfile Guide

This reference defines patterns for generating a Dockerfile for .NET applications targeting ECS Fargate Linux containers.

## Check First

Before generating, check if a Dockerfile already exists:
- `Dockerfile` in the web project directory (alongside the `.csproj`)
- `.dockerignore` in the build context root (indicates Docker is already configured)

If a working Dockerfile exists for Linux, skip this phase.

## Output Location

Place the Dockerfile alongside the web project's `.csproj` file:

```
<project-root>/<WebProject>/Dockerfile
```

Do NOT place it in the `infra/` folder.

## Multi-Stage Build Pattern

```dockerfile
# Stage 1: Build
FROM mcr.microsoft.com/dotnet/sdk:<version> AS build
WORKDIR /src

# Copy project files first for layer caching
COPY <ProjectName>/<ProjectName>.csproj ./<ProjectName>/
# If multi-project, copy each .csproj:
# COPY <OtherProject>/<OtherProject>.csproj ./<OtherProject>/
# COPY *.sln ./

RUN dotnet restore ./<ProjectName>/<ProjectName>.csproj

# Copy everything and publish
COPY . .
WORKDIR /src/<ProjectName>
RUN dotnet publish -c Release -o /app/publish --no-restore

# Stage 2: Runtime (Ubuntu Chiseled — minimal, no shell, non-root by default)
FROM mcr.microsoft.com/dotnet/aspnet:<version>-noble-chiseled AS runtime
WORKDIR /app

COPY --from=build /app/publish .

ENV ASPNETCORE_ENVIRONMENT=Production
ENV ASPNETCORE_URLS=http://+:<port>

# Use the built-in non-root user provided by chiseled .NET images
USER $APP_UID
EXPOSE <port>

ENTRYPOINT ["dotnet", "<ProjectName>.dll"]
```

## Runtime Image Selection

Use the **Ubuntu Chiseled** variant (`-noble-chiseled`) as the default for all deployments. Chiseled images are:
- Significantly smaller (~100 MB vs ~220 MB for the full aspnet image)
- More secure (no shell, no package manager, no unnecessary OS components)
- Non-root by default via `$APP_UID`

**Important:** Do NOT use `adduser` or `RUN` commands that require a shell in the runtime stage — chiseled images have no shell. Use `USER $APP_UID` instead.

**Trade-off:** Chiseled images cannot run `CMD-SHELL` container health checks (no shell, no `curl`). The ECS console will show container health as "Unknown." The ALB health check still works correctly. If the user explicitly wants the ECS container health check to report "Healthy" in the console, use the non-chiseled variant instead (see below).

### Non-Chiseled Alternative (When Container Health Check Is Required)

If the user chooses to enable the ECS container health check, switch to the standard Ubuntu runtime image (`-noble`) which includes `curl` and a shell:

```dockerfile
# Stage 2: Runtime (noble — includes curl for ECS container health checks)
FROM mcr.microsoft.com/dotnet/aspnet:<version>-noble AS runtime
WORKDIR /app

COPY --from=build /app/publish .

ENV ASPNETCORE_ENVIRONMENT=Production
ENV ASPNETCORE_URLS=http://+:<port>

# Use a non-root user for security
RUN adduser --disabled-password --gecos "" appuser
USER appuser
EXPOSE <port>

ENTRYPOINT ["dotnet", "<ProjectName>.dll"]
```

**When to use this pattern:**
- The user wants the ECS console to display "Healthy" container status instead of "Unknown"
- The task definition includes a `HealthCheck` with `CMD-SHELL` and `curl`

**Inform the user of the trade-offs:**
- Image is ~120 MB larger
- Includes shell and package manager (slightly larger attack surface)
- Provides explicit container health visibility in the ECS console

## Version Selection

Match to `TargetFramework` in the `.csproj`:

| TargetFramework | SDK Image | Runtime Image (Chiseled — default) | Runtime Image (Non-Chiseled — container health check) |
|---|---|---|---|
| net8.0 | `mcr.microsoft.com/dotnet/sdk:8.0` | `mcr.microsoft.com/dotnet/aspnet:8.0-noble-chiseled` | `mcr.microsoft.com/dotnet/aspnet:8.0-noble` |
| net9.0 | `mcr.microsoft.com/dotnet/sdk:9.0` | `mcr.microsoft.com/dotnet/aspnet:9.0-noble-chiseled` | `mcr.microsoft.com/dotnet/aspnet:9.0-noble` |
| net10.0 | `mcr.microsoft.com/dotnet/sdk:10.0` | `mcr.microsoft.com/dotnet/aspnet:10.0-noble-chiseled` | `mcr.microsoft.com/dotnet/aspnet:10.0-noble` |

**ICU / Globalization Note:** If the application uses SqlClient, culture-aware formatting, or any feature requiring ICU globalization data, use the `-chiseled-extra` variant instead of plain `-chiseled` (e.g., `aspnet:10.0-noble-chiseled-extra`). The `-extra` variant includes ICU libraries while still being shell-free and minimal.

## Port

- .NET 8+: default `8080`
- .NET 6/7: default `5000`
- Always set `ASPNETCORE_URLS` explicitly
- `EXPOSE` must match the task definition `ContainerPort`

## .dockerignore

**Critical:** The `.dockerignore` file must be placed at the Docker build context root, NOT inside the web project folder. The build context root is the directory you pass to `docker build .` (typically the parent directory containing all projects).

For a solution structured as:
```
app/                        ← build context root
├── .dockerignore           ← place HERE
├── Bookstore.Web/
│   ├── Dockerfile
│   └── Bookstore.Web.csproj
├── Bookstore.Domain/
└── Bookstore.Data/
```

Contents:

```
**/.git
**/.vs
**/.vscode
**/bin
**/obj
**/node_modules
*.user
*.suo
.env
```

**Why this matters:** If `.dockerignore` is inside the web project folder, Docker won't find it. The `obj/` directories will be copied into the container, carrying Windows-specific NuGet fallback paths (e.g., `C:\Program Files (x86)\Microsoft Visual Studio\Shared\NuGetPackages`) that cause `ResolvePackageAssets` failures on the Linux build stage.

## Multi-Project Solutions

For solutions with multiple projects, copy all `.csproj` files preserving structure before restore:

```dockerfile
COPY MyApp.Web/MyApp.Web.csproj ./MyApp.Web/
COPY MyApp.Domain/MyApp.Domain.csproj ./MyApp.Domain/
COPY MyApp.Data/MyApp.Data.csproj ./MyApp.Data/

RUN dotnet restore ./MyApp.Web/MyApp.Web.csproj

COPY . .
WORKDIR /src/MyApp.Web
RUN dotnet publish -c Release -o /app/publish --no-restore
```

The build context should be the directory containing all projects (not the web project folder itself). The Dockerfile is referenced via `-f`:

```bash
docker build -t <app-name> -f <WebProject>/Dockerfile .
```

## Local Validation

After generating the Dockerfile, validate the build locally before proceeding to deployment.

### Step 1: Check Docker Availability

Run `docker --version` to confirm Docker is installed. If Docker is not available:
- Skip the local validation
- Add a "Validate Docker Build" section to the deployment guide (DEPLOYMENT.md) with the commands the user should run manually

### Step 2: Build the Image

Run the build from the build context root:

```bash
docker build -t <app-name> -f <WebProject>/Dockerfile .
```

If the build fails:
- Check `.dockerignore` is at the build context root (not inside the project folder)
- Verify `obj/` directories are excluded
- Fix and retry

### Step 3: Smoke Test the Container

Run the container briefly to verify the runtime starts:

```bash
docker run -d --name <app-name>-test -p 8080:8080 -e "ASPNETCORE_ENVIRONMENT=Development" <app-name>
```

Wait a few seconds and check logs:

```bash
docker logs <app-name>-test
```

**Expected outcomes:**
- ✅ App starts and listens on port 8080 → full success
- ✅ App starts but fails connecting to a database → acceptable (confirms the image works; DB isn't available locally)
- ❌ Image crashes immediately with a .NET runtime error → investigate and fix the Dockerfile

### Step 4: Clean Up

Always clean up after validation:

```bash
docker rm -f <app-name>-test
docker rmi <app-name>
```

Remove any dangling images from failed builds:

```bash
docker image prune -f
```
