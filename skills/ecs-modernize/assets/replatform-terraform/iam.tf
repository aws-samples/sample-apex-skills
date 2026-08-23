# =============================================================================
# SKELETON — IAM for the Replatform environment
#
# Three roles, each with a stated reason to exist:
#
#   * instance   — lets the EC2 container instances register with the cluster
#   * execution  — lets ECS pull the image and write logs
#   * exec_access — ECS Exec only, and only when it is enabled
#
# No task role granting application permissions is generated: an unchanged
# lift-and-shift typically calls no AWS API. If the application does call one,
# add a task role with exactly those actions and cite the code evidence.
# =============================================================================

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# --- IAM path ----------------------------------------------------------------
#
# Every role and instance profile below sits under a shared path. That is what
# lets the operator's own permissions be scoped: an IAM statement can name
# `arn:aws:iam::*:role/ecs-modernize/*` and cover exactly the roles this skeleton
# creates, which is impossible when role names come from a user-supplied prefix.
# See references/iam-policy.json (ExecutionTerraformIAM*).

# --- container instance role --------------------------------------------------

resource "aws_iam_role" "instance" {
  name               = "${local.name}-instance"
  path               = var.iam_role_path
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "instance_ecs" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role"
}

# Required for ECS Exec: the SSM agent on the instance brokers the session.
resource "aws_iam_role_policy_attachment" "instance_ssm" {
  count      = var.enable_execute_command ? 1 : 0
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "instance" {
  name = "${local.name}-instance"
  path = var.iam_role_path
  role = aws_iam_role.instance.name
  tags = local.tags
}

# --- task execution role ------------------------------------------------------

resource "aws_iam_role" "execution" {
  name               = "${local.name}-execution"
  path               = var.iam_role_path
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# NOTE: if the task definition uses `secrets` (SSM Parameter Store / Secrets
# Manager), extend this execution role with an inline policy granting
# ssm:GetParameters / secretsmanager:GetSecretValue (and kms:Decrypt for a
# customer-managed key) for the referenced ARNs. AmazonECSTaskExecutionRolePolicy
# does NOT grant read access to your parameters/secrets, so tasks fail to start
# without it. This skeleton ships no `secrets` by default, so no such policy is
# generated here.

# --- task role for ECS Exec only ---------------------------------------------
#
# ECS Exec uses the TASK role, not the execution role — a common source of
# "why does exec fail with a valid execution role" confusion. These actions do
# not support resource-level permissions, so "*" is the documented grant:
# https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec.html

data "aws_iam_policy_document" "exec_access" {
  count = var.enable_execute_command ? 1 : 0

  statement {
    sid = "SsmMessageChannel"

    actions = [
      "ssmmessages:CreateControlChannel",
      "ssmmessages:CreateDataChannel",
      "ssmmessages:OpenControlChannel",
      "ssmmessages:OpenDataChannel",
    ]

    resources = ["*"]
  }
}

resource "aws_iam_role" "exec_access" {
  count              = var.enable_execute_command ? 1 : 0
  name               = "${local.name}-task-exec-access"
  path               = var.iam_role_path
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
  tags               = local.tags
}

resource "aws_iam_role_policy" "exec_access" {
  count  = var.enable_execute_command ? 1 : 0
  name   = "ecs-exec"
  role   = aws_iam_role.exec_access[0].id
  policy = data.aws_iam_policy_document.exec_access[0].json
}
