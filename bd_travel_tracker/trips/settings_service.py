from dataclasses import dataclass

from .models import (
    SettingsAuditLog,
    UserAppearanceSettings,
    UserCommunitySettings,
    UserDataSettings,
    UserMediaSettings,
    UserNotificationSettings,
    UserPrivacySettings,
    UserProfile,
    UserRegionalSettings,
    UserSecuritySettings,
    UserTravelPreferences,
)
from .settings_constants import SETTINGS_META, SETTINGS_SECTIONS


@dataclass
class SettingsBundle:
    profile: UserProfile
    privacy: UserPrivacySettings
    security: UserSecuritySettings
    appearance: UserAppearanceSettings
    regional: UserRegionalSettings
    notifications: UserNotificationSettings
    media: UserMediaSettings
    community: UserCommunitySettings
    travel: UserTravelPreferences
    data: UserDataSettings


def get_or_create_settings_bundle(user):
    return SettingsBundle(
        profile=UserProfile.objects.get_or_create(user=user)[0],
        privacy=UserPrivacySettings.objects.get_or_create(user=user)[0],
        security=UserSecuritySettings.objects.get_or_create(user=user)[0],
        appearance=UserAppearanceSettings.objects.get_or_create(user=user)[0],
        regional=UserRegionalSettings.objects.get_or_create(user=user)[0],
        notifications=UserNotificationSettings.objects.get_or_create(user=user)[0],
        media=UserMediaSettings.objects.get_or_create(user=user)[0],
        community=UserCommunitySettings.objects.get_or_create(user=user)[0],
        travel=UserTravelPreferences.objects.get_or_create(user=user)[0],
        data=UserDataSettings.objects.get_or_create(user=user)[0],
    )


def normalize_settings_section(section):
    if section in SETTINGS_SECTIONS:
        return section
    return "account"


def build_settings_sidebar(active_section):
    items = []
    for key in SETTINGS_SECTIONS:
        meta = SETTINGS_META[key]
        items.append(
            {
                "key": key,
                "label": meta["label"],
                "icon": meta["icon"],
                "description": meta["description"],
                "is_active": key == active_section,
            }
        )
    return items


def get_settings_section_meta(section):
    return SETTINGS_META[normalize_settings_section(section)]


def log_settings_change(user, section, action, request, changed_fields=None):
    changed_fields = changed_fields or []
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
    SettingsAuditLog.objects.create(
        user=user,
        section=section,
        action=action,
        changed_fields=changed_fields,
        ip_address=forwarded_for or request.META.get("REMOTE_ADDR") or None,
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
    )
