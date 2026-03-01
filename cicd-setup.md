# CI/CD Setup Guide

The deployment workflow uses **GitHub Actions with OIDC** to authenticate against AWS — no long-lived access keys stored anywhere.

## How it works

```
GitHub Actions → "Deploy Data Ingestion Stack" (workflow_dispatch)
  ↓ choose: stack / entry_point / environment / action
  ↓
  Assumes AWS IAM Role via OIDC (no stored credentials)
  ↓
  cdk synth  →  cdk diff | cdk deploy | cdk destroy
```

Each environment (`dev`, `prod`) maps to a **separate AWS account** and a separate GitHub Environment with its own set of secrets and (optionally) required reviewers.

---

## 1. Create GitHub Environments

In your repository go to **Settings → Environments** and create two environments:

| Environment | Protection rules |
|-------------|-----------------|
| `dev`       | None (deploy freely) |
| `prod`      | ✅ Required reviewers — add yourself or your team |

The `prod` environment protection means any `deploy` or `destroy` targeting prod will pause and wait for a manual approval before the job runs.

---

## 2. Configure AWS OIDC Trust (once per account)

https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws

https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html

---

## 3. Add Secrets to Each GitHub Environment

In **Settings → Environments → [environment name] → Environment secrets**, add:

| Secret name     | Value | Required |
|-----------------|-------|----------|
| `AWS_ROLE_ARN`  | `arn:aws:iam::<ACCOUNT_ID>:role/GitHubActions-CDK-Deploy` | ✅ |
| `AWS_REGION`    | `eu-west-2` | ✅ |
| `CDK_ACCOUNT_ID`| `<ACCOUNT_ID>` | ✅ |
| `ALERT_EMAIL`   | Your email address for CloudWatch alarm notifications | Optional |

Each environment has different `AWS_ROLE_ARN` and `CDK_ACCOUNT_ID` values pointing to their respective AWS accounts.

---

## 4. Using the Workflow

Go to **Actions → Deploy Data Ingestion Stack → Run workflow**:

| Input | Options | Description |
|-------|---------|-------------|
| Stack | `DataIngestionStack-Dev` / `DataIngestionStack-Prod` | Which CDK stack to target |
| Entry point | `src/python/cdk/app.py` | CDK app entry point (rarely changes) |
| Environment | `dev` / `prod` | AWS account to deploy into |
| Action | `diff` / `deploy` / `destroy` | What to do |

### Recommended flow

1. **Always run `diff` first** to preview changes
2. Review the diff output in the Actions run log
3. If it looks good, re-run with `deploy`
4. `destroy` tears everything down — use with caution on prod (will be blocked by required reviewers)

### Stack / environment validation

The workflow enforces that `DataIngestionStack-Dev` can only be used with `dev` and `DataIngestionStack-Prod` can only be used with `prod`. Mismatches fail fast before any AWS calls are made.

---

## 5. CDK Outputs

After a successful `deploy`, the stack outputs (API URL, table name, etc.) are automatically saved as a downloadable artifact named `cdk-outputs-<env>-<run_id>` in the Actions run. You can use these values directly in `test_api.sh`.
