# =============================================================================
# SKELETON — Replatform environment: ECS on EC2, containerize-as-is
#
# This is the fixed skeleton of the Replatform shape. It is deliberately NOT
# what `ecs-build` produces: every task definition `ecs-build` generates is
# `awsvpc` and every service it generates carries a capacity_provider_strategy,
# and it has no stickiness / bridge / dynamic-host-port knowledge. Those are
# exactly the four elements below, which is why this path is generated here.
#
# What varies between runs, and where it comes from:
#
#   * stickiness            -> var.session_affinity_required, set from the
#                              in_process_session blocker (cite the id)
#   * persistent volumes    -> add efs.tf ONLY when local_state findings were
#                              classified persistent (see the module reference)
#   * image_uri / sizing    -> variables, from the containerization artifact
#                              and the capacity derivation
#
# Everything else is identical every time. Do not add resources the assessment
# did not justify.
# =============================================================================

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.60, < 7.0"
    }
  }
}

provider "aws" {
  region = var.region
}

locals {
  name = var.name_prefix

  tags = merge(var.tags, {
    ManagedBy = "ecs-modernize"
    Path      = "replatform"
  })

  # CREATE when no VPC was supplied — the normal case for a migration from
  # outside AWS. REUSE when one was.
  create_network = var.vpc_id == null

  vpc_id     = local.create_network ? aws_vpc.this[0].id : var.vpc_id
  subnet_ids = local.create_network ? aws_subnet.public[*].id : var.subnet_ids

  # CREATE mode builds PUBLIC subnets routed through an internet gateway and no
  # NAT gateway, so instances MUST get public IPs: an instance in a public subnet
  # without one has no internet path at all, so the ECS agent cannot reach the
  # control plane and cannot pull from ECR. It never joins the cluster, tasks
  # never place, and the failure appears at steady-state verification rather than
  # at apply. In REUSE mode the supplied subnets decide — see the variable.
  assign_public_ip = local.create_network ? true : var.assign_public_ip
}

# -----------------------------------------------------------------------------
# Network — CREATE mode only
#
# Two public subnets across two AZs is the minimum the capacity plan needs
# (N+1 spread across >= 2 AZs). Public subnets with public IPs avoid NAT gateway
# charges; for a workload that must not be directly reachable, switch to private
# subnets plus a NAT gateway or VPC endpoints and record the cost decision.
#
# Nothing here is created in REUSE mode: count = 0 leaves the existing network
# untouched, which is also why this skeleton never modifies a supplied VPC.
# -----------------------------------------------------------------------------
data "aws_availability_zones" "available" {
  count = local.create_network ? 1 : 0
  state = "available"
}

resource "aws_vpc" "this" {
  count = local.create_network ? 1 : 0

  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(local.tags, { Name = local.name })
}

resource "aws_internet_gateway" "this" {
  count = local.create_network ? 1 : 0

  vpc_id = aws_vpc.this[0].id
  tags   = merge(local.tags, { Name = local.name })
}

resource "aws_subnet" "public" {
  count = local.create_network ? 2 : 0

  vpc_id            = aws_vpc.this[0].id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone = data.aws_availability_zones.available[0].names[count.index]

  tags = merge(local.tags, { Name = "${local.name}-public-${count.index}" })
}

resource "aws_route_table" "public" {
  count = local.create_network ? 1 : 0

  vpc_id = aws_vpc.this[0].id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this[0].id
  }

  tags = merge(local.tags, { Name = "${local.name}-public" })
}

resource "aws_route_table_association" "public" {
  count = local.create_network ? 2 : 0

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public[0].id
}

