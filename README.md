# todo-app

Django + Django REST Framework To-Do app: reads go through Redis (django-redis, cache-aside,
30s TTL — see `tasks/services.py`), writes go to PostgreSQL through RDS Proxy (Django ORM,
`DB_PROXY_ENDPOINT`). The browsable UI at `/` is server-rendered Django templates
(`tasks/templates/tasks/list.html`) with plain HTML forms for create/toggle/delete; the same
data is also exposed as a DRF API under `/api/tasks/`.

Deploys as a container to ECS Fargate via `todo-infra`'s pipeline: this repo's workflow builds
the image, registers the real ECS task definition directly (via `jq`, not a checked-in template
file), uploads it with `appspec.yaml` to S3 for CodeDeploy's blue/green shift, then pushes the
image to ECR — which fires the EventBridge rule that starts CodePipeline.

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

`entrypoint.sh` no longer runs `manage.py migrate` — it only execs gunicorn. Migrations run in
`todo-infra`'s pipeline instead, in a dedicated **Migrate** stage between Source and Deploy: a
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

## No checked-in task-definition template

There's no `taskdef.json` in this repo. `build-and-deploy.yml`'s "Generate real taskdef.json"
step builds the complete, real ECS task definition with `jq` on every run — the image URI is
freshly known, and everything else (execution/task role ARNs, the log group name, the SSM
parameter paths for DB/Redis config) is derived from the `ENVIRONMENT_NAME` naming convention
shared with `todo-infra`'s templates, not copied in as GitHub secrets. Only the two *real*
secrets (DB credentials, Django's secret key) come from GitHub secrets, since their ARNs include
an unpredictable Secrets-Manager-generated suffix. This avoids keeping a template file with
placeholder tokens that a substitution pass could silently get out of sync with.

## Required GitHub repo configuration

Values come from two stacks in two different repos — see `todo-infra/README.md` and
`todo-bootstrap/README.md`:

```bash
aws cloudformation describe-stacks --stack-name todo-dev-root --query "Stacks[0].Outputs"
aws cloudformation describe-stacks --stack-name todo-dev-ecr --query "Stacks[0].Outputs"  # ECR_REPOSITORY_URI
```

**Secrets** (real ARNs — masked, per best practice; note how short this list is now that
non-secret config is resolved by naming convention / SSM Parameter Store instead of being
copied through GitHub):
`APP_BUILD_ROLE_ARN`, `ECR_REPOSITORY_URI` (from `todo-bootstrap`'s stack, not `todo-infra`'s),
`ARTIFACT_BUCKET_NAME`, `DB_SECRET_ARN`, `DJANGO_SECRET_KEY_ARN`

**Variables**: `AWS_REGION`, `ENVIRONMENT_NAME` (must exactly match the value used to deploy
`todo-infra` — everything computed by naming convention depends on this matching)

Note `DJANGO_SECRET_KEY` itself is never a GitHub secret — it's generated and stored in Secrets
Manager by the `ecs` child stack (`ecs.yaml`'s `DjangoSecretKeySecret`), and injected into the
container directly by ECS. `DJANGO_SECRET_KEY_ARN` here is just the pointer to that secret.

## Why the image push happens last in the workflow

The workflow builds the image, computes its URI, generates the real `taskdef.json` + copies
`appspec.yaml`, zips and uploads them to the fixed S3 key CodePipeline's source action watches —
and only then pushes the image to ECR. The push is what fires EventBridge → CodePipeline, so the
S3 artifact has to already reflect this build before that happens; pushing first would risk the
pipeline picking up the previous build's task definition.
