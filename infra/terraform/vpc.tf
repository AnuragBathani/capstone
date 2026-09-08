data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  name = "${var.cluster_name}-${var.environment}"
  azs  = slice(data.aws_availability_zones.available.names, 0, var.az_count)
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.13"

  name = local.name
  cidr = var.vpc_cidr
  azs  = local.azs

  # /20 private (4094 usable) vs /24 public. The VPC CNI assigns a real VPC IP to
  # every pod, so private subnets exhaust far faster than node count suggests.
  private_subnets = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 4, i)]
  public_subnets  = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 8, i + 200)]

  # A NAT gateway is ~$33/month and is only needed when nodes sit in private
  # subnets. See variables.tf for the trade being made here.
  enable_nat_gateway     = var.enable_nat_gateway
  single_nat_gateway     = var.enable_nat_gateway && var.single_nat_gateway
  one_nat_gateway_per_az = var.enable_nat_gateway && !var.single_nat_gateway

  # Without this, nodes launched into public subnets get no public IP, cannot
  # reach the internet, fail to pull images, and never join the cluster.
  map_public_ip_on_launch = var.nodes_in_public_subnets

  # Required by the VPC CNI and by anything resolving in-cluster private endpoints.
  enable_dns_hostnames = true
  enable_dns_support   = true

  # These tags are load-bearing, not cosmetic: the AWS load balancer controller
  # discovers subnets by them. Without them, a Service of type LoadBalancer
  # provisions nothing and fails with no obvious error.
  public_subnet_tags = {
    "kubernetes.io/role/elb" = "1"
  }

  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = "1"
  }
}
