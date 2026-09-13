variable "region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name. Also used as the Terraform workspace / state key."
  type        = string
  default     = "production"

  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be one of: staging, production."
  }
}

variable "cluster_name" {
  description = "EKS cluster name."
  type        = string
  default     = "capstone"
}

variable "cluster_version" {
  description = "Kubernetes minor version for the EKS control plane."
  type        = string
  default     = "1.31"
}

variable "vpc_cidr" {
  description = <<-DESC
    CIDR block for the VPC. Deliberately NOT 10.0.0.0/16: this account already
    holds an unrelated VPC on that range (Project=Jerney). Overlapping CIDRs are
    legal but can never be peered, so the two are kept apart from the start.
  DESC
  type        = string
  default     = "10.1.0.0/16"
}

variable "az_count" {
  description = <<-DESC
    Availability zones to spread subnets across. EKS requires a minimum of 2.
    Two is the right answer for a learning cluster -- a third AZ buys resilience
    you do not need and more subnets to reason about.
  DESC
  type        = number
  default     = 2

  validation {
    condition     = var.az_count >= 2 && var.az_count <= 4
    error_message = "EKS requires at least 2 AZs; more than 4 is wasteful here."
  }
}

variable "node_instance_types" {
  description = "Instance types for the managed node group."
  type        = list(string)
  default     = ["t3.medium"]
}

variable "node_desired_size" {
  description = "Desired node count. Two t3.medium fit the whole demo stack comfortably."
  type        = number
  default     = 2
}

variable "node_capacity_type" {
  description = <<-DESC
    ON_DEMAND or SPOT. SPOT is 60-70% cheaper and is the single biggest saving
    available on the node bill. The trade is that AWS can reclaim an instance with
    two minutes notice; the node group simply replaces it. Fine for learning,
    wrong for anything with real users.
  DESC
  type        = string
  default     = "SPOT"

  validation {
    condition     = contains(["ON_DEMAND", "SPOT"], var.node_capacity_type)
    error_message = "node_capacity_type must be ON_DEMAND or SPOT."
  }
}

variable "node_disk_size" {
  description = "EBS volume per node, in GB. 20 holds the demo images with room to spare."
  type        = number
  default     = 20
}

variable "node_min_size" {
  description = "Minimum node count."
  type        = number
  default     = 2
}

variable "node_max_size" {
  description = "Maximum node count."
  type        = number
  default     = 4
}

variable "enable_nat_gateway" {
  description = <<-DESC
    A NAT gateway costs roughly $33/month before data charges, and exists only so
    that nodes in PRIVATE subnets can reach the internet. Setting this false and
    placing nodes in public subnets removes that cost entirely.

    Kept TRUE by default. The cheaper alternative -- public subnets, no NAT --
    needs the node group's launch template to request a public IP via a
    network_interfaces block; the EKS module has no top-level setting for it, and
    getting it wrong means nodes silently launch with no route to the internet and
    never join the cluster.

    Billing is hourly, so with the destroy-nightly workflow this is roughly
    $0.045/hour rather than the $33/month a permanently-running NAT would cost.
  DESC
  type        = bool
  default     = true
}

variable "single_nat_gateway" {
  description = "When NAT is enabled, share one gateway across AZs rather than one per AZ."
  type        = bool
  default     = true
}

variable "nodes_in_public_subnets" {
  description = <<-DESC
    Place worker nodes in public subnets instead of private.

    Leave FALSE unless you also add a network_interfaces block to the node group
    requesting a public IP. Subnet-level map_public_ip_on_launch alone is not
    reliably honoured once the EKS module attaches its own launch template, so
    nodes can come up with no internet route and no error until the node group
    times out ~20 minutes in.
  DESC
  type        = bool
  default     = false
}

variable "cluster_log_types" {
  description = <<-DESC
    EKS control plane logs shipped to CloudWatch. Each stream is billed on ingest
    and storage. Empty by default -- turn on "audit" when you actually want to
    inspect API activity.
  DESC
  type        = list(string)
  default     = []
}

variable "cluster_endpoint_public_access_cidrs" {
  description = <<-DESC
    CIDRs allowed to reach the public Kubernetes API endpoint. Defaults to open,
    matching the Civo firewall this replaces (6443 from 0.0.0.0/0). Narrow this
    to your egress IP once you know it.
  DESC
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "argocd_chart_version" {
  description = "argo-cd Helm chart version. Pinned so a cluster rebuild is reproducible."
  type        = string
  default     = "7.7.11"
}

variable "lb_controller_chart_version" {
  description = "aws-load-balancer-controller Helm chart version."
  type        = string
  default     = "1.10.1"
}
