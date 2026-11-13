from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Case, IntegerField, When
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.services import get_or_create_placeholder
from courses.forms import (
    AddTaForm, AssignmentForm, CourseForm, ProblemForm, RosterAddForm, RosterUploadForm,
    duplicate_number_message,
)
from courses.models import Assignment, Course, Enrollment, Problem
from courses.permissions import get_role, require_course_role
from courses.roster import import_roster, parse_roster_csv


def _invalid(request, template, context):
    """表單驗證失敗：重新顯示頁面並回傳 400，而不是讓例外變成 500。"""
    return render(request, template, context, status=400)


@login_required
def course_create(request):
    if not getattr(request.user, "profile", None) or not request.user.profile.can_create_course:
        return HttpResponseForbidden("forbidden")
    template = "courses/course_form.html"
    if request.method != "POST":
        return render(request, template, {"form": CourseForm()})

    form = CourseForm(request.POST)
    if not form.is_valid():
        return _invalid(request, template, {"form": form})
    # course 與 professor enrollment 必須同時成立，否則會出現沒有人能管理的課程
    with transaction.atomic():
        course = Course.objects.create(owner=request.user, **form.cleaned_data)
        Enrollment.objects.create(user=request.user, course=course, role="professor")
    return redirect(f"/courses/{course.id}/")


def _roster_context(course):
    """名單頁共用的 context：課程與目前成員（教授、助教、學生依序，再依學號排序）。

    必須在匯入之後才呼叫，名單才會包含剛匯入的學生。
    """
    role_order = Case(
        When(role="professor", then=0), When(role="ta", then=1), default=2,
        output_field=IntegerField(),
    )
    roster = list(
        course.enrollments.select_related("user__profile")
        .order_by(role_order, "user__profile__student_id", "user__username")
    )
    return {
        "course": course,
        "roster": roster,
        "has_students": any(e.role == "student" for e in roster),
        "add_form": RosterAddForm(),
    }


@login_required
@require_course_role("professor", "ta")
def roster_import(request, course_id):
    template = "courses/roster_import.html"
    if request.method != "POST":
        return render(request, template,
                      {**_roster_context(request.course), "form": RosterUploadForm()})

    form = RosterUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        return _invalid(request, template, {**_roster_context(request.course), "form": form})

    rows, errors = parse_roster_csv(form.cleaned_data["file"])
    added = import_roster(request.course, rows) if rows else 0
    if not errors:
        return redirect(f"/courses/{course_id}/")
    # 有錯誤時顯示清單；完全沒有可匯入的列時回傳 400
    status = 200 if rows else 400
    return render(request, template,
                  {**_roster_context(request.course), "form": RosterUploadForm(),
                   "added": added, "errors": errors},
                  status=status)


@login_required
@require_course_role("professor", "ta")
@require_POST
def roster_add(request, course_id):
    """名單頁表格內單筆加入學生。規則與 CSV 匯入相同：已在課程中的人角色不變。"""
    form = RosterAddForm(request.POST)
    if not form.is_valid():
        return _invalid(request, "courses/roster_import.html",
                        {**_roster_context(request.course),
                         "form": RosterUploadForm(), "add_form": form})
    sid, name = form.cleaned_data["student_id"], form.cleaned_data["name"]
    if import_roster(request.course, [{"student_id": sid, "name": name}]):
        messages.success(request, f"已加入 {sid}")
    else:
        messages.info(request, f"{sid} 已在名單中，未變更")
    return redirect("roster_import", course_id=course_id)


@login_required
@require_course_role("professor")
def add_ta(request, course_id):
    template = "courses/add_ta.html"
    ctx = {"course": request.course}
    if request.method != "POST":
        return render(request, template, {**ctx, "form": AddTaForm()})

    form = AddTaForm(request.POST)
    if not form.is_valid():
        return _invalid(request, template, {**ctx, "form": form})

    with transaction.atomic():
        user = get_or_create_placeholder(form.cleaned_data["student_id"])
        enrollment, created = Enrollment.objects.get_or_create(
            user=user, course=request.course, defaults={"role": "ta"})
        # 唯一允許的角色變更：把本課的學生升為 TA。professor 不會被降級。
        if not created and enrollment.role == "student":
            enrollment.role = "ta"
            enrollment.save(update_fields=["role"])
    return redirect(f"/courses/{course_id}/")


@login_required
@require_course_role("professor", "ta")
def assignment_create(request, course_id):
    template = "courses/assignment_form.html"
    ctx = {"course": request.course}
    if request.method != "POST":
        return render(request, template, {**ctx, "form": AssignmentForm()})

    form = AssignmentForm(request.POST)
    if not form.is_valid():
        return _invalid(request, template, {**ctx, "form": form})
    Assignment.objects.create(course=request.course, **form.cleaned_data)
    return redirect(f"/courses/{course_id}/")


@login_required
@require_course_role("professor", "ta")
def problem_create(request, course_id, assignment_id):
    # assignment 必須屬於 URL 中的課程，否則 404（避免跨課程新增題目）
    assignment = get_object_or_404(Assignment, pk=assignment_id, course=request.course)
    template = "courses/problem_form.html"
    ctx = {
        "course": request.course,
        "assignment": assignment,
        "existing_numbers": list(assignment.problems.values_list("number", flat=True)),
    }
    if request.method != "POST":
        return render(request, template, {**ctx, "form": ProblemForm(assignment=assignment)})

    form = ProblemForm(request.POST, assignment=assignment)
    if not form.is_valid():
        return _invalid(request, template, {**ctx, "form": form})
    data = form.cleaned_data
    try:
        # savepoint：被唯一約束擋下時（兩人同時建立同題號），外層交易仍可繼續使用
        with transaction.atomic():
            Problem.objects.create(
                assignment=assignment,
                number=data["number"],
                statement=data["statement"],
            )
    except IntegrityError:
        form.add_error("number", duplicate_number_message(data["number"]))
        return _invalid(request, template, {**ctx, "form": form})
    return redirect(f"/courses/{course_id}/")


@login_required
def dashboard(request):
    enrollments = request.user.enrollments.select_related("course")
    profile = getattr(request.user, "profile", None)
    can_create = getattr(getattr(request.user, "profile", None), "can_create_course", False)
    # 沒有學號、也沒有任何課程：很可能是登入時沒有同意提供學號的學生，
    # 導致無法認領老師匯入的名單。提示他重新登入並授權學號。
    needs_student_id = (
        profile is not None
        and not profile.student_id
        and not enrollments.exists()
    )
    return render(request, "dashboard.html", {
        "enrollments": enrollments,
        "can_create": can_create,
        "needs_student_id": needs_student_id,
    })


@login_required
def course_detail(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    role = get_role(request.user, course)
    if role is None:
        return HttpResponseForbidden("forbidden")
    return render(request, "courses/course_detail.html", {
        "course": course,
        "course_role": role,
    })