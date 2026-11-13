from collections import defaultdict

from django.db import migrations, models


def renumber_duplicates(apps, schema_editor):
    """加唯一約束前，處理同一份作業內的重複題號。

    每組重複保留 id 最小（最早建立）的那筆；其餘依 id 順序改成
    「該作業目前最大題號 + 1」並逐筆遞增。不刪任何資料，提交不受影響。
    """
    Problem = apps.get_model("courses", "Problem")
    by_assignment = defaultdict(list)
    for p in Problem.objects.order_by("assignment_id", "number", "id"):
        by_assignment[p.assignment_id].append(p)

    for assignment_id, problems in by_assignment.items():
        next_number = max(p.number for p in problems) + 1
        seen = set()
        for p in problems:
            if p.number not in seen:
                seen.add(p.number)
                continue
            old = p.number
            p.number = next_number
            p.save(update_fields=["number"])
            print(f"\n  renumbered problem id={p.pk} (assignment {assignment_id}): {old} -> {next_number}")
            next_number += 1


class Migration(migrations.Migration):

    dependencies = [
        ('courses', '0003_problem_number_integer_drop_order'),
    ]

    operations = [
        migrations.RunPython(renumber_duplicates, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='problem',
            constraint=models.UniqueConstraint(fields=('assignment', 'number'), name='unique_problem_number_per_assignment'),
        ),
    ]
