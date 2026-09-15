from django.db import models


class Task(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    priority = models.CharField(max_length=20, blank=True, default="")
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


# class TaskHistory(models.Model):
#     task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="history")
#     title = models.CharField(max_length=255)
#     description = models.TextField(blank=True, default="")
#     priority = models.CharField(max_length=20, blank=True, default="")
#     completed = models.BooleanField(default=False)
#     updated_at = models.DateTimeField(auto_now_add=True)

#     class Meta:
#         ordering = ["-updated_at"]

#     def __str__(self):
#         return f"History for {self.task.title} at {self.updated_at}"
