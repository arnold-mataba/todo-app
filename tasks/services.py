import logging

from django.core.cache import cache

from .models import Task

logger = logging.getLogger(__name__)

TASKS_CACHE_KEY = "tasks:all"
TASKS_CACHE_TTL_SECONDS = 30


def get_all_tasks():
    tasks = cache.get(TASKS_CACHE_KEY)
    if tasks is None:
        logger.info("cache miss: %s", TASKS_CACHE_KEY)
        tasks = list(Task.objects.all())
        cache.set(TASKS_CACHE_KEY, tasks, TASKS_CACHE_TTL_SECONDS)
    else:
        logger.info("cache hit: %s", TASKS_CACHE_KEY)
    return tasks


def invalidate_tasks_cache():
    cache.delete(TASKS_CACHE_KEY)
