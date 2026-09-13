output "backend_config" {
  description = "Paste these into infra/terraform/backend.hcl."
  value       = <<-CONFIG
    bucket         = "${aws_s3_bucket.tfstate.id}"
    key            = "eks/production/terraform.tfstate"
    region         = "${var.region}"
    dynamodb_table = "${aws_dynamodb_table.tflock.name}"
    encrypt        = true
  CONFIG
}
