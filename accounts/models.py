from django.contrib.auth.models import User
from django.db import models

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    oauth_sub = models.CharField(max_length=255, blank=True)
    student_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    can_create_course = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["oauth_sub"],
                condition=~models.Q(oauth_sub=""),
                name="unique_nonempty_oauth_sub",
            )
        ]

    def __str__(self):
        return f"{self.user.username} ({self.student_id})"
