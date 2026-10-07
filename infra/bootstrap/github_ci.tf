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

# --- Catalog and query permissions for the apply user (Step 2.6b) ---
# Lets CI create dev's Glue Data Catalog tables and Athena workgroup,
# and nothing outside names starting with dsl_dev_ / dsl-dev-.

locals {
  ci_region  = "ap-southeast-2"
  ci_account = data.aws_caller_identity.current.account_id
}

data "aws_iam_policy_document" "dev_apply_catalog" {
  statement {
    sid     = "GlueCatalogDev"
    actions = ["glue:*"]
    resources = [
      "arn:aws:glue:${local.ci_region}:${local.ci_account}:catalog",
      "arn:aws:glue:${local.ci_region}:${local.ci_account}:database/dsl_dev_*",
      "arn:aws:glue:${local.ci_region}:${local.ci_account}:table/dsl_dev_*/*",
    ]
  }

  statement {
    sid       = "AthenaWorkgroupDev"
    actions   = ["athena:*"]
    resources = ["arn:aws:athena:${local.ci_region}:${local.ci_account}:workgroup/dsl-dev-*"]
  }
}

resource "aws_iam_user_policy" "github_apply_catalog" {
  name   = "dev-catalog"
  user   = aws_iam_user.github_apply.name
  policy = data.aws_iam_policy_document.dev_apply_catalog.json
}

# --- Image repository permissions for the apply user (Step 2.7) ---
# Lets CI create and configure dev's ECR repositories, named dsl-dev-*.

data "aws_iam_policy_document" "dev_apply_ecr" {
  statement {
    sid       = "EcrRepositoriesDev"
    actions   = ["ecr:*"]
    resources = ["arn:aws:ecr:${local.ci_region}:${local.ci_account}:repository/dsl-dev-*"]
  }
}

resource "aws_iam_user_policy" "github_apply_ecr" {
  name   = "dev-ecr"
  user   = aws_iam_user.github_apply.name
  policy = data.aws_iam_policy_document.dev_apply_ecr.json
}
