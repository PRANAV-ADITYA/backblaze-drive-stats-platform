# CI identities for GitHub Actions.
# The Free plan's SCP blocks OIDC, so CI uses IAM users with access keys.
# Keys are created outside Terraform, so secrets never enter the state file,
# and are stored directly in GitHub secrets. Rotate every 90 days.

# --- What the users may do ---

# Read and write dev's Terraform state (state file + lock file).
data "aws_iam_policy_document" "dev_state" {
  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.tfstate.arn]
  }
  statement {
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.tfstate.arn}/dev/*"]
  }
}

# Manage dev's S3 buckets only. Later phases add more through PRs.
data "aws_iam_policy_document" "dev_apply" {
  statement {
    actions = ["s3:*"]
    resources = [
      "arn:aws:s3:::dsl-dev-*",
      "arn:aws:s3:::dsl-dev-*/*",
    ]
  }
}

# --- User for pull requests: look, don't touch ---

resource "aws_iam_user" "github_plan" {
  name = "dsl-dev-github-plan"
}

resource "aws_iam_user_policy_attachment" "github_plan_readonly" {
  user       = aws_iam_user.github_plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

resource "aws_iam_user_policy" "github_plan_state" {
  name   = "dev-terraform-state"
  user   = aws_iam_user.github_plan.name
  policy = data.aws_iam_policy_document.dev_state.json
}

# --- User for main: change dev ---

resource "aws_iam_user" "github_apply" {
  name = "dsl-dev-github-apply"
}

resource "aws_iam_user_policy" "github_apply_state" {
  name   = "dev-terraform-state"
  user   = aws_iam_user.github_apply.name
  policy = data.aws_iam_policy_document.dev_state.json
}

resource "aws_iam_user_policy" "github_apply_permissions" {
  name   = "dev-resources"
  user   = aws_iam_user.github_apply.name
  policy = data.aws_iam_policy_document.dev_apply.json
}

output "github_plan_user" {
  value = aws_iam_user.github_plan.name
}

output "github_apply_user" {
  value = aws_iam_user.github_apply.name
}