# -----------------------------------------------------------------------------
# Security groups
#
# The container-instance group admits the EPHEMERAL PORT RANGE from the ALB,
# not a single fixed port. That is a consequence of dynamic host port mapping
# (hostPort = 0): ECS assigns each task an ephemeral host port, so the ALB
# reaches tasks on unpredictable ports. Restricting to var.container_port here
# would break every task after the first.
# -----------------------------------------------------------------------------
resource "aws_security_group" "alb" {
  name        = "${local.name}-alb"
  description = "ALB ingress for the replatformed application"
  vpc_id      = local.vpc_id
  tags        = local.tags

  ingress {
    description = "Application traffic from the approved CIDR"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = [var.ingress_cidr]
  }

  egress {
    description = "To the container instances"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "instances" {
  name        = "${local.name}-instances"
  description = "ECS container instances: ephemeral ports from the ALB only"
  vpc_id      = local.vpc_id
  tags        = local.tags

  ingress {
    description     = "Dynamic host ports from the ALB"
    from_port       = 32768
    to_port         = 65535
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "Image pull, logs, and application egress"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# -----------------------------------------------------------------------------
# Load balancer
#
# target_type = "instance" is the correct pairing with bridge mode and dynamic
# host ports. "ip" targets belong to awsvpc and would not work here.
# -----------------------------------------------------------------------------
resource "aws_lb" "app" {
  name               = substr("${local.name}-alb", 0, 32)
  load_balancer_type = "application"
  internal           = false
  security_groups    = [aws_security_group.alb.id]
  subnets            = local.subnet_ids
  tags               = local.tags
}

resource "aws_lb_target_group" "app" {
  name        = substr("${local.name}-tg", 0, 32)
  port        = var.container_port
  protocol    = "HTTP"
  vpc_id      = local.vpc_id
  target_type = "instance"
  tags        = local.tags

  health_check {
    path                = var.health_check_path
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  # CONDITIONED on the in_process_session blocker. Enabled means the unchanged
  # application's in-memory session survives across requests from one user;
  # it does NOT survive that task's replacement. Cite the blocker id in the
  # value supplied for var.session_affinity_required.
  stickiness {
    enabled = var.session_affinity_required
    type    = "lb_cookie"

    # One day, the AWS default. Match the application server's session timeout
    # when Source_Analysis established it.
    cookie_duration = 86400
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.app.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}

# -----------------------------------------------------------------------------
# Cluster and capacity — a fixed EC2 fleet
#
# The AMI comes from the SSM public parameter rather than a hardcoded id, so
# this code stays valid as AMIs are refreshed.
# -----------------------------------------------------------------------------
resource "aws_ecs_cluster" "app" {
  name = local.name
  tags = local.tags
}

data "aws_ssm_parameter" "ecs_ami" {
  name = "/aws/service/ecs/optimized-ami/amazon-linux-2023/recommended/image_id"
}

resource "aws_launch_template" "instances" {
  name_prefix   = "${local.name}-"
  image_id      = data.aws_ssm_parameter.ecs_ami.value
  instance_type = var.instance_type

  iam_instance_profile {
    arn = aws_iam_instance_profile.instance.arn
  }

  network_interfaces {
    associate_public_ip_address = local.assign_public_ip
    security_groups             = [aws_security_group.instances.id]
  }

  # IMDSv2 required, hop limit 1. The hop limit is what keeps a bridge-networked
  # container from reaching the instance's credentials at all; requiring tokens is
  # host-level defence in depth on top of that.
  metadata_options {
    http_tokens                 = "required"
    http_endpoint               = "enabled"
    http_put_response_hop_limit = 1
  }

  # Without this the instances never join the cluster.
  user_data = base64encode(<<-EOT
    #!/bin/bash
    echo "ECS_CLUSTER=${aws_ecs_cluster.app.name}" >> /etc/ecs/ecs.config
  EOT
  )

  tag_specifications {
    resource_type = "instance"
    tags          = merge(local.tags, { Name = "${local.name}-instance" })
  }
}

# min = max = desired: a fixed fleet, sized once from expected peak load. No
# scaling policy is attached, which is the static configuration this path calls
# for rather than an omission.
resource "aws_autoscaling_group" "instances" {
  name                = "${local.name}-asg"
  vpc_zone_identifier = local.subnet_ids
  min_size            = var.instance_count
  max_size            = var.instance_count
  desired_capacity    = var.instance_count

  launch_template {
    id      = aws_launch_template.instances.id
    version = "$Latest"
  }

  tag {
    key                 = "AmazonECSManaged"
    value               = ""
    propagate_at_launch = true
  }
}

# -----------------------------------------------------------------------------
# Task definition — bridge networking with dynamic host ports
#
# This is the element `ecs-build` cannot generate, and the reason this module
# exists. The unmodified application is not being adapted to per-task ENIs.
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${local.name}"
  retention_in_days = var.log_retention_days
  tags              = local.tags
}

resource "aws_ecs_task_definition" "app" {
  family             = local.name
  network_mode       = "bridge"
  execution_role_arn = aws_iam_role.execution.arn

  # Task role: present only when ECS Exec is enabled (SSM channel actions) or
  # the application itself calls an AWS API. An unchanged lift-and-shift
  # usually calls none, and granting nothing is the correct least privilege.
  task_role_arn = var.enable_execute_command ? aws_iam_role.exec_access[0].arn : null

  container_definitions = jsonencode([
    {
      name      = "app"
      image     = var.image_uri
      essential = true
      cpu       = var.task_cpu
      memory    = var.task_memory

      portMappings = [
        {
          containerPort = var.container_port
          hostPort      = 0 # dynamic — the ALB discovers the assigned port
          protocol      = "tcp"
        }
      ]

      # `mode` is set explicitly on purpose. Since 2025-06-25 an unset mode
      # defaults to non-blocking, and a non-blocking driver buffers up to its
      # max-buffer-size — 10 MiB by default (the ECS max-buffer-size default is
      # `10m`) — before it starts dropping lines, which is exactly the wrong
      # failure during the steady-state verification this path ends with, since
      # the logs are the diagnosis.
      #
      # non-blocking is still the right default: blocking backs pressure up into
      # the application's stdout writes and can hang a container (Trusted Advisor
      # flags it as an availability risk). The buffer is widened instead. Switch
      # to blocking only when complete logs matter more than task availability,
      # and say so when you do.
      logConfiguration = {
        logDriver = "awslogs"
        options = merge(
          {
            "awslogs-group"         = aws_cloudwatch_log_group.app.name
            "awslogs-region"        = var.region
            "awslogs-stream-prefix" = "replatform"
            "mode"                  = var.log_driver_mode
          },
          # max-buffer-size is only valid in non-blocking mode.
          var.log_driver_mode == "non-blocking" ? { "max-buffer-size" = var.log_max_buffer_size } : {}
        )
      }
    }
  ])

  tags = local.tags
}

# -----------------------------------------------------------------------------
# Service — fixed count, no scaling policy
#
# launch_type = "EC2" is the simpler mapping of "fixed fleet, fixed count".
# Note the asymmetry before changing it: moving a service from launch_type to a
# capacity_provider_strategy later is an in-place update, while the reverse
# requires recreating the service. The two are mutually exclusive — never both.
# -----------------------------------------------------------------------------
resource "aws_ecs_service" "app" {
  name            = local.name
  cluster         = aws_ecs_cluster.app.id
  task_definition = aws_ecs_task_definition.app.arn
  launch_type     = "EC2"
  desired_count   = var.desired_count

  enable_execute_command = var.enable_execute_command

  # Legacy applications start slowly — the Replatform path exists because they
  # are unmodified, so a JVM or an app server warming up for a minute is normal.
  # Without a grace period the ALB health check fails a task that is still
  # starting and ECS kills it, which reads as a crash loop rather than a slow
  # start. Tune it to the application's observed startup time.
  health_check_grace_period_seconds = var.health_check_grace_period_seconds

  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = "app"
    container_port   = var.container_port
  }

  # Spread across AZs so the fixed fleet's failure characteristics match the
  # multi-AZ capacity plan.
  ordered_placement_strategy {
    type  = "spread"
    field = "attribute:ecs.availability-zone"
  }

  # A safe default for a first containerized deployment: a failing deployment
  # rolls back instead of sitting half-replaced. Decline it if the user prefers
  # to inspect a stuck deployment manually.
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  depends_on = [aws_lb_listener.http]
}
