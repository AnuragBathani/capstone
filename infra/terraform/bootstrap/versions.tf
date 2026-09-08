# Bootstrap keeps LOCAL state on purpose: it creates the very bucket and lock
# table the main configuration uses as its backend, so it cannot store state
# remotely without a chicken-and-egg problem. Run this once, then never again.
# terraform.tfstate here is gitignored -- it describes only these two resources.

terraform {
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "capstone"
      ManagedBy = "terraform"
      Component = "tfstate-backend"
    }
  }
}
