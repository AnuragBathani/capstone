module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.31"

  cluster_name    = local.name
  cluster_version = var.cluster_version

  vpc_id = module.vpc.vpc_id

  # Nodes go wherever nodes_in_public_subnets says. The control plane's own ENIs
  # always sit in the private subnets regardless -- they never need egress.
  subnet_ids               = var.nodes_in_public_subnets ? module.vpc.public_subnets : module.vpc.private_subnets
  control_plane_subnet_ids = module.vpc.private_subnets

  # Public endpoint so kubectl and CI can reach the API without a bastion. This
  # mirrors the Civo firewall rule that opened 6443 to the world -- see
  # cluster_endpoint_public_access_cidrs to narrow it.
  cluster_endpoint_public_access       = true
  cluster_endpoint_public_access_cidrs = var.cluster_endpoint_public_access_cidrs
  cluster_endpoint_private_access      = true

  # CloudWatch bills per log stream ingested and stored. Off by default.
  cluster_enabled_log_types   = var.cluster_log_types
  create_cloudwatch_log_group = length(var.cluster_log_types) > 0

  # IAM Roles for Service Accounts. The EBS CSI driver below needs it, and so
  # will ArgoCD in Phase 2 if it talks to AWS APIs.
  enable_irsa = true

  # Grant the identity running `terraform apply` cluster-admin, otherwise the
  # applier cannot use kubectl against the cluster it just created.
  enable_cluster_creator_admin_permissions = true
  authentication_mode                      = "API_AND_CONFIG_MAP"

  cluster_addons = {
    coredns    = { most_recent = true }
    kube-proxy = { most_recent = true }
    vpc-cni = {
      most_recent    = true
      before_compute = true
    }
    # cloudnative-pg claims PersistentVolumes. Without a CSI driver those PVCs
    # stay Pending forever and postgres never starts.
    aws-ebs-csi-driver = {
      most_recent              = true
      service_account_role_arn = module.ebs_csi_irsa.iam_role_arn
    }
  }

  eks_managed_node_groups = {
    default = {
      instance_types = var.node_instance_types
      capacity_type  = var.node_capacity_type

      min_size     = var.node_min_size
      max_size     = var.node_max_size
      desired_size = var.node_desired_size

      disk_size = var.node_disk_size
    }
  }
}

module "ebs_csi_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.47"

  role_name             = "${local.name}-ebs-csi"
  attach_ebs_csi_policy = true

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:ebs-csi-controller-sa"]
    }
  }
}

# NOTE: no Kubernetes resources are declared here on purpose. A `kubernetes` or
# `helm` provider configured from module.eks outputs is evaluated at PLAN time,
# before the cluster exists -- it usually survives the first apply but breaks on
# destroy and re-plan with "Provider configuration not present". Since the whole
# cost strategy here is destroy-nightly-rebuild-tomorrow, that failure would hit
# constantly. In-cluster objects belong to ArgoCD (see deploy/) or to the
# separate platform module in Phase 2.
