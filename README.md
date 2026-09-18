# AWS_Infra_Terraform

Terraform infrastructure (VPC, public subnet, IGW, route table, security group, EC2) and a GitHub Actions workflow (`terraform.yaml`) that provisions it using AWS OIDC — no long-lived AWS keys stored in GitHub.

## OIDC setup (one-time bootstrap)

The OIDC provider, IAM role, and its ARN are created by Terraform itself (`oidc.tf`), so the ARN is never typed into the workflow.

1. Run `terraform init && terraform apply` locally with your AWS credentials (default `aws` profile).
2. Read the generated role ARN:
   ```sh
   terraform output oidc_role_arn
   ```
3. In GitHub: **Settings → Secrets and variables → Actions → Variables**, add:
   - `AWS_ROLE_TO_ASSUME`: paste the ARN from step 2 (e.g. `arn:aws:iam::123456789012:role/github-actions-terraform`)

The workflow references it via `${{ vars.AWS_ROLE_TO_ASSUME }}`.

## Variable values

`ami_id`, `key_name`, and `my_ip` have no defaults — provide them via a
`terraform.tfvars` file (gitignored) or as GitHub Actions variables so
`terraform plan` can run.

## Manual run

**Actions → Terraform → Run workflow.**
