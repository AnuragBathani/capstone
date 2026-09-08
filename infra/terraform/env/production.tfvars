# Sizing for a PERSONAL LEARNING cluster: no real users, no uptime obligation.
# Every setting here trades resilience for cost. See the "production" notes on
# each line for what to change if that ever stops being true.

environment     = "production"
region          = "us-east-1"
cluster_name    = "capstone"
cluster_version = "1.31"

# 2 AZs is the EKS minimum. A third only buys resilience we do not need.
az_count = 2

# t3.medium = 2 vCPU / 4GB. Two of them hold traefik + postgres + four services
# with headroom. t3.small (2GB) is genuinely too tight once postgres is running.
node_instance_types = ["t3.medium"]
node_desired_size   = 2
node_min_size       = 2
node_max_size       = 3
node_disk_size      = 20

# ~65% off the node bill. AWS can reclaim an instance with two minutes notice and
# the node group replaces it -- pods reschedule. Fine here; use ON_DEMAND for
# anything with real users.
node_capacity_type = "SPOT"

# Nodes sit in PRIVATE subnets behind one NAT gateway. NAT bills hourly
# (~$0.045/hr), so with destroy-nightly this is a few cents a day rather than the
# $33/month a permanently-running gateway costs.
#
# Do not set nodes_in_public_subnets = true to save the NAT without also adding a
# network_interfaces block to the node group -- see variables.tf.
enable_nat_gateway      = true
single_nat_gateway      = true
nodes_in_public_subnets = false

# Control plane logs are billed on ingest and storage. Add "audit" when you want
# to actually look at API activity.
cluster_log_types = []

# Open so kubectl works from anywhere. Narrow to "<your-ip>/32" to close the two
# CRITICAL Trivy findings on this config.
cluster_endpoint_public_access_cidrs = ["0.0.0.0/0"]
