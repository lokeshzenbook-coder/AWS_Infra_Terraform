output "vpc_id" {
  value = aws_vpc.main.id
}

output "subnet_id" {
  value = aws_subnet.public.id
}

output "security_group_id" {
  value = aws_security_group.ec2.id
}

output "instance_id" {
  value = aws_instance.app.id
}

output "public_ip" {
  value = aws_instance.app.public_ip
}

output "public_dns" {
  value = aws_instance.app.public_dns
}

output "account_id" {
  value = data.aws_caller_identity.current.account_id
}

output "oidc_provider_arn" {
  value = aws_iam_openid_connect_provider.github.arn
}

output "oidc_role_arn" {
  description = "ARN of the IAM role to use in .github/workflows/terraform.yaml"
  value       = aws_iam_role.github_actions.arn
}