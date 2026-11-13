from functools import wraps
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404
from courses.models import Course, Enrollment

def get_role(user, course):
    if not user.is_authenticated:
        return None
    e = Enrollment.objects.filter(user=user, course=course).first()
    return e.role if e else None

def require_course_role(*roles):
    allowed = set(roles)
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            course = get_object_or_404(Course, pk=kwargs["course_id"])
            role = get_role(request.user, course)
            if role not in allowed:
                return HttpResponseForbidden("forbidden")
            request.course = course
            request.course_role = role
            return view(request, *args, **kwargs)
        return wrapper
    return decorator
