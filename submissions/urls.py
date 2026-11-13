from django.urls import path
from submissions import views

urlpatterns = [
    path("problems/<int:problem_id>/edit/", views.editor, name="editor"),
    path("problems/<int:problem_id>/autosave/", views.autosave, name="autosave"),
    path("problems/<int:problem_id>/submissions/", views.submission_list, name="submission_list"),
    path("submissions/<int:submission_id>/grade/", views.grade_submission, name="grade_submission"),
    path("problems/<int:problem_id>/feedback/", views.feedback, name="feedback"),
]
