# =============================================================================
# REARCHITECT path — Fargate, externalized state, least-privilege task role.
#
# Differences from replatform.tf, each one a consequence of the remediation:
#
#   * Fargate instead of ECS on EC2 (no instances to operate)
#   * awsvpc networking, target_type "ip"
#   * an S3 bucket holds the order archive, and the task role grants access to
#     that bucket only
#   * no sticky sessions on the target group (see main.tf) — the app holds no
#     server-side session
#
# This file is the whole Rearchitect environment; there is no path switch.
# =============================================================================

resource "random_id" "bucket" {
  byte_length = 4
}

resource "aws_s3_bucket" "archive" {
  bucket        = "${local.name}-archive-${random_id.bucket.hex}"
  force_destroy = true # exercise convenience: destroy removes the objects too
  tags          = local.tags
}

resource "aws_s3_bucket_public_access_block" "archive" {
  bucket                  = aws_s3_bucket.archive.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "archive" {
  bucket = aws_s3_bucket.archive.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "archive" {
  bucket = aws_s3_bucket.archive.id

  versioning_configuration {
    status = "Enabled"
  }
}

# --- task role: this bucket, these actions, nothing else ----------------------
data "aws_iam_policy_document" "archive_write" {

  statement {
    sid       = "PutOrderArchives"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.archive.arn}/orders/*"]
  }
}

resource "aws_iam_role" "task" {
  name               = "${local.name}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
  tags               = local.tags
}

resource "aws_iam_role_policy" "task_archive" {
  name   = "archive-write"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.archive_write.json
}

# --- task definition ---------------------------------------------------------
resource "aws_ecs_task_definition" "rearchitect" {
  count = var.image_uri != "" ? 1 : 0

  family                   = "${local.name}-rearchitect"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  # Must match the architecture the image was built for. The README's build
  # step uses --platform linux/amd64 so this is correct even when you build on
  # an Apple Silicon laptop; override var.cpu_architecture to ARM64 if you build
  # natively for Graviton.
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = var.cpu_architecture
  }

  container_definitions = jsonencode([
    {
      name      = "orders"
      image     = var.image_uri
      essential = true

      portMappings = [
        {
          containerPort = 9080
          protocol      = "tcp"
        }
      ]

      # Externalized configuration: the bucket arrives as an environment
      # variable, credentials come from the task role. Nothing environment
      # specific is baked into the image.
      environment = [
        { name = "ORDERS_ARCHIVE_BUCKET", value = aws_s3_bucket.archive.bucket },
        { name = "AWS_REGION", value = var.region },
        { name = "PRICING_ENDPOINT", value = "http://pricing.internal/pricing" }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.app.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "rearchitect"
        }
      }
    }
  ])

  tags = local.tags
}

resource "aws_ecs_service" "rearchitect" {
  count = var.image_uri != "" ? 1 : 0

  name            = "${local.name}-rearchitect"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.rearchitect[0].arn
  desired_count   = var.desired_count

  capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
  }

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.task.id]
    assign_public_ip = true # public subnets, no NAT gateway
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.this.arn
    container_name   = "orders"
    container_port   = 9080
  }

  health_check_grace_period_seconds = 60

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  depends_on = [aws_lb_listener.http]

  tags = local.tags
}
