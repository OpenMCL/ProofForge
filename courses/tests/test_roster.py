import io
from django.contrib.auth.models import User
from django.test import TestCase
from accounts.models import Profile
from courses.models import Course, Enrollment
from courses.roster import parse_roster_csv, import_roster


class RosterTest(TestCase):
    def test_parse_skips_rows_without_student_id(self):
        f = io.StringIO("student_id,name\nB001,小明\n,缺學號\nB002,小華\n")
        rows, errors = parse_roster_csv(f.getvalue())
        self.assertEqual([r["student_id"] for r in rows], ["B001", "B002"])
        self.assertEqual(len(errors), 1)

    def test_import_creates_enrollments_and_dedupes(self):
        prof = User.objects.create(username="prof")
        course = Course.objects.create(title="C", term="114-1", owner=prof)
        rows = [{"student_id": "B001", "name": "小明"}, {"student_id": "B001", "name": "小明"}]
        added = import_roster(course, rows)
        self.assertEqual(added, 1)
        self.assertEqual(Enrollment.objects.filter(course=course, role="student").count(), 1)


from django.core.files.uploadedfile import SimpleUploadedFile


class RosterViewTest(TestCase):
    def setUp(self):
        self.prof = User.objects.create_user("prof", password="x")
        Profile.objects.create(user=self.prof, student_id="T1", can_create_course=True)
        self.course = Course.objects.create(title="C", term="114-1", owner=self.prof)
        Enrollment.objects.create(user=self.prof, course=self.course, role="professor")

    def test_student_cannot_import(self):
        stu = User.objects.create_user("stu", password="x")
        Profile.objects.create(user=stu, student_id="B500")
        Enrollment.objects.create(user=stu, course=self.course, role="student")
        self.client.force_login(stu)
        resp = self.client.post(f"/courses/{self.course.id}/roster/")
        self.assertEqual(resp.status_code, 403)

    def test_import_page_explains_csv_format(self):
        self.course.title = "名單匯入測試課程"
        self.course.save(update_fields=["title"])
        self.client.force_login(self.prof)
        response = self.client.get(f"/courses/{self.course.id}/roster/")
        self.assertContains(response, self.course.title)
        self.assertContains(response, "student_id")
        self.assertContains(response, "name")
        self.assertContains(response, 'accept=".csv,text/csv"')
        self.assertContains(response, "required")
        self.assertContains(response, f"/courses/{self.course.id}/")

    def test_professor_imports_csv(self):
        self.client.force_login(self.prof)
        csv_file = SimpleUploadedFile("r.csv", b"student_id,name\nB001,A\n", content_type="text/csv")
        resp = self.client.post(f"/courses/{self.course.id}/roster/", {"file": csv_file})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Enrollment.objects.filter(
            course=self.course, role="student", user__profile__student_id="B001").exists())

    def test_import_reports_skipped_bad_rows(self):
        self.client.force_login(self.prof)
        csv_file = SimpleUploadedFile("r.csv",
            "student_id,name\nB001,A\n,缺學號\nB002,C\n".encode("utf-8"),
            content_type="text/csv")
        resp = self.client.post(f"/courses/{self.course.id}/roster/", {"file": csv_file})
        self.assertEqual(resp.status_code, 200)            # 有壞列 → 停在頁面回報
        self.assertContains(resp, "第 3 列")               # 壞列的行號
        self.assertContains(resp, "缺 student_id")          # 壞列的原因
        # 好的列仍照常匯入
        self.assertTrue(Enrollment.objects.filter(course=self.course, role="student",
            user__profile__student_id="B001").exists())
        self.assertTrue(Enrollment.objects.filter(course=self.course, role="student",
            user__profile__student_id="B002").exists())


class RosterListTest(TestCase):
    def setUp(self):
        self.prof = User.objects.create_user("prof", password="x", first_name="王教授")
        Profile.objects.create(user=self.prof, student_id="T001", oauth_sub="sub-prof")
        self.course = Course.objects.create(title="C", term="114-1", owner=self.prof)
        Enrollment.objects.create(user=self.prof, course=self.course, role="professor")
        self.url = f"/courses/{self.course.id}/roster/"

    def _add(self, username, student_id, role, name="", oauth_sub="", course=None):
        user = User.objects.create_user(username, first_name=name)
        Profile.objects.create(user=user, student_id=student_id, oauth_sub=oauth_sub)
        Enrollment.objects.create(user=user, course=course or self.course, role=role)
        return user

    def test_lists_current_members_with_role_and_name(self):
        self._add("b1", "B001", "student", name="小明")
        self._add("ta", "B900", "ta", name="助教甲")
        self.client.force_login(self.prof)

        response = self.client.get(self.url)

        self.assertContains(response, "目前名單（3 人）")
        for text in ["T001", "王教授", "教授", "B900", "助教甲", "助教", "B001", "小明", "學生"]:
            self.assertContains(response, text)

    def test_orders_professor_then_ta_then_students_by_student_id(self):
        self._add("b2", "B002", "student")
        self._add("b1", "B001", "student")
        self._add("ta", "B900", "ta")
        self.client.force_login(self.prof)

        response = self.client.get(self.url)

        ids = [e.user.profile.student_id for e in response.context["roster"]]
        self.assertEqual(ids, ["T001", "B900", "B001", "B002"])

    def test_shows_whether_member_has_logged_in(self):
        self._add("u-B001", "B001", "student")
        self._add("b2", "B002", "student", oauth_sub="sub-b2")
        self.client.force_login(self.prof)

        html = self.client.get(self.url).content.decode()

        self.assertRegex(html, r"(?s)<td>B001</td>.*?<td>尚未登入</td>")
        self.assertRegex(html, r"(?s)<td>B002</td>.*?<td>已登入</td>")

    def test_falls_back_to_username_without_display_name(self):
        self._add("u-B001", "B001", "student")
        self.client.force_login(self.prof)

        self.assertContains(self.client.get(self.url), "u-B001")

    def test_member_without_profile_does_not_break_page(self):
        user = User.objects.create_user("no-profile")
        Enrollment.objects.create(user=user, course=self.course, role="student")
        self.client.force_login(self.prof)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "no-profile")

    def test_excludes_members_of_other_courses(self):
        other = Course.objects.create(title="Other", term="114-1", owner=self.prof)
        self._add("x", "X999", "student", course=other)
        self.client.force_login(self.prof)

        self.assertNotContains(self.client.get(self.url), "X999")

    def test_ta_also_sees_roster(self):
        ta = self._add("ta", "B900", "ta")
        self.client.force_login(ta)

        self.assertContains(self.client.get(self.url), "T001")

    def test_empty_student_list_message(self):
        self.client.force_login(self.prof)

        self.assertContains(self.client.get(self.url), "尚未加入學生")

    def test_roster_shown_after_import_with_errors(self):
        self.client.force_login(self.prof)
        f = SimpleUploadedFile("r.csv", "student_id,name\nB001,小明\n,缺學號\n".encode())

        response = self.client.post(self.url, {"file": f})

        self.assertContains(response, "B001")
        self.assertContains(response, "目前名單（2 人）")

    def test_roster_shown_when_form_invalid(self):
        self.client.force_login(self.prof)

        response = self.client.post(self.url, {})

        self.assertContains(response, "T001", status_code=400)
