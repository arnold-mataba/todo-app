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
