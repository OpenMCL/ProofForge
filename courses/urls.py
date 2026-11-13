from django.urls import path
from courses import views

urlpatterns = [
    path("new/", views.course_create, name="course_create"),
    path("<int:course_id>/", views.course_detail, name="course_detail"),
    path("<int:course_id>/roster/", views.roster_import, name="roster_import"),
    path("<int:course_id>/roster/add/", views.roster_add, name="roster_add"),
    path("<int:course_id>/add-ta/", views.add_ta, name="add_ta"),
    path("<int:course_id>/assignments/new/", views.assignment_create, name="assignment_create"),
    path("<int:course_id>/assignments/<int:assignment_id>/problems/new/",
         views.problem_create, name="problem_create"),
]
