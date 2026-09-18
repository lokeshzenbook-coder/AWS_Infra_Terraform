"""Estimate the monthly infrastructure cost of this Terraform repo.

Queries the AWS Pricing API through boto3 for on-demand EC2 and EBS (gp3)
rates, then produces a human-readable cost report. If the Pricing API is
unavailable (no credentials, offline, etc.) the script falls back to a small
built-in table so the report still gets produced.

Only resources that actually incur charges are priced:
  - EC2 instance          -> on-demand hourly rate x assumed running hours
  - EBS root volume (gp3) -> per-GB-month x volume size
Everything else (VPC, subnet, route table, internet gateway, security group)
is listed as free.

Configuration comes from CLI args first, then environment variables:
  --region           AWS region (env: AWS_REGION, default us-east-1)
  --instance-type    EC2 instance type (env: INSTANCE_TYPE, default t3.small)
  --volume-gb        Root volume size in GB (env: VOLUME_GB, default 30)
  --hours-per-month  Running hours per month (env: HOURS_PER_MONTH, default 730)
  --output           markdown | json | table
  --report-path      Where to write the report (default cost_report.md)
"""

import argparse
import json
import os
import sys
from datetime import datetime

import boto3
from botocore.exceptions import BotoCoreError, ClientError

REGION_LOCATIONS = {
    "us-east-1": "US East (N. Virginia)",
    "us-east-2": "US East (Ohio)",
    "us-west-1": "US West (N. California)",
    "us-west-2": "US West (Oregon)",
    "ca-central-1": "Canada (Central)",
    "sa-east-1": "South America (Sao Paulo)",
    "eu-west-1": "EU (Ireland)",
    "eu-west-2": "EU (London)",
    "eu-west-3": "EU (Paris)",
    "eu-central-1": "EU (Frankfurt)",
    "eu-north-1": "EU (Stockholm)",
    "ap-south-1": "Asia Pacific (Mumbai)",
    "ap-southeast-1": "Asia Pacific (Singapore)",
    "ap-southeast-2": "Asia Pacific (Sydney)",
    "ap-northeast-1": "Asia Pacific (Tokyo)",
    "ap-northeast-2": "Asia Pacific (Seoul)",
}

EC2_FALLBACK_HOURLY = {
    "t2.micro": 0.0116,
    "t2.small": 0.0230,
    "t2.medium": 0.0464,
    "t3.nano": 0.0052,
    "t3.micro": 0.0104,
    "t3.small": 0.0208,
    "t3.medium": 0.0416,
    "t3.large": 0.0832,
    "t3.xlarge": 0.1664,
    "t3.2xlarge": 0.3328,
    "t4g.nano": 0.0042,
    "t4g.micro": 0.0084,
    "t4g.small": 0.0168,
    "t4g.medium": 0.0336,
    "t4g.large": 0.0672,
    "t4g.xlarge": 0.1344,
    "t4g.2xlarge": 0.2688,
    "m5.large": 0.0960,
    "m5.xlarge": 0.1920,
    "m5.2xlarge": 0.3840,
}

EBS_FALLBACK_PER_GB = 0.08

FREE_RESOURCES = [
    ("VPC", "aws_vpc"),
    ("Internet Gateway", "aws_internet_gateway"),
    ("Public Subnet", "aws_subnet"),
    ("Route Table", "aws_route_table"),
    ("Security Group", "aws_security_group"),
]


def parse_args():
    parser = argparse.ArgumentParser(description="Estimate AWS infrastructure cost.")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-east-1"))
    parser.add_argument("--instance-type", default=os.environ.get("INSTANCE_TYPE", "t3.small"))
    parser.add_argument(
        "--volume-gb", type=int, default=int(os.environ.get("VOLUME_GB", "30"))
    )
    parser.add_argument(
        "--hours-per-month",
        type=float,
        default=float(os.environ.get("HOURS_PER_MONTH", "730")),
    )
    parser.add_argument(
        "--output", choices=["markdown", "json", "table"], default="markdown"
    )
    parser.add_argument(
        "--report-path", default=os.environ.get("REPORT_PATH", "cost_report.md")
    )
    return parser.parse_args()


