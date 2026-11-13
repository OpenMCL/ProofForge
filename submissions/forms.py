from django import forms
from django.core.exceptions import ValidationError


class GradeForm(forms.Form):
    """批改表單。行內評論是選填的，但一旦填了內容，就必須指定合法的位置。"""

    score = forms.IntegerField(min_value=0)  # 若之後題目有滿分設定，在這裡加 max_value
    overall_comment = forms.CharField(required=False)
    body = forms.CharField(required=False)
    anchor_start = forms.IntegerField(min_value=0, required=False)
    anchor_end = forms.IntegerField(min_value=0, required=False)

    def __init__(self, *args, content_length, **kwargs):
        super().__init__(*args, **kwargs)
        self.content_length = content_length

    def clean(self):
        cleaned = super().clean()
        body = cleaned.get("body")
        start = cleaned.get("anchor_start")
        end = cleaned.get("anchor_end")

        # 欄位本身已經驗證失敗（例如 anchor 不是整數）時，不再做組合檢查
        if any(name in self.errors for name in ("body", "anchor_start", "anchor_end")):
            return cleaned

        if not body:
            cleaned["inline_comment"] = None
            return cleaned

        if start is None or end is None:
            raise ValidationError("行內評論需要指定起訖位置")
        if start > end:
            raise ValidationError("行內評論的起始位置不能大於結束位置")
        if end > self.content_length:
            raise ValidationError("行內評論的位置超出繳交內容的範圍")

        cleaned["inline_comment"] = {
            "anchor_start": start,
            "anchor_end": end,
            "body": body,
        }
        return cleaned
