from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from tasks.views import TaskViewSet, health

router = DefaultRouter()
router.register("tasks", TaskViewSet, basename="task")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
    path("health/", health, name="health"),
    path("", include("tasks.urls")),
]
