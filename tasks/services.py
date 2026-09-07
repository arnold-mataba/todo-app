"""
Cache-aside on top of RDS Proxy, shared by the DRF API and the template views so both paths
demonstrate the same read/write split: reads try Redis first (django-redis, CACHES in
settings.py), writes go straight to Postgres through RDS Proxy and evict the cache.
"""

from django.core.cache import cache

from .models import Task

TASKS_CACHE_KEY = "tasks:all"
TASKS_CACHE_TTL_SECONDS = 30


def get_all_tasks():
    tasks = cache.get(TASKS_CACHE_KEY)
    if tasks is None:
        tasks = list(Task.objects.all())
        cache.set(TASKS_CACHE_KEY, tasks, TASKS_CACHE_TTL_SECONDS)
    return tasks


def invalidate_tasks_cache():
    cache.delete(TASKS_CACHE_KEY)
