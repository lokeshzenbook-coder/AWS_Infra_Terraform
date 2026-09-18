# AWS_Infra_Terraform

Terraform infrastructure (VPC, public subnet, IGW, route table, security group, EC2) provisioned by a GitHub Actions workflow (`terraform.yaml`) using static AWS credentials stored as GitHub Actions secrets.

## AWS credentials setup (one-time)

No OIDC is used. Add the following to **Settings → Secrets and variables → Actions → Secrets**:

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_SESSION_TOKEN` *(optional — only if your credentials are temporary)*

The workflow references them via `${{ secrets.AWS_ACCESS_KEY_ID }}` etc.

> Use a dedicated IAM user whose policy grants at least EC2/VPC/IAM management permissions needed by this Terraform config.

## Variable values

`ami_id`, `key_name`, and `my_ip` have no defaults — provide them via a
`terraform.tfvars` file (gitignored) for local runs, or as GitHub Actions
**Variables** (non-secret) so `terraform plan` can run in CI:

- `AMI_ID`
- `KEY_NAME`
- `MY_IP`

## Local run

```sh
terraform init
terraform plan
terraform apply
```

## Manual run

**Actions → Terraform → Run workflow.**