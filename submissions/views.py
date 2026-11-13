import json
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import ensure_csrf_cookie
from courses.models import Problem
from courses.permissions import get_role
from submissions.forms import GradeForm
from submissions.models import (
    Grade, Submission, deadline_passed, finalize_grade, grading_open, regrade)

def _staff_role(request, course):
    return get_role(request.user, course) in {"professor", "ta"}

@login_required
def submission_list(request, problem_id):
    problem = get_object_or_404(Problem, pk=problem_id)
    if not _staff_role(request, problem.assignment.course):
        return HttpResponseForbidden("forbidden")
    subs = Submission.objects.filter(problem=problem).select_related("student")
    return render(request, "submissions/grade_list.html",
        {"problem": problem, "submissions": subs})

@login_required
def grade_submission(request, submission_id):
    sub = get_object_or_404(
        Submission.objects.select_related("problem__assignment__course", "student"),
        pk=submission_id,
    )
    # 權限依據 submission 自己所屬的課程，而不是 URL 中的任何參數
    if not _staff_role(request, sub.problem.assignment.course):
        return HttpResponseForbidden("forbidden")

    template = "submissions/grade_detail.html"
    content_length = len(sub.content_markdown)
    existing = Grade.objects.filter(submission=sub).first()
    is_open = grading_open(sub)

    def page(form, status=200, error=None):
        return render(request, template, {
            "submission": sub,
            "grade": existing,
            "grading_open": is_open,
            "form": form,
            "error": error,
        }, status=status)

    if request.method != "POST":
        initial = ({"score": existing.score, "overall_comment": existing.overall_comment}
                   if existing else None)
        return page(GradeForm(initial=initial, content_length=content_length))

    form = GradeForm(request.POST, content_length=content_length)
    if not is_open:
        return page(form, status=409, error="作業尚未截止，不能批改。")
    if not form.is_valid():
        return page(form, status=400)

    data = form.cleaned_data
    fields = dict(score=data["score"], overall_comment=data["overall_comment"],
                  grader=request.user, inline_comment=data["inline_comment"])
    if existing:
        regrade(existing, **fields)
    elif finalize_grade(sub, **fields) is None:
        # 在這次請求載入頁面後，已有其他人完成第一次批改。
        # 不自動改成 regrade，以免在不知情的情況下覆蓋對方的分數。
        return page(form, status=409,
                    error="剛剛已有其他人完成批改，這次的評分沒有儲存。請重新載入後確認。")
    return redirect(f"/problems/{sub.problem.id}/submissions/")


def _require_student(request, problem):
    course = problem.assignment.course
    return get_role(request.user, course) == "student"

@login_required
@ensure_csrf_cookie
def editor(request, problem_id):
    problem = get_object_or_404(Problem, pk=problem_id)
    if not _require_student(request, problem):
        return HttpResponseForbidden("forbidden")
    sub = Submission.objects.filter(problem=problem, student=request.user).first()
    return render(request, "submissions/editor.html",
        {"problem": problem, "content": sub.content_markdown if sub else "",
         "closed": deadline_passed(problem.assignment)})

@login_required
def feedback(request, problem_id):
    problem = get_object_or_404(Problem, pk=problem_id)
    if get_role(request.user, problem.assignment.course) != "student":
        return HttpResponseForbidden("forbidden")
    sub = Submission.objects.filter(problem=problem, student=request.user).first()
    grade = getattr(sub, "grade", None) if sub else None
    comments = sub.comments.all() if sub else []
    return render(request, "submissions/feedback.html",
        {"problem": problem, "submission": sub, "grade": grade, "comments": comments})

@login_required
def autosave(request, problem_id):
    problem = get_object_or_404(Problem, pk=problem_id)
    if not _require_student(request, problem):
        return JsonResponse({"error": "forbidden"}, status=403)
    # 截止後不接受任何存檔,也不建立新的 submission
    if deadline_passed(problem.assignment):
        return JsonResponse({"error": "locked"}, status=409)
    content = json.loads(request.body).get("content", "")
    sub, _ = Submission.objects.get_or_create(problem=problem, student=request.user)
    if not sub.save_draft_content(content):
        return JsonResponse({"error": "locked"}, status=409)
    return JsonResponse({"saved": True})