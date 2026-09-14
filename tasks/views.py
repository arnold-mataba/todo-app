from django.db import connection
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from rest_framework import viewsets
from rest_framework.response import Response

from .models import Task
from .serializers import TaskSerializer
from .services import get_all_tasks, invalidate_tasks_cache


class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    queryset = Task.objects.all()

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(get_all_tasks(), many=True)
        return Response(serializer.data)

    def perform_create(self, serializer):
        serializer.save()
        invalidate_tasks_cache()

    def perform_update(self, serializer):
        serializer.save()
        invalidate_tasks_cache()

    def perform_destroy(self, instance):
        instance.delete()
        invalidate_tasks_cache()


def task_list(request):
    return render(request, "tasks/list.html", {"tasks": get_all_tasks()})


@require_POST
def task_create(request):
    title = request.POST.get("title", "").strip()
    priority = request.POST.get("priority", "").strip()
    if title:
        Task.objects.create(title=title, priority=priority)
        invalidate_tasks_cache()
    return redirect("task_list")


@require_POST
def task_toggle(request, pk):
    task = get_object_or_404(Task, pk=pk)
    task.completed = not task.completed
    task.save(update_fields=["completed", "updated_at"])
    invalidate_tasks_cache()
    return redirect("task_list")


@require_POST
def task_delete(request, pk):
    Task.objects.filter(pk=pk).delete()
    invalidate_tasks_cache()
    return redirect("task_list")


def health(request):
    try:
        connection.ensure_connection()
        cache.set("health:check", "ok", 5)
        if cache.get("health:check") != "ok":
            raise RuntimeError("cache read-after-write failed")
    except Exception as exc:
        return JsonResponse({"status": "DOWN", "error": str(exc)}, status=503)
    return JsonResponse({"status": "UP"})
