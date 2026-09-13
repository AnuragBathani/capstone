terraform {
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.33"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 3.0"
    }
  }

  # Partial backend config: a backend block cannot interpolate variables, and an
  # S3 bucket name has to be globally unique. Supply the rest at init time:
  #   terraform init -backend-config=backend.hcl
  backend "s3" {}
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "capstone"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# Both Kubernetes-facing providers authenticate by shelling out to
# `aws eks get-token` rather than storing a token. EKS tokens expire after 15
# minutes, so a stored one would be stale by the next apply and would sit in
# state as a credential besides.
provider "kubernetes" {
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)

  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_name, "--region", var.region]
  }
}

# NOTE: helm provider v3 turned the `kubernetes` block into an attribute, so this
# is `kubernetes = {}` and not `kubernetes {}` as it would be on v2.
provider "helm" {
  kubernetes = {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)

    exec = {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_name, "--region", var.region]
    }
  }
}
