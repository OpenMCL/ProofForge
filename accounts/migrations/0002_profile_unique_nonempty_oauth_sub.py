from django.db import migrations, models
from django.db.models import Count, Q


def reject_duplicate_subjects(apps, schema_editor):
    Profile = apps.get_model("accounts", "Profile")
    duplicate_exists = (
        Profile.objects.exclude(oauth_sub="")
        .values("oauth_sub")
        .annotate(total=Count("pk"))
        .filter(total__gt=1)
        .exists()
    )
    if duplicate_exists:
        raise RuntimeError(
            "Duplicate non-empty oauth_sub values must be resolved before migration"
        )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]

    operations = [
        migrations.RunPython(reject_duplicate_subjects, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="profile",
            constraint=models.UniqueConstraint(
                fields=("oauth_sub",),
                condition=~Q(oauth_sub=""),
                name="unique_nonempty_oauth_sub",
            ),
        ),
    ]
