# =============================================================================
# IAM shared by both paths.
#
# The task EXECUTION role is what the ECS agent uses to pull the image and ship
# logs; both paths need it and it is identical for both. The task ROLE — the
# credentials the application itself gets — is path-specific and lives in
# rearchitect.tf, because only the rearchitected app calls an AWS API. The
# Replatform task definition deliberately has no task role at all.
# =============================================================================

data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${local.name}-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}
