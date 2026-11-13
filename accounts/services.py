import hashlib
import logging

from django.contrib.auth.models import User
from django.db import transaction

from accounts.models import Profile
from accounts.providers import OAuthIdentity

audit_log = logging.getLogger("proofforge.audit")

class AccountLinkConflict(Exception):
    pass


def _available_username(identity):
    if not User.objects.filter(username=identity.identifier[:150]).exists():
        return identity.identifier[:150]

    digest = hashlib.sha256(identity.subject.encode("utf-8")).hexdigest()
    base = f"oauth-{digest}"
    candidate = base
    suffix = 2
    while User.objects.filter(username=candidate).exists():
        suffix_text = f"-{suffix}"
        candidate = f"{base[:150 - len(suffix_text)]}{suffix_text}"
        suffix += 1
    return candidate

def _placeholder_has_activity(user):
    """佔位帳號理論上不可能有這些資料（它無法登入）。
 
    若真的有，刪除它會透過 CASCADE 一併刪掉這些資料，因此認領必須中止。
    透過反向關聯查詢，不需要 import courses 或 submissions，
    維持 accounts 不依賴其他 app 的方向。
    """
    return (
        user.submissions.exists()
        or user.owned_courses.exists()
    )

def _attach_student_id(profile, student_id):
    """已登入過、但沒有學號的帳號，在之後某次登入帶來學號時呼叫（延遲認領）。
 
    必須在 transaction 內呼叫（link_or_create_user 已是 atomic）。
    """
    other = (
        Profile.objects.select_for_update()
        .select_related("user")
        .filter(student_id=student_id)
        .first()
    )
 
    # 情況一：沒有人使用這個學號 → 直接寫入
    if other is None:
        profile.student_id = student_id
        profile.save(update_fields=["student_id"])
        audit_log.info("attach student_id user=%s student_id=%s",
                       profile.user_id, student_id)
        return
 
    # 情況三：學號屬於另一個已綁定的帳號 → 不修改，照常登入，留下紀錄
    if other.oauth_sub:
        audit_log.warning(
            "student_id already linked user=%s student_id=%s owner=%s (unchanged)",
            profile.user_id, student_id, other.user_id)
        return
 
    # 情況二：學號屬於未認領的佔位帳號 → 認領
    placeholder = other.user
    placeholder_id = placeholder.pk  # delete() 之後 pk 會變成 None，先記下來
    if _placeholder_has_activity(placeholder):
        audit_log.error(
            "claim aborted: placeholder=%s has submissions or courses; "
            "user=%s student_id=%s needs manual review",
            placeholder_id, profile.user_id, student_id)
        return
 
    moved = skipped = 0
    for enrollment in placeholder.enrollments.select_for_update():
        if profile.user.enrollments.filter(course_id=enrollment.course_id).exists():
            # 目前帳號已在這門課中：保留原本的角色，佔位帳號這筆隨帳號一起刪除
            skipped += 1
            continue
        enrollment.user = profile.user
        enrollment.save(update_fields=["user"])
        moved += 1
 
    # 先刪除佔位帳號釋放學號，再寫入目前帳號（student_id 有唯一性限制）
    placeholder.delete()
    profile.student_id = student_id
    profile.save(update_fields=["student_id"])
    audit_log.info(
        "claim placeholder=%s by user=%s student_id=%s moved=%s skipped=%s",
        placeholder_id,
        profile.user_id, student_id, moved, skipped)
 

@transaction.atomic
def link_or_create_user(identity):
    if not isinstance(identity, OAuthIdentity):
        raise TypeError("identity must be an OAuthIdentity")

    profile = (
        Profile.objects.select_for_update()
        .filter(oauth_sub=identity.subject)
        .first()
    )
    if profile:
        if identity.student_id and not profile.student_id:
            _attach_student_id(profile, identity.student_id)
        elif identity.student_id and profile.student_id != identity.student_id:
            audit_log.warning(
                "student_id mismatch user=%s stored=%s portal=%s (unchanged)",
                profile.user_id, profile.student_id, identity.student_id)
        return profile.user
 

    if identity.student_id:
        profile = (
            Profile.objects.select_for_update()
            .filter(student_id=identity.student_id)
            .first()
        )
        if profile:
            if profile.oauth_sub and profile.oauth_sub != identity.subject:
                raise AccountLinkConflict(
                    "student ID is already linked to another OAuth subject"
                )
            profile.oauth_sub = identity.subject
            profile.save(update_fields=["oauth_sub"])
            return profile.user

    user = User(
        username=_available_username(identity),
        first_name=identity.display_name[:150],
        email=identity.email,
    )
    user.set_unusable_password()
    user.save()
    
    Profile.objects.create(
        user=user,
        student_id=identity.student_id,
        oauth_sub=identity.subject,
    )
    return user


def get_or_create_placeholder(student_id, display_name=""):
    """依學號取得使用者；不存在時建立尚未綁定 OAuth 的佔位帳號。

    roster 匯入與 add_ta 共用這個函式，確保佔位帳號的建立方式只有一種：
    沒有可用密碼、oauth_sub 為空，等待本人第一次以 NCU Portal 登入時認領。
    呼叫端負責包在 transaction.atomic() 裡。
    """
    profile = (
        Profile.objects.select_related("user")
        .filter(student_id=student_id)
        .first()
    )
    if profile:
        return profile.user

    user = User(username=f"u-{student_id}", first_name=display_name[:150])
    user.set_unusable_password()
    user.save()
    Profile.objects.create(user=user, student_id=student_id)
    return user
