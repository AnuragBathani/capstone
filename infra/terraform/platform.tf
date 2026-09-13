# ---------------------------------------------------------------------------
# Phase 2: the two things that must exist before GitOps can take over.
#
# Terraform installs ONLY ArgoCD and the load balancer controller. Everything
# else -- HAProxy, CloudNativePG, the five services -- is installed BY ArgoCD
# from deploy/argocd/. Splitting it that way keeps one tool in charge of the
# cluster's contents and avoids Terraform and ArgoCD fighting over the same
# resources.
# ---------------------------------------------------------------------------

# The controller needs AWS API access to create load balancers and target groups.
# IRSA scopes those permissions to one service account rather than the node role,
# so a compromised pod elsewhere on the node does not inherit them.
module "lb_controller_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.47"

  role_name                              = "${local.name}-aws-lb-controller"
  attach_load_balancer_controller_policy = true

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:aws-load-balancer-controller"]
    }
  }
}

# Without this, a Service of type LoadBalancer still works -- EKS's cloud
# controller manager falls back to a Classic ELB. The controller upgrades that to
# an NLB with pod-IP target groups, which health-checks individual pods instead of
# node ports.
resource "helm_release" "aws_lb_controller" {
  name       = "aws-load-balancer-controller"
  repository = "https://aws.github.io/eks-charts"
  chart      = "aws-load-balancer-controller"
  version    = var.lb_controller_chart_version
  namespace  = "kube-system"

  # helm provider v3 takes `set` as a list attribute, not repeated blocks.
  set = [
    {
      name  = "clusterName"
      value = module.eks.cluster_name
    },
    {
      name  = "serviceAccount.create"
      value = "true"
    },
    {
      name  = "serviceAccount.name"
      value = "aws-load-balancer-controller"
    },
    {
      # Dots inside the annotation KEY must be escaped, or helm reads them as
      # nesting and the service account never gets its role.
      name  = "serviceAccount.annotations.eks\\.amazonaws\\.com/role-arn"
      value = module.lb_controller_irsa.iam_role_arn
    },
    {
      name  = "region"
      value = var.region
    },
    {
      name  = "vpcId"
      value = module.vpc.vpc_id
    },
  ]

  # Nodes must be schedulable before the controller pods can land.
  depends_on = [module.eks]
}

resource "helm_release" "argocd" {
  name             = "argocd"
  repository       = "https://argoproj.github.io/argo-helm"
  chart            = "argo-cd"
  version          = var.argocd_chart_version
  namespace        = "argocd"
  create_namespace = true

  values = [yamlencode({
    # ClusterIP, reached by port-forward. A LoadBalancer here would provision a
    # second ELB (~$18/month) to expose a dashboard only you use.
    server = {
      service = {
        type = "ClusterIP"
      }
      # --insecure: TLS is terminated at the load balancer (or nowhere), and the
      #   server rejects plain HTTP unless told not to.
      # --rootpath: ArgoCD is served under /argocd on the shared HAProxy load
      #   balancer rather than getting an ELB of its own. It must generate its own
      #   links under that prefix or the UI loads blank.
      extraArgs = ["--insecure", "--rootpath=/argocd"]
    }

    # Single-replica everything: this is a two node learning cluster.
    controller     = { replicas = 1 }
    repoServer     = { replicas = 1 }
    applicationSet = { replicaCount = 1 }

    # The kubectl-based Redis HA setup is unnecessary here.
    redis-ha = { enabled = false }
  })]

  depends_on = [module.eks]
}
