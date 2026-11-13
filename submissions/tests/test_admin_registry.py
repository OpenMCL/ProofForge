from django.contrib import admin
from django.test import TestCase
from submissions.models import Grade, InlineComment, Submission


class AdminRegistryTest(TestCase):
    def test_grading_models_stay_out_of_admin(self):
        """admin 直接寫入 Grade 會繞過 finalize_grade() 的鎖定轉換,不註冊。"""
        self.assertNotIn(Grade, admin.site._registry)
        self.assertNotIn(InlineComment, admin.site._registry)
        self.assertIn(Submission, admin.site._registry)
