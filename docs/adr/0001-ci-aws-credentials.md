# ADR 0001: CI uses IAM user access keys instead of OIDC

**Status:** Accepted
**Date:** 2026-10-05

## Context

GitHub Actions needs AWS access to run `terraform plan` on pull requests and
`terraform apply` on `main`. The standard approach is OIDC federation: short-lived
credentials, no stored secrets.

This AWS account is on the Free plan. An AWS-managed service control policy (SCP)
explicitly denies `iam:CreateOpenIDConnectProvider`, so OIDC cannot be set up.
Unlocking it requires the Paid plan and activating advanced features, which is
irreversible and removes the Free plan's guarantee of no charges.

## Decision

Use two IAM users with long-lived access keys, mirroring the intended OIDC roles:

- `dsl-dev-github-plan`: `ReadOnlyAccess` + dev Terraform state. Key stored as a
  repository secret; used by pull-request workflows.
- `dsl-dev-github-apply`: dev state + `s3:*` on `dsl-dev-*` buckets only. Key stored
  as a secret of the GitHub Environment `dev`, which only the `main` branch can use.

Keys are created with the AWS CLI and piped directly into GitHub secrets; they never
touch Terraform state, files, or logs. Users have no console password.

## Consequences

- Long-lived credentials exist. Mitigated by: least-privilege policies, read/write
  split, the environment restriction to `main`, GitHub withholding secrets from fork
  pull requests, and rotation every 90 days.
- Rotation is manual (calendar reminder; runbook to follow).
- Permissions grow phase by phase through reviewed pull requests.

## Alternatives considered

- **OIDC:** preferred, blocked by the SCP. The intended configuration is kept in
  `docs/reference/github_oidc.tf.example`.
- **Paid plan + advanced features:** unlocks OIDC, but irreversible and exposes the
  account to charges beyond credits.
- **No AWS access in CI, deploy from laptop:** no stored keys, but manual deploys and
  no automated plans on pull requests.

## Revisit when

The account moves to the Paid plan, or the project moves to an account without this
SCP. Then switch to OIDC and delete both IAM users.
