from django.contrib.auth.models import User
from django.db import models


class Course(models.Model):
    title = models.CharField(max_length=200)
    term = models.CharField(max_length=20, db_index=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="owned_courses")

    def __str__(self):
        return f"{self.title} ({self.term})"

class Enrollment(models.Model):
    ROLE_CHOICES = [("professor", "professor"), ("ta", "ta"), ("student", "student")]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="enrollments")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)

    class Meta:
        unique_together = [("user", "course")]


class Assignment(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="assignments")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    deadline = models.DateTimeField()

    def __str__(self):
        return f"{self.title} ({self.course.title})"


class Problem(models.Model):
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="problems")
    number = models.PositiveIntegerField()
    statement = models.TextField()

    class Meta:
        ordering = ["number", "id"]
        constraints = [
            models.UniqueConstraint(fields=["assignment", "number"],
                                    name="unique_problem_number_per_assignment"),
        ]

    def __str__(self):
        return f"{self.number} ({self.assignment.title})"
