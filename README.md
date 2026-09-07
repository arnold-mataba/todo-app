# todo-app

Django + Django REST Framework To-Do app: reads go through Redis (django-redis, cache-aside,
30s TTL — see `tasks/services.py`), writes go to PostgreSQL through RDS Proxy (Django ORM,
`DB_PROXY_ENDPOINT`). The browsable UI at `/` is server-rendered Django templates
(`tasks/templates/tasks/list.html`) with plain HTML forms for create/toggle/delete; the same
data is also exposed as a DRF API under `/api/tasks/`.

Deploys as a container to ECS Fargate via `todo-infra`'s pipeline: this repo's workflow builds
the image, pushes it to ECR (which fires the EventBridge rule that starts CodePipeline), and
uploads the rendered `taskdef.json` + `appspec.yaml` to S3 for CodeDeploy's blue/green shift.

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

## Container startup runs migrations

`entrypoint.sh` runs `manage.py migrate --noinput` before starting gunicorn — there's no
separate migration step in the deploy pipeline. This is a documented lab-scope simplification:
fine because blue/green replaces one task set at a time, but a genuinely concurrent first-migrate
from multiple tasks starting at once (e.g. autoscaling right after a deploy) isn't fully guarded
against. A production setup would run migrations as a one-off CodeDeploy lifecycle hook instead.

## Required GitHub repo configuration

Values come from `todo-infra`'s root stack output (`aws cloudformation describe-stacks
--stack-name todo-dev-root --query "Stacks[0].Outputs"`) — see `todo-infra/README.md`.

**Secrets** (ARNs / internal hostnames — masked, per best practice):
`APP_BUILD_ROLE_ARN`, `ECR_REPOSITORY_URI`, `ARTIFACT_BUCKET_NAME`, `TASK_EXECUTION_ROLE_ARN`,
`TASK_ROLE_ARN`, `DB_SECRET_ARN`, `DB_PROXY_ENDPOINT`, `DJANGO_SECRET_KEY_ARN`, `REDIS_HOST`,
`LOG_GROUP_NAME`

**Variables** (non-identifying config): `AWS_REGION`, `DB_NAME`, `REDIS_PORT`, `TASK_FAMILY`
(e.g. `todo-dev-todo-app`, must match the `ecs` child stack's task definition family)

Note `DJANGO_SECRET_KEY` itself is never a GitHub secret — it's generated and stored in Secrets
Manager by the `ecs` child stack (`ecs.yaml`'s `DjangoSecretKeySecret`), and injected into the
container directly by ECS. `DJANGO_SECRET_KEY_ARN` here is just the pointer to that secret, used
to fill in `taskdef.json`'s `secrets` entry.

## Why the image push happens last in the workflow

The workflow builds the image, computes its URI, renders `taskdef.json`/`appspec.yaml`, zips
and uploads them to the fixed S3 key CodePipeline's source action watches — and only then pushes
the image to ECR. The push is what fires EventBridge → CodePipeline, so the S3 artifact has to
already reflect this build before that happens; pushing first would risk the pipeline picking up
last build's `taskdef.json`.
