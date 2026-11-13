from django import forms
from django.core.exceptions import ValidationError

from accounts.validators import validate_student_id


class CourseForm(forms.Form):
    title = forms.CharField(max_length=200)
    term = forms.CharField(max_length=20)


class AddTaForm(forms.Form):
    student_id = forms.CharField(max_length=20, validators=[validate_student_id])


class AssignmentForm(forms.Form):
    title = forms.CharField(max_length=200, label="標題")
    description = forms.CharField(required=False, label="說明")
    # 接受 <input type="datetime-local"> 的格式；USE_TZ=True 時，
    # 沒有時區的輸入會以 TIME_ZONE（Asia/Taipei）解讀並轉為 aware datetime。
    deadline = forms.DateTimeField(label="截止時間")


def duplicate_number_message(number):
    return f"這份作業已經有第 {number} 題"


class ProblemForm(forms.Form):
    number = forms.IntegerField(min_value=1, label="題號")
    statement = forms.CharField(label="題目內容")

    def __init__(self, *args, assignment, **kwargs):
        # assignment 為必填：漏傳會直接報錯，而不是默默跳過重複題號檢查。
        super().__init__(*args, **kwargs)
        self.assignment = assignment

    def clean_number(self):
        # 友善的錯誤訊息；真正的保證是 DB 的 unique_problem_number_per_assignment。
        # 之後若做「編輯題目」，要 .exclude(pk=題目本身)。
        number = self.cleaned_data["number"]
        if self.assignment.problems.filter(number=number).exists():
            raise ValidationError(duplicate_number_message(number))
        return number


class RosterAddForm(forms.Form):
    """名單頁表格內單筆加入學生。"""
    student_id = forms.CharField(max_length=20, validators=[validate_student_id], label="學號")
    name = forms.CharField(max_length=150, required=False, label="姓名")


class RosterUploadForm(forms.Form):
    MAX_BYTES = 1024 * 1024  # 1 MB，約數萬列，遠超過一門課的人數
    ENCODINGS = ("utf-8-sig", "cp950")  # Excel 常見輸出：UTF-8（含 BOM）或 Big5

    file = forms.FileField()

    def clean_file(self):
        """回傳解碼後的文字，而不是檔案物件。"""
        f = self.cleaned_data["file"]
        if f.size > self.MAX_BYTES:
            raise ValidationError("檔案過大（上限 1 MB）")
        raw = f.read()
        for encoding in self.ENCODINGS:
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise ValidationError("無法辨識檔案編碼，請另存為 UTF-8 格式的 CSV")
