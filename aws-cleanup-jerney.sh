#!/usr/bin/env bash
# Removes orphans left by the deleted "jerney-eks" cluster, plus a dead Lambda role.
# None of these cost money -- this is tidiness, so that anything left in the account
# afterwards is unambiguously created by THIS project's Terraform.
#
# Does NOT touch the default VPC (vpc-09f4832b0b9705a7d): several AWS services
# expect one to exist, and recreating it later is awkward.
set -uo pipefail

R=us-east-1
VPC=vpc-0a2ea173754a2f7d8
ACCT=961353952618

step() { printf '\n\033[1m→ %s\033[0m\n' "$1"; }
try()  { echo "  \$ $*"; "$@" 2>&1 | sed 's/^/    /'; }

# ── 1. Security groups ──────────────────────────────────────────────────────
# EKS security groups reference each other, and a group cannot be deleted while
# another group's rule points at it. Revoking the rules first breaks that cycle.
step "Security groups: revoke cross-references, then delete"
for sg in sg-0b4fec7a3417ae7d2 sg-003369ef6e3967f05; do
  ing=$(aws ec2 describe-security-groups --region $R --group-ids $sg \
        --query 'SecurityGroups[0].IpPermissions' --output json 2>/dev/null)
  egr=$(aws ec2 describe-security-groups --region $R --group-ids $sg \
        --query 'SecurityGroups[0].IpPermissionsEgress' --output json 2>/dev/null)
  [ "$ing" != "[]" ] && [ -n "$ing" ] && \
    aws ec2 revoke-security-group-ingress --region $R --group-id $sg --ip-permissions "$ing" >/dev/null 2>&1
  [ "$egr" != "[]" ] && [ -n "$egr" ] && \
    aws ec2 revoke-security-group-egress  --region $R --group-id $sg --ip-permissions "$egr" >/dev/null 2>&1
done
for sg in sg-0b4fec7a3417ae7d2 sg-003369ef6e3967f05; do
  try aws ec2 delete-security-group --region $R --group-id $sg
done

# ── 2. Subnets ──────────────────────────────────────────────────────────────
step "Subnets (6)"
for s in subnet-0235bdd058d0b9c8a subnet-0e47396b651afd892 subnet-0ba53e269d724fc69 \
         subnet-0b00bdc53d3aa5310 subnet-0feb4af28f0cf530f subnet-07e742e00c3764783; do
  try aws ec2 delete-subnet --region $R --subnet-id $s
done

# ── 3. Route tables ─────────────────────────────────────────────────────────
# The MAIN route table is intentionally absent: it cannot be deleted separately
# and goes away with the VPC.
step "Route tables (non-main)"
for rt in rtb-0261fe10390d7bb55 rtb-07df8f9d5d645b416; do
  try aws ec2 delete-route-table --region $R --route-table-id $rt
done

# ── 4. Internet gateway ─────────────────────────────────────────────────────
step "Internet gateway: detach then delete"
try aws ec2 detach-internet-gateway --region $R --internet-gateway-id igw-0cf412ac984044133 --vpc-id $VPC
try aws ec2 delete-internet-gateway --region $R --internet-gateway-id igw-0cf412ac984044133

# ── 5. VPC ──────────────────────────────────────────────────────────────────
step "VPC"
try aws ec2 delete-vpc --region $R --vpc-id $VPC

# ── 6. IAM roles ────────────────────────────────────────────────────────────
# Every managed policy must be detached before a role can be deleted.
step "IAM roles: detach policies, then delete"
for role in jerney-eks-cluster-20260523101033373700000001 \
            jerney-eks-eks-auto-20260523101033417700000003 \
            demofunction-role-4e365c6p; do
  echo "  role: $role"
  for arn in $(aws iam list-attached-role-policies --role-name "$role" \
               --query 'AttachedPolicies[].PolicyArn' --output text 2>/dev/null); do
    aws iam detach-role-policy --role-name "$role" --policy-arn "$arn" 2>&1 | sed 's/^/    /'
  done
  for pol in $(aws iam list-role-policies --role-name "$role" \
               --query 'PolicyNames' --output text 2>/dev/null); do
    aws iam delete-role-policy --role-name "$role" --policy-name "$pol" 2>&1 | sed 's/^/    /'
  done
  try aws iam delete-role --role-name "$role"
done

# ── 7. Customer-managed policies ────────────────────────────────────────────
# Only deletable once detached from every entity, which step 6 just did.
step "Customer-managed IAM policies"
for arn in arn:aws:iam::$ACCT:policy/jerney-eks-cluster-ClusterEncryption20260523101054561200000011 \
           arn:aws:iam::$ACCT:policy/jerney-eks-cluster-20260523101033410300000002 \
           arn:aws:iam::$ACCT:policy/service-role/AWSLambdaBasicExecutionRole-e54566fd-4e15-4c70-ad01-f895e3860533; do
  try aws iam delete-policy --policy-arn "$arn"
done

# ── 8. CloudWatch log group ─────────────────────────────────────────────────
step "CloudWatch log group (0 bytes)"
try aws logs delete-log-group --region $R --log-group-name /aws/eks/jerney-eks/cluster

printf '\n\033[1mDone.\033[0m Verify with the check below.\n'
