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

Run this in each AWS account (dev and prod) to allow GitHub Actions to assume a role without storing credentials.

### 2a. Create the OIDC identity provider

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

### 2b. Create the IAM role

Create a file `trust-policy.json`:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:fosainversa/api-ingestion:*"
        }
      }
    }
  ]
}
```

```bash
aws iam create-role \
  --role-name GitHubActions-CDK-Deploy \
  --assume-role-policy-document file://trust-policy.json \
  --description "Role assumed by GitHub Actions for CDK deployments"
```

### 2c. Attach permissions

For CDK deployments you need broad CloudFormation + service permissions. The simplest starting point:

```bash
aws iam attach-role-policy \
  --role-name GitHubActions-CDK-Deploy \
  --policy-arn arn:aws:iam::aws:policy/AdministratorAccess
```

> **Note:** For a production setup, scope this down to exactly the services CDK needs (CloudFormation, Lambda, API Gateway, DynamoDB, S3, SSM, IAM, CloudWatch, SNS, EventBridge). `AdministratorAccess` is fine for a personal/demo project.

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

## 4. Bootstrap CDK (once per account/region)

Before the first deploy, CDK needs to bootstrap the target account:

```bash
# From your local machine with the target account credentials active
cdk bootstrap aws://<ACCOUNT_ID>/eu-west-2 \
  --app "python3 src/python/cdk/app.py" \
  --trust <ACCOUNT_ID> \
  --cloudformation-execution-policies arn:aws:iam::aws:policy/AdministratorAccess
```

---

## 5. Using the Workflow

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

## 6. CDK Outputs

After a successful `deploy`, the stack outputs (API URL, table name, etc.) are automatically saved as a downloadable artifact named `cdk-outputs-<env>-<run_id>` in the Actions run. You can use these values directly in `test_api.sh`.
