# Lets the existing scheduler role start the silver maintenance Glue job (Phase 6).
resource "aws_iam_role_policy" "scheduler_start_maintenance" {
  name = "start-silver-maintenance"
  role = "dsl-dev-scheduler"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "glue:StartJobRun"
        Resource = "arn:aws:glue:ap-southeast-2:739871966917:job/dsl-dev-silver-maintenance"
      }
    ]
  })
}
