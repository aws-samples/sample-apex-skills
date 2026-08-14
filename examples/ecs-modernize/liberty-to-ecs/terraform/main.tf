# =============================================================================
# Target environment for the REARCHITECT path of the Liberty-to-ECS exercise.
#
# Fargate, awsvpc, no sticky sessions, an S3 bucket for externalized state, and
# a task role granting only that bucket.
#
# There is deliberately NO Replatform Terraform here. The skill generates that
# path itself, from the verified skeleton it ships at
# skills/ecs-modernize/assets/replatform-terraform/ — `ecs-build` cannot produce
# the Replatform shape (bridge networking, dynamic host ports, ALB stickiness,
# a fixed-count service with no scaling policy). Part 2 of the README has the
# agent generate it, which is the point of the exercise.
#
# This file exists because the Rearchitect shape IS `ecs-build`'s territory, and
# the exercise keeps a verified implementation so the deploy step stays cheap and
# reproducible. Part 3b's optional step runs the real `ecs-build` hand-off.
# =============================================================================

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.60, < 7.0"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.5"
    }
  }
}

provider "aws" {
  region = var.region
}

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  name = "ex-liberty-${var.suffix}"
  azs  = slice(data.aws_availability_zones.available.names, 0, 2)

  tags = {
    Example = "apex-ecs-modernize-liberty-to-ecs"
    Path    = "rearchitect"
  }
}

# -----------------------------------------------------------------------------
# Networking — two public subnets is all this exercise needs. Public subnets
# with public IPs avoid NAT gateway charges, which dominate the cost of a
# short-lived hands-on.
# -----------------------------------------------------------------------------
resource "aws_vpc" "this" {
  cidr_block           = "10.20.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = merge(local.tags, { Name = local.name })
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = merge(local.tags, { Name = local.name })
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.this.id
  cidr_block              = cidrsubnet(aws_vpc.this.cidr_block, 8, count.index)
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true
  tags                    = merge(local.tags, { Name = "${local.name}-public-${count.index}" })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }
  tags = merge(local.tags, { Name = "${local.name}-public" })
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# -----------------------------------------------------------------------------
# Security groups
# -----------------------------------------------------------------------------
resource "aws_security_group" "alb" {
  name        = "${local.name}-alb"
  description = "ALB ingress for the Orders exercise"
  vpc_id      = aws_vpc.this.id
  tags        = merge(local.tags, { Name = "${local.name}-alb" })
}

resource "aws_vpc_security_group_ingress_rule" "alb_http" {
  security_group_id = aws_security_group.alb.id
  # No apostrophe: EC2 accepts security group rule descriptions only from the set
  # a-zA-Z0-9. _-:/()#,@[]+=&;{}!$* and rejects anything else with
  # InvalidParameterValue, which fails the apply on this resource.
  description = "HTTP from the operator address range"
  cidr_ipv4   = var.ingress_cidr
  from_port   = 80
  to_port     = 80
  ip_protocol = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "alb_all" {
  security_group_id = aws_security_group.alb.id
  description       = "ALB to targets"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

resource "aws_security_group" "task" {
  name        = "${local.name}-task"
  description = "Orders task/instance"
  vpc_id      = aws_vpc.this.id
  tags        = merge(local.tags, { Name = "${local.name}-task" })
}

resource "aws_vpc_security_group_ingress_rule" "task_from_alb" {
  security_group_id            = aws_security_group.task.id
  description                  = "Liberty HTTP from the ALB only"
  referenced_security_group_id = aws_security_group.alb.id
  from_port                    = 9080
  to_port                      = 9080
  ip_protocol                  = "tcp"
}


resource "aws_vpc_security_group_egress_rule" "task_all" {
  security_group_id = aws_security_group.task.id
  description       = "Outbound for image pulls, logs, and S3"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

# -----------------------------------------------------------------------------
# ECR — one repository per path, so both images can coexist.
# -----------------------------------------------------------------------------
resource "aws_ecr_repository" "app" {
  name                 = "${local.name}-rearchitect"
  image_tag_mutability = "MUTABLE"
  force_delete         = true # exercise convenience: destroy removes the images

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = local.tags
}

# -----------------------------------------------------------------------------
# Load balancer
# -----------------------------------------------------------------------------
resource "aws_lb" "this" {
  name               = local.name
  load_balancer_type = "application"
  subnets            = aws_subnet.public[*].id
  security_groups    = [aws_security_group.alb.id]
  tags               = local.tags
}

resource "aws_lb_target_group" "this" {
  name        = "${local.name}-rearchitect"
  port        = 9080
  protocol    = "HTTP"
  vpc_id      = aws_vpc.this.id
  target_type = "ip" # awsvpc on Fargate registers task IPs, not instances

  health_check {
    path                = var.health_check_path
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  # OFF, and that is a finding rather than a default: the rearchitected app holds
  # no server-side session (CartResource derives its response from the request),
  # so pinning a user to one task buys nothing. Contrast the Replatform skeleton,
  # where the in_process_session blocker forces it ON.
  stickiness {
    type            = "lb_cookie"
    enabled         = false
    cookie_duration = 3600
  }

  tags = local.tags
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.this.arn
  }

  tags = local.tags
}

# -----------------------------------------------------------------------------
# Cluster and logs
# -----------------------------------------------------------------------------
resource "aws_ecs_cluster" "this" {
  name = local.name

  setting {
    name  = "containerInsights"
    value = "disabled" # keeps the exercise's CloudWatch bill at ~zero
  }

  tags = local.tags
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${local.name}"
  retention_in_days = 7
  tags              = local.tags
}
