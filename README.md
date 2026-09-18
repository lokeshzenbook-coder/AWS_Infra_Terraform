# AWS_Infra_Terraform

Terraform-managed AWS infrastructure with **automatic cost estimation via a Python `boto3` script** running in CI.

The infrastructure builds a minimal, publicly reachable stack:

| Resource                       | Terraform resource            |
|--------------------------------|-------------------------------|
| VPC (`10.0.0.0/16`)            | `aws_vpc`                     |
| Internet Gateway               | `aws_internet_gateway`        |
| Public Subnet (`10.0.1.0/24`)  | `aws_subnet`                  |
| Route Table + association      | `aws_route_table(_association)` |
| Security Group (SSH/HTTP)      | `aws_security_group`          |
| EC2 instance + 30 GB gp3 EBS   | `aws_instance`                |

## Repository layout

```
.
├── .github/workflows/terraform.yaml   # CI/CD: plan/apply + boto3 cost estimate
├── scripts/
│   ├── cost_estimator.py             # Python cost estimator (AWS Pricing API)
│   └── requirements.txt              # Python dependencies (boto3)
├── main.tf                           # Core Terraform infrastructure
├── variables.tf                      # Input variables
├── outputs.tf                        # Outputs (ids, public IP/DNS)
├── terraform.tfvars.example          # Template for your variable values
└── .gitignore
```

## How the cost estimator works

`scripts/cost_estimator.py` uses **boto3** to query the AWS Pricing API for on-demand rates:

- **EC2** — hourly rate for the configured instance type (Linux, shared tenancy)
- **EBS (gp3)** — per-GB-month storage rate × volume size

Free components (VPC, subnet, route table, internet gateway, security group)
are listed with `$0.00`. The report gives hourly, monthly, and yearly totals.
If the Pricing API is unreachable (e.g. a fork without secrets), it falls back
to a built-in rate table so the report is still produced.

```
python scripts/cost_estimator.py --output markdown
```

CLI args (env-var fallbacks in parentheses):

| Flag                 | Default      | Env var        |
|----------------------|--------------|----------------|
| `--region`           | `us-east-1`  | `AWS_REGION`   |
| `--instance-type`    | `t3.small`   | `INSTANCE_TYPE`|
| `--volume-gb`        | `30`         | `VOLUME_GB`    |
| `--hours-per-month`  | `730`        | `HOURS_PER_MONTH` |
| `--output`           | `markdown`   | —              |

`--output` supports `markdown`, `table`, and `json`.

## AWS credentials setup (one-time)

No OIDC is used. Add the following to **Settings → Secrets and variables → Actions → Secrets**:

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_SESSION_TOKEN` *(optional — only for temporary credentials)*

> Use a dedicated IAM user with permissions for the resources this config manages.
> The cost estimator reads the public Pricing API; it does not read Cost Explorer.

## Variable values (CI)

The Terraform `plan`/`apply` steps need these as GitHub Actions **Variables** (non-secret):

- `AMI_ID`
- `KEY_NAME`
- `MY_IP`

The cost estimator honors these optional Variables with defaults:

- `INSTANCE_TYPE` (default `t3.small`) — keep in sync with `variables.tf`
- `VOLUME_GB` (default `30`)
- `HOURS_PER_MONTH` (default `730`)
- `COST_REGION` (default `us-east-1`)

## Local run

```sh
cp terraform.tfvars.example terraform.tfvars   # fill in ami_id, key_name, my_ip
terraform init
terraform plan
terraform apply
```

## Outputs

After `apply`, outputs (`vpc_id`, `subnet_id`, `security_group_id`, `instance_id`,
`public_ip`, `public_dns`) are printed by Terraform.