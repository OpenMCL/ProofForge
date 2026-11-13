import re

from django.core.exceptions import ValidationError

# 目前只限制字元集與長度。確認 NCU 學號的實際格式後（例如固定 9 碼數字）請收緊。
STUDENT_ID_RE = re.compile(r"[A-Za-z0-9]{1,20}")


def is_valid_student_id(value):
    return bool(STUDENT_ID_RE.fullmatch(value or ""))


def validate_student_id(value):
    if not is_valid_student_id(value):
        raise ValidationError("學號格式不正確")
