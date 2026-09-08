terraform {
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
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
