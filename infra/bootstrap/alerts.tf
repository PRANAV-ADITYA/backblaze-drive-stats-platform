resource "aws_iam_policy" "github_apply_alerts" {
  name        = "dsl-dev-github-apply-alerts"
  description = "Lets CI manage the dev alert topic, CloudWatch alarms and EventBridge rules"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AlertTopic"
        Effect = "Allow"
        Action = [
          "sns:CreateTopic",
          "sns:DeleteTopic",
          "sns:GetTopicAttributes",
          "sns:SetTopicAttributes",
          "sns:ListTagsForResource",
          "sns:TagResource",
          "sns:UntagResource"
        ]
        Resource = "arn:aws:sns:ap-southeast-2:739871966917:dsl-dev-*"
      },
      {
        Sid    = "Alarms"
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricAlarm",
          "cloudwatch:DeleteAlarms",
          "cloudwatch:ListTagsForResource",
          "cloudwatch:TagResource",
          "cloudwatch:UntagResource"
        ]
        Resource = "arn:aws:cloudwatch:ap-southeast-2:739871966917:alarm:dsl-dev-*"
      },
      {
        Sid      = "DescribeAlarms"
        Effect   = "Allow"
        Action   = ["cloudwatch:DescribeAlarms"]
        Resource = "*"
      },
      {
        Sid    = "Dashboards"
        Effect = "Allow"
        Action = [
          "cloudwatch:PutDashboard",
          "cloudwatch:GetDashboard",
          "cloudwatch:DeleteDashboards"
        ]
        Resource = "arn:aws:cloudwatch::739871966917:dashboard/dsl-dev-*"
      },
      {
        Sid    = "EventRules"
        Effect = "Allow"
        Action = [
          "events:PutRule",
          "events:DeleteRule",
          "events:DescribeRule",
          "events:PutTargets",
          "events:RemoveTargets",
          "events:ListTargetsByRule",
          "events:ListTagsForResource",
          "events:TagResource",
          "events:UntagResource"
        ]
        Resource = "arn:aws:events:ap-southeast-2:739871966917:rule/dsl-dev-*"
      }
    ]
  })
}

resource "aws_iam_user_policy_attachment" "github_apply_alerts" {
  user       = aws_iam_user.github_apply.name
  policy_arn = aws_iam_policy.github_apply_alerts.arn
}
