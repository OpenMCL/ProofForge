import csv
import io

from django.db import transaction

from accounts.services import get_or_create_placeholder
from accounts.validators import is_valid_student_id
from courses.models import Enrollment

REQUIRED_COLUMN = "student_id"


def parse_roster_csv(text):
    """解析 roster CSV 文字。回傳 (rows, errors)；不寫入資料庫。"""
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = [(name or "").strip() for name in (reader.fieldnames or [])]
    if REQUIRED_COLUMN not in fieldnames:
        return [], [{"line": 1, "reason": f"缺少 {REQUIRED_COLUMN} 欄位（目前的欄位：{', '.join(fieldnames) or '無'}）"}]
    reader.fieldnames = fieldnames

    rows, errors, seen = [], [], set()
    for line, raw in enumerate(reader, start=2):
        sid = (raw.get(REQUIRED_COLUMN) or "").strip()
        if not sid:
            errors.append({"line": line, "reason": "缺 student_id"})
            continue
        if not is_valid_student_id(sid):
            errors.append({"line": line, "reason": "學號格式不正確"})
            continue
        if sid in seen:
            errors.append({"line": line, "reason": f"學號 {sid} 重複"})
            continue
        seen.add(sid)
        rows.append({"student_id": sid, "name": (raw.get("name") or "").strip()})
    return rows, errors


@transaction.atomic
def import_roster(course, rows):
    """把 rows 加入課程成為學生。已在課程中的人（含 TA、professor）角色不變。"""
    added = 0
    for r in rows:
        user = get_or_create_placeholder(r["student_id"], r.get("name", ""))
        _, created = Enrollment.objects.get_or_create(
            user=user, course=course, defaults={"role": "student"})
        if created:
            added += 1
    return added