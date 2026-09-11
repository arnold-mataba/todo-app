from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from .models import Task
from .services import TASKS_CACHE_KEY, get_all_tasks, invalidate_tasks_cache


class CacheClearingTestCase(TestCase):
    def setUp(self):
        cache.clear()


class TaskApiTests(CacheClearingTestCase):
    def test_create_then_list_via_api(self):
        response = self.client.post("/api/tasks/", {"title": "Buy milk"}, content_type="application/json")
        self.assertEqual(response.status_code, 201)

        response = self.client.get("/api/tasks/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["title"], "Buy milk")

    def test_delete_via_api(self):
        task = Task.objects.create(title="Temp")
        response = self.client.delete(f"/api/tasks/{task.id}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Task.objects.filter(id=task.id).exists())


class TaskTemplateViewTests(CacheClearingTestCase):
    def test_list_page_renders(self):
        Task.objects.create(title="Walk the dog")
        response = self.client.get(reverse("task_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Walk the dog")

    def test_create_via_form(self):
        response = self.client.post(reverse("task_create"), {"title": "Read a book"})
        self.assertRedirects(response, reverse("task_list"))
        self.assertTrue(Task.objects.filter(title="Read a book").exists())

    def test_toggle_and_delete_via_form(self):
        task = Task.objects.create(title="Ship it")
        self.client.post(reverse("task_toggle", args=[task.id]))
        task.refresh_from_db()
        self.assertTrue(task.completed)

        self.client.post(reverse("task_delete", args=[task.id]))
        self.assertFalse(Task.objects.filter(id=task.id).exists())


class CacheAsideTests(CacheClearingTestCase):
    def test_write_invalidates_cache(self):
        Task.objects.create(title="First")
        self.assertEqual(len(get_all_tasks()), 1)
        self.assertIsNotNone(cache.get(TASKS_CACHE_KEY))

        Task.objects.create(title="Second")
        invalidate_tasks_cache()
        self.assertIsNone(cache.get(TASKS_CACHE_KEY))
        self.assertEqual(len(get_all_tasks()), 2)


class HealthCheckTests(TestCase):
    def test_health_ok(self):
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "UP")
