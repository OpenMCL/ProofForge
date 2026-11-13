from django.contrib import admin
from courses.models import Course, Enrollment, Assignment, Problem

admin.site.register(Course)
admin.site.register(Enrollment)
admin.site.register(Assignment)
admin.site.register(Problem)