def extract_price(terms):
    """Return the first positive USD on-demand price found in a price list term."""
    for offer in terms.get("OnDemand", {}).values():
        for dimension in offer.get("priceDimensions", {}).values():
            rate = float(dimension.get("pricePerUnit", {}).get("USD", 0.0))
            if rate > 0.0:
                return rate
    return None


def get_first_price(pricing, service_code, filters):
    """Call get_products and return the first positive USD price, or None."""
    try:
        response = pricing.get_products(
            ServiceCode=service_code, Filters=filters, MaxResults=10
        )
        for raw_price in response.get("PriceList", []):
            product = json.loads(raw_price)
            rate = extract_price(product.get("terms", {}))
            if rate is not None:
                return rate
    except ClientError as exc:
        print(f"[cost-estimator] Pricing API error: {exc}", file=sys.stderr)
    except BotoCoreError as exc:
        print(f"[cost-estimator] AWS client error: {exc}", file=sys.stderr)
    return None


def fetch_ec2_hourly(pricing, instance_type, location):
    filters = [
        {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
        {"Type": "TERM_MATCH", "Field": "location", "Value": location},
        {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": "Linux"},
        {"Type": "TERM_MATCH", "Field": "tenancy", "Value": "Shared"},
        {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"},
        {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
    ]
    return get_first_price(pricing, "AmazonEC2", filters)


def fetch_ebs_per_gb(pricing, location):
    filters = [
        {"Type": "TERM_MATCH", "Field": "volumeApiName", "Value": "gp3"},
        {"Type": "TERM_MATCH", "Field": "location", "Value": location},
    ]
    return get_first_price(pricing, "AmazonEC2", filters)


def currency(amount):
    return f"${amount:,.4f}"


def usd_safe(amount):
    return 0.0 if amount is None else amount


def estimate(args):
    location = REGION_LOCATIONS.get(args.region, args.region)
    used_pricing_api = True

    pricing = boto3.client("pricing", region_name="us-east-1")
    ec2_hourly = fetch_ec2_hourly(pricing, args.instance_type, location)
    ebs_per_gb = fetch_ebs_per_gb(pricing, location)

    if ec2_hourly is None or ebs_per_gb is None:
        used_pricing_api = False
        ec2_hourly = ec2_hourly or EC2_FALLBACK_HOURLY.get(args.instance_type)
        ebs_per_gb = ebs_per_gb or EBS_FALLBACK_PER_GB
        print(
            "[cost-estimator] Pricing API unavailable or incomplete; "
            "using built-in baseline rates.",
            file=sys.stderr,
        )

    if ec2_hourly is None:
        print(
            f"[cost-estimator] Warning: no pricing found for '{args.instance_type}'. "
            "EC2 line treated as $0.",
            file=sys.stderr,
        )
        ec2_hourly = 0.0

    ec2_monthly = ec2_hourly * args.hours_per_month
    ebs_monthly = ebs_per_gb * args.volume_gb
    total_monthly = ec2_monthly + ebs_monthly
    total_yearly = total_monthly * 12

    return {
        "generated_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"),
        "region": args.region,
        "instance_type": args.instance_type,
        "volume_gb": args.volume_gb,
        "hours_per_month": args.hours_per_month,
        "source": ("AWS Pricing API (boto3)" if used_pricing_api else "fallback table"),
        "ec2_hourly": ec2_hourly,
        "ec2_monthly": ec2_monthly,
        "ebs_per_gb": ebs_per_gb,
        "ebs_monthly": ebs_monthly,
        "total_monthly": total_monthly,
        "total_yearly": total_yearly,
        "total_hourly": total_monthly / args.hours_per_month,
    }


def render_table(data):
    rows = [
        ("VPC", "aws_vpc", "Fixed infrastructure", "$0.00"),
        ("Internet Gateway", "aws_internet_gateway", "Fixed infrastructure", "$0.00"),
        ("Public Subnet", "aws_subnet", "Fixed infrastructure", "$0.00"),
        ("Route Table", "aws_route_table", "Fixed infrastructure", "$0.00"),
        ("Security Group", "aws_security_group", "Fixed infrastructure", "$0.00"),
        (
            "EC2 instance",
            "aws_instance",
            f"{data['instance_type']} @ {currency(data['ec2_hourly'])}/hr",
            f"{currency(data['ec2_monthly'])}/mo",
        ),
        (
            "EBS root volume",
            "aws_ebs_volume",
            f"gp3, {data['volume_gb']} GB @ {currency(data['ebs_per_gb'])}/GB-mo",
            f"{currency(data['ebs_monthly'])}/mo",
        ),
    ]

    width_name = max(len(r[0]) for r in rows)
    width_type = max(len(r[1]) for r in rows)
    width_basis = max(len(r[2]) for r in rows)
    width_cost = max(len(r[3]) for r in rows)

    line = f"+{'-' * (width_name + 2)}+{'-' * (width_type + 2)}+{'-' * (width_basis + 2)}+{'-' * (width_cost + 2)}+"

    def fmt(name, rtype, basis, cost):
        return (
            f"| {name:<{width_name}} "
            f"| {rtype:<{width_type}} "
            f"| {basis:<{width_basis}} "
            f"| {cost:<{width_cost}} |"
        )

    out = [line, fmt("Resource", "Terraform type", "Basis", "Est. cost"), line]
    out.extend(fmt(*r) for r in rows)
    out.append(line)
    out.append("")
    out.append(
        f"TOTAL : {currency(data['total_monthly'])}/month "
        f"({currency(data['total_yearly'])}/year, "
        f"~{currency(data['total_hourly'])}/hr)"
    )
    out.append(f"Source: {data['source']} | Region: {data['region']}")
    return "\n".join(out)


def render_markdown(data):
    header = f"""# AWS Infrastructure Cost Estimate

Generated: {data['generated_at']} · Region: `{data['region']}` · Source: {data['source']}

## Resource breakdown

| Resource | Terraform type | Basis | Est. cost |
|---|---|---|---|
"""
    rows = []
    for name in ("VPC", "Internet Gateway", "Public Subnet", "Route Table", "Security Group"):
        rows.append(f"| {name} | aws_* | Fixed infrastructure | $0.00 |")
    rows.append(
        f"| EC2 instance | aws_instance | `{data['instance_type']}` Linux @ "
        f"{currency(data['ec2_hourly'])}/hr | {currency(data['ec2_monthly'])}/mo |"
    )
    rows.append(
        f"| EBS root volume | aws_ebs_volume | gp3 {data['volume_gb']} GB @ "
        f"{currency(data['ebs_per_gb'])}/GB-mo | {currency(data['ebs_monthly'])}/mo |"
    )
    summary = f"""
## Summary

| Metric | Est. cost |
|---|---|
| Per hour | ~{currency(data['total_hourly'])} |
| Per month | **{currency(data['total_monthly'])}** |
| Per year | {currency(data['total_yearly'])} |

## Assumptions

- On-demand pricing for Linux EC2 and gp3 EBS in `{data['region']}`.
- Instance runs **{data['hours_per_month']:.0f} hours/month** (24x7 default).
- Excludes data transfer, Elastic IP, NAT gateway, and other usage.
"""
    return header + "\n".join(rows) + summary


def render_json(data):
    return json.dumps(data, indent=2)


def main():
    args = parse_args()
    try:
        data = estimate(args)
    except (ClientError, BotoCoreError) as exc:
        print(f"[cost-estimator] Could not reach AWS: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.output == "json":
        report = render_json(data)
    elif args.output == "table":
        report = render_table(data)
    else:
        report = render_markdown(data)

    print(report)

    if args.output == "markdown":
        with open(args.report_path, "w", encoding="utf-8") as handle:
            handle.write(report)
        print(f"\n[cost-estimator] Report written to {args.report_path}", file=sys.stderr)


if __name__ == "__main__":
    main()