# todo-app

Django + Django REST Framework To-Do app: reads go through Redis (django-redis, cache-aside,
30s TTL — see `tasks/services.py`), writes go to PostgreSQL through RDS Proxy (Django ORM,
`DB_PROXY_ENDPOINT`). The browsable UI at `/` is server-rendered Django templates
(`tasks/templates/tasks/list.html`) with plain HTML forms for create/toggle/delete; the same
data is also exposed as a DRF API under `/api/tasks/`.

Deploys as a container to ECS Fargate via `todo-infra`'s pipeline: this repo's workflow builds
the image, tags it `:latest` (mutable — every build overwrites it), zips the checked-in
`deploy/taskdef.json` + `deploy/appspec.yaml` to S3 for CodeDeploy's blue/green shift, then
pushes the image to ECR — which fires the EventBridge rule that starts CodePipeline.

## Local development

Requires local Postgres + Redis (or point at real dev endpoints) — without them the app falls
back to sqlite + in-memory cache, which is enough to run `manage.py runserver`:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Then open http://localhost:8000. To point at real Postgres/Redis instead of the sqlite/locmem
fallback:

```bash
docker run -d --name pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=tododb -p 5432:5432 postgres:16
docker run -d --name redis -p 6379:6379 redis:7

export DB_PROXY_ENDPOINT=localhost DB_PORT=5432 DB_NAME=tododb \
       DB_USERNAME=postgres DB_PASSWORD=postgres REDIS_HOST=localhost REDIS_PORT=6379
python manage.py migrate
python manage.py runserver
```

Run tests with `python manage.py test`.

## Migrations run once, before traffic shifts — not in the container

The container no longer runs `manage.py migrate` on startup — the Dockerfile's `CMD` execs
gunicorn directly, no entrypoint script needed. Migrations run in `todo-infra`'s pipeline
instead, in a dedicated **Migrate** stage between Source and Deploy: a
CodeBuild action registers the incoming `taskdef.json` and runs it once as a standalone
`ecs run-task` with the container command overridden to `manage.py migrate --noinput`. If that
task doesn't exit 0, the CodeBuild action fails and CodeDeploy's blue/green shift never runs.

This replaced running `migrate` from the container's own entrypoint, which raced across however
many tasks a blue/green deploy (or autoscaling right after one) starts concurrently — every task
would call `migrate` on startup, with no guarantee only one wins the race on the same schema
change. See `todo-infra/README.md` for the pipeline-side detail.

## Missing-migration check runs in CI, before the image is even built

`build-and-deploy.yml` runs `python manage.py makemigrations --check --dry-run --no-input` right
after installing dependencies. It exits non-zero if a model changed without a matching migration
file being committed, so a forgotten `makemigrations` fails the workflow immediately — before
`check`/`test` run, before the image builds, before anything touches AWS.

## `deploy/` — the actual task definition, appspec, and migrate buildspec, checked in and static

`deploy/taskdef.json`, `deploy/appspec.yaml`, and `deploy/migrate-buildspec.yml` are real,
complete, checked-in files — open any of them and see exactly what gets deployed. There is no
template, no placeholder, no rendering step of any kind; the workflow just zips these three
files as they are. `migrate-buildspec.yml` is what `todo-infra`'s `MigrateProject` CodeBuild
project actually runs (`Source.BuildSpec: migrate-buildspec.yml`, a path into this same
artifact, instead of the script being embedded as inline YAML text inside the CloudFormation
template) — the three CFN-specific values it needs (`CLUSTER_NAME`, `PRIVATE_ECS_SUBNET_IDS`,
`ECS_SECURITY_GROUP_ID`) arrive as plain CodeBuild environment variables, so this file itself
has zero CloudFormation syntax in it.

Every value in `taskdef.json` is a static literal:

- **Image**: `<account>.dkr.ecr.<region>.amazonaws.com/todo-app:latest` — fixed, because the tag
  never changes (see "Mutable `:latest` tag" below).
- **Execution/task role ARNs, log group name**: fixed, derived from the `todo-dev` naming
  convention shared with `todo-infra`'s templates — account ID and region are also fixed, since
  this project only ever targets one account/region.
- **DB/Redis config**: SSM parameter ARNs, deterministic by construction
  (`/todo-dev/db-proxy-endpoint` etc.).
- **Both secrets**: referenced by *partial* ARN (the deterministic name, without the random
  6-character suffix Secrets Manager appends) — `todo-dev-db-credentials` and
  `todo-dev-django-secret-key`. ECS resolves a partial ARN to the one matching secret at task
  launch, so the actual generated value can change (and does, every time RDS/the Django secret
  gets recreated) without `taskdef.json` ever needing to change. See `todo-infra/README.md` for
  why the DB secret has a deterministic name at all (it replaces RDS's own managed-password
  feature specifically to make this possible).

If you ever add a genuinely unpredictable value (something with no deterministic name), it has
to come back as a real templated field — but as long as everything is either a fixed literal or
referenced by a deterministic name, there's nothing to keep in sync and nothing to render.

## Mutable `:latest` tag — no per-build image URI to track anywhere

Every build overwrites the same ECR tag (`ecr.yaml` sets `ImageTagMutability: MUTABLE`), so
`taskdef.json`'s image field never has to change and the workflow never has to compute or look up
an image URI. Tradeoff: there's no per-commit image history in ECR to roll back to by
repointing a tag — a rollback means checking out an older commit and re-running the workflow
(the lifecycle policy still keeps the last 5 image digests, so a same-tag rollback push is
also possible directly from ECR if needed).

## Required GitHub repo configuration

```bash
aws cloudformation describe-stacks --stack-name todo-dev-ecr --query "Stacks[0].Outputs"  # ECR_REPOSITORY_URI
```

**Secrets**: `APP_BUILD_ROLE_ARN`, `ECR_REPOSITORY_URI` (from `todo-bootstrap`'s stack),
`ARTIFACT_BUCKET_NAME` — that's the whole list. No DB or Django secret ARNs are needed here at
all anymore, since `taskdef.json` references both by deterministic partial ARN instead of
copying the real generated value through GitHub.

**Variables**: `AWS_REGION`, `ENVIRONMENT_NAME` (must exactly match the value used to deploy
`todo-infra` — everything computed by naming convention depends on this matching)

## Why the image push happens last in the workflow

The workflow builds the image, zips the checked-in `deploy/taskdef.json` + `deploy/appspec.yaml`
+ `deploy/migrate-buildspec.yml` and uploads them to the fixed S3 key CodePipeline's source
action watches — and only then pushes
the image to ECR. The push is what fires EventBridge → CodePipeline, so the S3 artifact has to
already be in place before that happens.
