import logging

from django.contrib.auth.models import User
from django.db import models, transaction
from django.utils import timezone
from courses.models import Problem

audit_log = logging.getLogger("proofforge.audit")


class GradingNotOpen(Exception):
    """作業尚未截止，不能批改。"""


def deadline_passed(assignment, now=None):
    """截止時間過後:學生不能再存檔,批改者才能批改。"""
    return (now or timezone.now()) > assignment.deadline


def grading_open(submission, now=None):
    """截止時間過後才能批改。"""
    return deadline_passed(submission.problem.assignment, now)

class Submission(models.Model):
    STATUS = [("draft", "draft"), ("graded", "graded")]
    problem = models.ForeignKey(Problem, on_delete=models.CASCADE, related_name="submissions")
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="submissions")
    content_markdown = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=10, choices=STATUS, default="draft")

    class Meta:
        unique_together = [("problem", "student")]

    def __str__(self):
        return f"{self.problem.number} / {self.student.username} ({self.status})"

    @property
    def locked(self):
        return self.status == "graded"

    def save_draft_content(self, content):
        """只在仍是 draft 且尚未截止時,以單一原子更新寫入內容

        用 ``WHERE status='draft' AND deadline >= now`` 的條件更新避免 TOCTOU:
        若批改者在期間把 submission 設為 graded,或請求跨過截止時間,
        更新會命中 0 列、回傳 False,絕不覆蓋既有狀態或內容。
        """
        now = timezone.now()
        updated = Submission.objects.filter(
            pk=self.pk, status="draft", problem__assignment__deadline__gte=now,
        ).update(content_markdown=content, updated_at=now)
        if not updated:
            return False
        self.content_markdown = content
        self.updated_at = now
        return True


class InlineComment(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="comments")
    anchor_start = models.PositiveIntegerField()
    anchor_end = models.PositiveIntegerField()
    body = models.TextField()
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.submission} [{self.anchor_start}-{self.anchor_end}]"


class Grade(models.Model):
    submission = models.OneToOneField(Submission, on_delete=models.CASCADE, related_name="grade")
    score = models.IntegerField()
    overall_comment = models.TextField(blank=True)
    grader = models.ForeignKey(User, on_delete=models.CASCADE)
    graded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.submission} = {self.score}"


def finalize_grade(submission, score, overall_comment, grader, inline_comment=None):
    """第一次批改：把 draft 鎖定為 graded 並建立 Grade。

    以 ``WHERE status='draft'`` 的條件更新保證只有一個贏家；
    輸掉的呼叫回傳 None，不寫入任何東西。截止前呼叫會拋出 GradingNotOpen。
    """
    if not grading_open(submission):
        raise GradingNotOpen()
    with transaction.atomic():
        won = Submission.objects.filter(pk=submission.pk, status="draft").update(status="graded")
        if not won:
            return None
        if inline_comment:
            InlineComment.objects.create(submission=submission, author=grader, **inline_comment)
        grade = Grade.objects.create(submission=submission, score=score,
            overall_comment=overall_comment, grader=grader)
    submission.status = "graded"
    audit_log.info("grade submission=%s grader=%s score=%s",
                   submission.pk, grader.pk, score)
    return grade


def regrade(grade, score, overall_comment, grader, inline_comment=None):
    """修改既有的評分。submission 維持 graded（鎖定）狀態。

    Grade 只保存最新的值，因此每次修改都寫一筆 audit log，
    記錄修改前後的分數與修改者，作為成績爭議時的依據。
    兩人同時修改時，後寫入者覆蓋先寫入者（兩筆都會留在 log 中）。
    """
    with transaction.atomic():
        grade = Grade.objects.select_for_update().get(pk=grade.pk)
        old_score, old_grader_id = grade.score, grade.grader_id
        grade.score = score
        grade.overall_comment = overall_comment
        grade.grader = grader
        grade.save(update_fields=["score", "overall_comment", "grader"])
        if inline_comment:
            InlineComment.objects.create(
                submission_id=grade.submission_id, author=grader, **inline_comment)
    audit_log.info(
        "regrade submission=%s grader=%s score=%s->%s previous_grader=%s",
        grade.submission_id, grader.pk, old_score, score, old_grader_id)
    return grade