variable "region" {
  description = "AWS region for the state bucket and lock table."
  type        = string
  default     = "us-east-1"
}

variable "state_bucket_name" {
  description = <<-DESC
    Globally unique S3 bucket name for Terraform state. S3 bucket names share a
    single global namespace, so this must be unique across all AWS accounts --
    suffix it with your account id or handle.
  DESC
  type        = string
}

variable "lock_table_name" {
  description = "DynamoDB table used for state locking."
  type        = string
  default     = "capstone-tfstate-lock"
}
