# Infrastructure — AWS EKS

Terraform for the EKS cluster that replaces the Civo cluster provisioned
imperatively by `deploy/kubernetes/Taskfile.yaml` (`civo:01` … `civo:06`).

| Civo task | Replaced by |
|---|---|
| `civo:01-create-network` | `module.vpc` |
| `civo:02-create-firewall` (+ `jq` loop deleting default rules) | EKS-managed security groups |
| `civo:03-create-cluster` | `module.eks` |
| `civo:05-get-kubeconfig` | `aws eks update-kubeconfig` (see outputs) |
| `civo:06-clean-up` (+ hardcoded `sleep 20`) | `terraform destroy` |

The `sleep 20` and the rule-deletion loop existed because ordering had to be
hand-managed. Terraform's dependency graph removes the need for both.

## Layout

```
infra/terraform/
├── bootstrap/          # S3 state bucket + DynamoDB lock table (run once)
├── versions.tf         # providers, partial S3 backend
├── variables.tf
├── vpc.tf              # VPC, 3 AZs, public + private subnets, NAT
├── eks.tf              # cluster, managed node group, addons, gp3 storage class
├── outputs.tf
└── env/production.tfvars
```

## First run

The bootstrap module creates the bucket the main configuration stores state in,
so it must run first and keeps its own state **locally** — that is why
`terraform.tfstate` is gitignored rather than committed.

```bash
cd infra/terraform/bootstrap
terraform init
terraform apply -var="state_bucket_name=capstone-tfstate-<your-suffix>"
```

S3 bucket names are globally unique across all AWS accounts, so pick a suffix.
The output prints a ready-made backend config.

```bash
cd ..
cp backend.hcl.example backend.hcl     # fill in the bucket name
terraform init -backend-config=backend.hcl
terraform plan  -var-file=env/production.tfvars
terraform apply -var-file=env/production.tfvars
```

Then point kubectl at it:

```bash
aws eks update-kubeconfig --name capstone-production --region us-east-1
```

## Sizing: this is a learning cluster

Every default here trades resilience for cost. Approximate monthly spend if left
running continuously:

| Item | Learning config | Production shape | Saving |
|---|---|---|---|
| EKS control plane | $73 | $73 | — (fixed, unavoidable) |
| 2x t3.medium | **$18** (SPOT) | $60 (on-demand) | $42 |
| NAT gateway | **$0** (nodes public) | $33 | $33 |
| EBS 2x20GB gp3 | $3 | $8 (2x50GB) | $5 |
| CloudWatch logs | **$0** (disabled) | ~$5 | $5 |
| Load balancer | $18 | $18 | — |
| **Total** | **~$112/mo** | ~$197/mo | **~$85** |

The control plane is $0.10/hour and dominates everything else, so the real lever
is not sizing -- it is **not leaving it running**:

```bash
terraform destroy -var-file=env/production.tfvars   # when you stop for the day
terraform apply   -var-file=env/production.tfvars   # ~15 min to rebuild
```

A few hours of learning costs well under a dollar. A month of forgetting costs $112.

### What was traded away

- **SPOT nodes** — AWS can reclaim an instance on two minutes notice. The node
  group replaces it and pods reschedule, but expect occasional churn.
- **No NAT gateway** — nodes sit in public subnets with public IPs. Their security
  group still permits no inbound internet traffic; only the egress path changed.
- **2 AZs, max 3 nodes** — no capacity for a real outage.
- **No control plane logging** — nothing to audit after the fact.

Flip all four in `env/production.tfvars` if this ever faces real users.

## What gets created

- VPC `10.0.0.0/16` across 3 AZs — `/20` private subnets, `/24` public
- One NAT gateway (see `single_nat_gateway`)
- EKS 1.31, public + private API endpoint
- One managed node group: 2× `t3.medium`, 50GB disk, scales 2–4
- Addons: CoreDNS, kube-proxy, VPC CNI, EBS CSI driver
- `gp3` StorageClass marked default

### Two things that are load-bearing

**Subnet tags.** `kubernetes.io/role/elb` and `kubernetes.io/role/internal-elb`
are how the AWS load balancer controller finds subnets. Without them a
`Service` of type LoadBalancer provisions nothing, with no clear error.

**The EBS CSI driver.** `cloudnative-pg` claims PersistentVolumes. With no CSI
driver those PVCs stay `Pending` forever and postgres never starts.

## Known scanner findings

`iac-scan.yaml` scans this directory with Trivy under the `terraform_scan`
policy check. Four findings are expected and currently accepted:

| ID | Finding | Why it stands |
|---|---|---|
| `AWS-0040` | Public cluster access enabled | kubectl and CI reach the API without a bastion |
| `AWS-0041` | API open to `0.0.0.0/0` | Mirrors the Civo firewall rule this replaces. Narrow via `cluster_endpoint_public_access_cidrs` |
| `AWS-0104` | Unrestricted egress on node SG | Comes from the upstream EKS module's node group |
| `AWS-0132` | State bucket uses SSE-S3, not a CMK | AES256 is sufficient here; KMS adds key management and cost |

The first two are the ones worth revisiting: setting
`cluster_endpoint_public_access_cidrs` to your egress IP closes both.

## State contains secrets

`.tfstate` holds cluster endpoints and CA data. It is gitignored, encrypted at
rest in S3, versioned, and the bucket denies non-TLS requests. Never commit it —
that is one of the things Gitleaks and Trivy are watching for.
