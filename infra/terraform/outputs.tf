output "cluster_name" {
  description = "EKS cluster name."
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "Kubernetes API endpoint."
  value       = module.eks.cluster_endpoint
}

output "cluster_version" {
  description = "Kubernetes version running on the control plane."
  value       = module.eks.cluster_version
}

output "oidc_provider_arn" {
  description = "IRSA OIDC provider ARN. Phase 2 (ArgoCD) needs this."
  value       = module.eks.oidc_provider_arn
}

output "vpc_id" {
  description = "VPC the cluster runs in."
  value       = module.vpc.vpc_id
}

output "private_subnet_ids" {
  description = "Private subnets hosting the nodes."
  value       = module.vpc.private_subnets
}

# Deliberately not an output: kubeconfig. Emitting it would write cluster
# credentials into state and into CI logs. Fetch it on demand instead:
#   aws eks update-kubeconfig --name <cluster_name> --region <region>
output "kubeconfig_command" {
  description = "Run this to point kubectl at the cluster."
  value       = "aws eks update-kubeconfig --name ${module.eks.cluster_name} --region ${var.region}"
}

output "argocd_port_forward" {
  description = "Open the ArgoCD UI on http://localhost:8080."
  value       = "kubectl -n argocd port-forward svc/argocd-server 8080:80"
}

output "argocd_initial_password" {
  description = "Retrieve the generated admin password (not stored in state)."
  value       = "kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d"
}

output "bootstrap_gitops" {
  description = "Hand the cluster over to ArgoCD -- one manifest, everything else follows."
  value       = "kubectl apply -f deploy/argocd/root.yaml"
}
