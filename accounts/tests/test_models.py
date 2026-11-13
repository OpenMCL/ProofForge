from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from accounts.models import Profile

class ProfileTest(TestCase):
    def test_profile_links_to_user_and_holds_student_id(self):
        u = User.objects.create(username="s001")
        p = Profile.objects.create(user=u, student_id="B11201001", oauth_sub="sub-1")
        self.assertEqual(u.profile.student_id, "B11201001")
        self.assertFalse(p.can_create_course)

    def test_nonempty_oauth_sub_must_be_unique(self):
        Profile.objects.create(
            user=User.objects.create(username="one"), oauth_sub="same"
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Profile.objects.create(
                    user=User.objects.create(username="two"), oauth_sub="same"
                )

    def test_empty_oauth_sub_may_repeat(self):
        Profile.objects.create(
            user=User.objects.create(username="one"), oauth_sub=""
        )
        Profile.objects.create(
            user=User.objects.create(username="two"), oauth_sub=""
        )
