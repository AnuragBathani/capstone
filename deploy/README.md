# Deployment

GitOps with **ArgoCD**. ArgoCD is the only thing that talks to the cluster; CI
never runs `kubectl`. The pipeline's job ends when it writes an image tag to git.

```
deploy/
├── argocd/
│   ├── root.yaml                       # app-of-apps -- the single manifest you apply
│   └── applications/
│       ├── platform-cloudnative-pg.yaml
│       ├── platform-haproxy.yaml
│       ├── services-production.yaml    # ApplicationSet -> 5 charts
│       └── services-staging.yaml
└── charts/
    ├── api-golang/      Deployment, Service, Ingress, Secret, migration hook
    ├── api-node/        Deployment, Service, Ingress, Secret
    ├── client-react/    Deployment, Service, Ingress, nginx ConfigMap
    ├── load-generator/  Deployment only -- it is a client, not a server
    └── postgres/        CloudNativePG Cluster + superuser Secret
```

## Bootstrapping

Once ArgoCD is running (Phase 2 installs it):

```bash
kubectl apply -f deploy/argocd/root.yaml
```

That one manifest is the whole bootstrap. `root` watches `deploy/argocd/applications/`,
so anything added there is picked up automatically.

## Ordering

Sync waves encode real dependencies, not preferences:

| Wave | What | Why |
|---:|---|---|
| -10 | CloudNativePG operator, HAProxy | CRDs and the ingress class must exist first |
| 0 | postgres Cluster | apps crash-loop until the database answers |
| 1 | api-golang, api-node, client-react | |
| 2 | load-generator | pointless before there is an API to call |

Within `api-golang`, two **PreSync** hooks run before any pod rolls: the migration
Secret (wave 1), then the migration Job (wave 2). ArgoCD blocks the sync until the
Job succeeds.

> Migration hooks were `kluctl.io/hook: pre-deploy`. ArgoCD ignores that annotation
> completely, so it had to be respelled as `argocd.argoproj.io/hook: PreSync`.
> The Job also carries `hook-delete-policy: BeforeHookCreation` — a Job's pod
> template is immutable, so without it every sync after the first fails.

## How CI updates a version

`update-gitops-manifests` finds the marker comment and rewrites the value before it:

```yaml
image:
  tag: 1.4.1 # production_services/go/api-golang
```

The marker format is unchanged from the kluctl layout, so the deploy workflow
needed no modification when the charts replaced it. ArgoCD notices the commit and
syncs within its polling interval.

## Ingress

**HAProxy**, not Traefik. Routing is standard `Ingress` resources; prefix stripping
is an annotation on the same object:

```yaml
haproxy.org/path-rewrite: '/api/golang/?(.*) /\1'
```

Traefik needed a separate `Middleware` CRD referenced by name — and those names had
drifted, which silently broke `/api/golang` and `/api/node`. Keeping the rewrite on
the route removes that failure mode.

Single quotes matter: Helm collapses `\\` to `\`, and a lone `\1` is an invalid
escape in a double-quoted YAML scalar.

## Staging

`services-staging.yaml` deploys into `demo-app-staging` / `postgres-staging` so both
environments can share one cluster. It roughly doubles the pod count, so delete it
if you only care about production.

## ⛔️ Secrets

Database passwords are plaintext in `values.yaml`, carried over from the course.
Real clusters want External Secrets, Sealed Secrets, or SOPS.
