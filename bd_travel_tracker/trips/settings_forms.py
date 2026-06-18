from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .settings_constants import (
    CURRENCY_CHOICES,
    DATE_FORMAT_CHOICES,
    DISTANCE_UNIT_CHOICES,
    EXPORT_FORMAT_CHOICES,
    FONT_SIZE_CHOICES,
    IMAGE_QUALITY_CHOICES,
    INTERACTION_CHOICES,
    LAYOUT_DENSITY_CHOICES,
    MAP_STYLE_CHOICES,
    MAP_VIEW_CHOICES,
    STORAGE_PROVIDER_CHOICES,
    TIMEZONE_CHOICES,
    VIDEO_UPLOAD_LIMIT_CHOICES,
    VISIBILITY_CHOICES,
)
from .settings_service import get_or_create_settings_bundle
from .validators import IMAGE_EXTENSIONS, IMAGE_MAX_BYTES, validate_upload

User = get_user_model()


class BaseSettingsForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        self.bundle = kwargs.pop("bundle", None) or get_or_create_settings_bundle(self.user)
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs.setdefault("class", "form-control")
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select")
            else:
                field.widget.attrs.setdefault("class", "form-control")


class AccountSettingsForm(BaseSettingsForm):
    email = forms.EmailField()
    phone = forms.CharField(max_length=30)
    recovery_email = forms.EmailField(required=False)
    recovery_phone = forms.CharField(max_length=30, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        security = self.bundle.security
        self.fields["email"].initial = self.user.email
        self.fields["phone"].initial = self.bundle.profile.phone
        self.fields["recovery_email"].initial = security.recovery_email
        self.fields["recovery_phone"].initial = security.recovery_phone

    def save(self):
        security = self.bundle.security
        previous_email = self.user.email

        self.bundle.profile.phone = self.cleaned_data["phone"].strip()
        self.bundle.profile.save(update_fields=["phone"])
        self.user.email = self.cleaned_data["email"].strip()
        self.user.save(update_fields=["email"])

        security.recovery_email = self.cleaned_data["recovery_email"].strip()
        security.recovery_phone = self.cleaned_data["recovery_phone"].strip()
        if previous_email != self.user.email:
            security.email_verified = False
        security.save(update_fields=["recovery_email", "recovery_phone", "email_verified", "updated_at"])


class ProfileSettingsSectionForm(BaseSettingsForm):
    full_name = forms.CharField(max_length=150)
    username = forms.CharField(max_length=150)
    avatar_file = forms.FileField(required=False)
    cover_photo = forms.FileField(required=False)
    avatar_url = forms.URLField(required=False)
    bio = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}))
    location = forms.CharField(required=False, max_length=120)
    website = forms.URLField(required=False)
    social_links = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="One link per line. Public profile will show only valid links.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        profile = self.bundle.profile
        self.fields["full_name"].initial = profile.full_name
        self.fields["username"].initial = self.user.username
        self.fields["avatar_url"].initial = profile.avatar_url
        self.fields["bio"].initial = profile.bio
        self.fields["location"].initial = profile.location
        self.fields["website"].initial = profile.website
        self.fields["social_links"].initial = "\n".join(profile.social_links or [])
        self.fields["avatar_file"].widget.attrs.update({"accept": "image/*"})
        self.fields["cover_photo"].widget.attrs.update({"accept": "image/*"})

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if not username:
            raise ValidationError("Username is required.")
        duplicate = User.objects.filter(username__iexact=username).exclude(pk=self.user.pk)
        if duplicate.exists():
            raise ValidationError("This username is already taken.")
        return username

    def clean_avatar_file(self):
        avatar_file = self.cleaned_data.get("avatar_file")
        validate_upload(
            avatar_file,
            allowed_extensions=IMAGE_EXTENSIONS,
            max_size_bytes=IMAGE_MAX_BYTES,
            label="Profile photo",
        )
        return avatar_file

    def clean_cover_photo(self):
        cover_photo = self.cleaned_data.get("cover_photo")
        validate_upload(
            cover_photo,
            allowed_extensions=IMAGE_EXTENSIONS,
            max_size_bytes=IMAGE_MAX_BYTES,
            label="Cover photo",
        )
        return cover_photo

    def clean_social_links(self):
        raw_value = self.cleaned_data.get("social_links", "")
        links = [line.strip() for line in raw_value.splitlines() if line.strip()]
        if len(links) > 8:
            raise ValidationError("Use up to 8 public links.")
        return links

    def save(self):
        profile = self.bundle.profile
        profile.full_name = self.cleaned_data["full_name"].strip()
        for field_name in ("avatar_url", "bio", "location", "website"):
            setattr(profile, field_name, self.cleaned_data.get(field_name, ""))
        profile.social_links = self.cleaned_data.get("social_links", [])
        if self.cleaned_data.get("avatar_file"):
            profile.avatar_file = self.cleaned_data["avatar_file"]
        if self.cleaned_data.get("cover_photo"):
            profile.cover_photo = self.cleaned_data["cover_photo"]
        profile.save()
        self.user.username = self.cleaned_data["username"].strip()
        self.user.save(update_fields=["username"])


class PrivacySettingsForm(BaseSettingsForm):
    public_profile = forms.BooleanField(required=False)
    contact_visibility = forms.ChoiceField(choices=[("private", "Private"), ("public", "Public")])
    default_album_visibility = forms.ChoiceField(choices=[("private", "Private"), ("public", "Public")])
    default_story_visibility = forms.ChoiceField(choices=[("private", "Private"), ("public", "Public")])
    trip_visibility = forms.ChoiceField(choices=VISIBILITY_CHOICES)
    history_visibility = forms.ChoiceField(choices=VISIBILITY_CHOICES)
    who_can_message = forms.ChoiceField(choices=INTERACTION_CHOICES)
    who_can_comment = forms.ChoiceField(choices=INTERACTION_CHOICES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        profile = self.bundle.profile
        privacy = self.bundle.privacy
        community = self.bundle.community
        self.fields["public_profile"].initial = profile.public_profile
        self.fields["contact_visibility"].initial = profile.contact_visibility
        self.fields["default_album_visibility"].initial = profile.default_album_visibility
        self.fields["default_story_visibility"].initial = profile.default_story_visibility
        self.fields["trip_visibility"].initial = privacy.trip_visibility
        self.fields["history_visibility"].initial = privacy.history_visibility
        self.fields["who_can_message"].initial = community.who_can_message
        self.fields["who_can_comment"].initial = community.who_can_comment

    def save(self):
        profile = self.bundle.profile
        privacy = self.bundle.privacy
        community = self.bundle.community
        profile.public_profile = self.cleaned_data.get("public_profile", False)
        profile.contact_visibility = self.cleaned_data["contact_visibility"]
        profile.default_album_visibility = self.cleaned_data["default_album_visibility"]
        profile.default_story_visibility = self.cleaned_data["default_story_visibility"]
        profile.save(
            update_fields=[
                "public_profile",
                "contact_visibility",
                "default_album_visibility",
                "default_story_visibility",
            ]
        )
        privacy.trip_visibility = self.cleaned_data["trip_visibility"]
        privacy.history_visibility = self.cleaned_data["history_visibility"]
        privacy.save(
            update_fields=[
                "trip_visibility",
                "history_visibility",
                "updated_at",
            ]
        )
        community.who_can_message = self.cleaned_data["who_can_message"]
        community.who_can_comment = self.cleaned_data["who_can_comment"]
        community.save(update_fields=["who_can_message", "who_can_comment", "updated_at"])
        profile.allow_dm = self.cleaned_data["who_can_message"] != "no_one"
        profile.save(update_fields=["allow_dm"])


class SecuritySettingsForm(BaseSettingsForm):
    current_password = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False))
    new_password = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False))
    confirm_password = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False))
    two_factor_enabled = forms.BooleanField(required=False)
    login_alerts = forms.BooleanField(required=False)
    suspicious_activity_alerts = forms.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        security = self.bundle.security
        self.fields["two_factor_enabled"].initial = security.two_factor_enabled
        self.fields["login_alerts"].initial = security.login_alerts
        self.fields["suspicious_activity_alerts"].initial = security.suspicious_activity_alerts

    def clean(self):
        cleaned_data = super().clean()
        current_password = cleaned_data.get("current_password")
        new_password = cleaned_data.get("new_password")
        confirm_password = cleaned_data.get("confirm_password")

        if new_password or confirm_password:
            if not current_password:
                raise ValidationError("Enter your current password to set a new password.")
            if not self.user.check_password(current_password):
                raise ValidationError("Current password is incorrect.")
            if new_password != confirm_password:
                raise ValidationError("New password and confirmation do not match.")
            validate_password(new_password, self.user)
        return cleaned_data

    def save(self):
        security = self.bundle.security
        security.two_factor_enabled = self.cleaned_data.get("two_factor_enabled", False)
        security.login_alerts = self.cleaned_data.get("login_alerts", False)
        security.suspicious_activity_alerts = self.cleaned_data.get("suspicious_activity_alerts", False)
        security.save(update_fields=["two_factor_enabled", "login_alerts", "suspicious_activity_alerts", "updated_at"])
        if self.cleaned_data.get("new_password"):
            self.user.set_password(self.cleaned_data["new_password"])
            self.user.save(update_fields=["password"])


class AppearanceSettingsForm(BaseSettingsForm):
    theme_mode = forms.ChoiceField(choices=[("light", "Light"), ("dark", "Dark"), ("night", "Night")])
    preferred_language = forms.ChoiceField(choices=[("en", "English"), ("bn", "Bangla")])
    font_size = forms.ChoiceField(choices=FONT_SIZE_CHOICES)
    layout_density = forms.ChoiceField(choices=LAYOUT_DENSITY_CHOICES)
    map_style = forms.ChoiceField(choices=MAP_STYLE_CHOICES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["theme_mode"].initial = self.bundle.profile.theme_mode
        self.fields["preferred_language"].initial = self.bundle.profile.preferred_language
        self.fields["font_size"].initial = self.bundle.appearance.font_size
        self.fields["layout_density"].initial = self.bundle.appearance.layout_density
        self.fields["map_style"].initial = self.bundle.appearance.map_style

    def save(self):
        profile = self.bundle.profile
        appearance = self.bundle.appearance
        profile.theme_mode = self.cleaned_data["theme_mode"]
        profile.preferred_language = self.cleaned_data["preferred_language"]
        profile.save(update_fields=["theme_mode", "preferred_language"])
        appearance.font_size = self.cleaned_data["font_size"]
        appearance.layout_density = self.cleaned_data["layout_density"]
        appearance.map_style = self.cleaned_data["map_style"]
        appearance.save(update_fields=["font_size", "layout_density", "map_style", "updated_at"])


class LanguageRegionSettingsForm(BaseSettingsForm):
    preferred_language = forms.ChoiceField(choices=[("en", "English"), ("bn", "Bangla")])
    timezone = forms.ChoiceField(choices=TIMEZONE_CHOICES)
    date_format = forms.ChoiceField(choices=DATE_FORMAT_CHOICES)
    currency = forms.ChoiceField(choices=CURRENCY_CHOICES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        profile = self.bundle.profile
        regional = self.bundle.regional
        self.fields["preferred_language"].initial = profile.preferred_language
        self.fields["timezone"].initial = regional.timezone
        self.fields["date_format"].initial = regional.date_format
        self.fields["currency"].initial = regional.currency

    def save(self):
        profile = self.bundle.profile
        regional = self.bundle.regional
        profile.preferred_language = self.cleaned_data["preferred_language"]
        profile.save(update_fields=["preferred_language"])
        regional.timezone = self.cleaned_data["timezone"]
        regional.date_format = self.cleaned_data["date_format"]
        regional.currency = self.cleaned_data["currency"]
        regional.save(update_fields=["timezone", "date_format", "currency", "updated_at"])


class NotificationSettingsForm(BaseSettingsForm):
    community_updates = forms.BooleanField(required=False)
    email_notifications = forms.BooleanField(required=False)
    push_notifications = forms.BooleanField(required=False)
    comment_alerts = forms.BooleanField(required=False)
    like_alerts = forms.BooleanField(required=False)
    follower_alerts = forms.BooleanField(required=False)
    message_alerts = forms.BooleanField(required=False)
    call_alerts = forms.BooleanField(required=False)
    trip_reminders = forms.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        notifications = self.bundle.notifications
        self.fields["community_updates"].initial = notifications.community_updates and self.bundle.profile.receive_community_updates
        self.fields["email_notifications"].initial = notifications.email_notifications
        self.fields["push_notifications"].initial = notifications.push_notifications
        self.fields["comment_alerts"].initial = notifications.comment_alerts
        self.fields["like_alerts"].initial = notifications.like_alerts
        self.fields["follower_alerts"].initial = notifications.follower_alerts
        self.fields["message_alerts"].initial = notifications.message_alerts
        self.fields["call_alerts"].initial = notifications.call_alerts
        self.fields["trip_reminders"].initial = notifications.trip_reminders

    def save(self):
        notifications = self.bundle.notifications
        community_updates = self.cleaned_data.get("community_updates", False)
        notifications.community_updates = community_updates
        notifications.email_notifications = self.cleaned_data.get("email_notifications", False)
        notifications.push_notifications = self.cleaned_data.get("push_notifications", False)
        notifications.comment_alerts = self.cleaned_data.get("comment_alerts", False)
        notifications.like_alerts = self.cleaned_data.get("like_alerts", False)
        notifications.follower_alerts = self.cleaned_data.get("follower_alerts", False)
        notifications.message_alerts = self.cleaned_data.get("message_alerts", False)
        notifications.call_alerts = self.cleaned_data.get("call_alerts", False)
        notifications.trip_reminders = self.cleaned_data.get("trip_reminders", False)
        notifications.save()
        self.bundle.profile.receive_community_updates = community_updates
        self.bundle.profile.save(update_fields=["receive_community_updates"])


class MediaSettingsForm(BaseSettingsForm):
    image_upload_quality = forms.ChoiceField(choices=IMAGE_QUALITY_CHOICES)
    auto_image_compression = forms.BooleanField(required=False)
    video_upload_limit = forms.ChoiceField(choices=VIDEO_UPLOAD_LIMIT_CHOICES)
    external_storage_provider = forms.ChoiceField(choices=STORAGE_PROVIDER_CHOICES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        media = self.bundle.media
        self.fields["image_upload_quality"].initial = media.image_upload_quality
        self.fields["auto_image_compression"].initial = media.auto_image_compression
        self.fields["video_upload_limit"].initial = media.video_upload_limit
        self.fields["external_storage_provider"].initial = media.external_storage_provider

    def save(self):
        media = self.bundle.media
        media.image_upload_quality = self.cleaned_data["image_upload_quality"]
        media.auto_image_compression = self.cleaned_data.get("auto_image_compression", False)
        media.video_upload_limit = self.cleaned_data["video_upload_limit"]
        media.external_storage_provider = self.cleaned_data["external_storage_provider"]
        media.save(update_fields=["image_upload_quality", "auto_image_compression", "video_upload_limit", "external_storage_provider", "updated_at"])


class CommunitySettingsForm(BaseSettingsForm):
    allow_dm = forms.BooleanField(required=False)
    who_can_message = forms.ChoiceField(choices=INTERACTION_CHOICES)
    who_can_comment = forms.ChoiceField(choices=INTERACTION_CHOICES)
    who_can_tag = forms.ChoiceField(choices=INTERACTION_CHOICES)
    who_can_mention = forms.ChoiceField(choices=INTERACTION_CHOICES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        community = self.bundle.community
        self.fields["allow_dm"].initial = self.bundle.profile.allow_dm
        self.fields["who_can_message"].initial = community.who_can_message
        self.fields["who_can_comment"].initial = community.who_can_comment
        self.fields["who_can_tag"].initial = community.who_can_tag
        self.fields["who_can_mention"].initial = community.who_can_mention

    def save(self):
        community = self.bundle.community
        self.bundle.profile.allow_dm = self.cleaned_data.get("allow_dm", False)
        self.bundle.profile.save(update_fields=["allow_dm"])
        community.who_can_message = self.cleaned_data["who_can_message"]
        community.who_can_comment = self.cleaned_data["who_can_comment"]
        community.who_can_tag = self.cleaned_data["who_can_tag"]
        community.who_can_mention = self.cleaned_data["who_can_mention"]
        community.save(update_fields=["who_can_message", "who_can_comment", "who_can_tag", "who_can_mention", "updated_at"])


class TravelPreferencesForm(BaseSettingsForm):
    default_currency = forms.ChoiceField(choices=CURRENCY_CHOICES)
    default_trip_visibility = forms.ChoiceField(choices=VISIBILITY_CHOICES)
    preferred_map_view = forms.ChoiceField(choices=MAP_VIEW_CHOICES)
    distance_unit = forms.ChoiceField(choices=DISTANCE_UNIT_CHOICES)
    default_expense_categories = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Comma-separated categories used as defaults in your trip workflow.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        travel = self.bundle.travel
        self.fields["default_currency"].initial = travel.default_currency
        self.fields["default_trip_visibility"].initial = travel.default_trip_visibility
        self.fields["preferred_map_view"].initial = travel.preferred_map_view
        self.fields["distance_unit"].initial = travel.distance_unit
        self.fields["default_expense_categories"].initial = ", ".join(
            travel.default_expense_categories or ["transport", "food", "hotel", "ticket", "other"]
        )

    def clean_default_expense_categories(self):
        raw_value = self.cleaned_data.get("default_expense_categories", "")
        return [item.strip() for item in raw_value.split(",") if item.strip()]

    def save(self):
        travel = self.bundle.travel
        travel.default_currency = self.cleaned_data["default_currency"]
        travel.default_trip_visibility = self.cleaned_data["default_trip_visibility"]
        travel.preferred_map_view = self.cleaned_data["preferred_map_view"]
        travel.distance_unit = self.cleaned_data["distance_unit"]
        travel.default_expense_categories = self.cleaned_data["default_expense_categories"]
        travel.save()


class DataBackupSettingsForm(BaseSettingsForm):
    backup_enabled = forms.BooleanField(required=False)
    export_format = forms.ChoiceField(choices=EXPORT_FORMAT_CHOICES)
    include_media_in_exports = forms.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        data_settings = self.bundle.data
        self.fields["backup_enabled"].initial = data_settings.backup_enabled
        self.fields["export_format"].initial = data_settings.export_format
        self.fields["include_media_in_exports"].initial = data_settings.include_media_in_exports

    def save(self):
        data_settings = self.bundle.data
        data_settings.backup_enabled = self.cleaned_data.get("backup_enabled", False)
        data_settings.export_format = self.cleaned_data["export_format"]
        data_settings.include_media_in_exports = self.cleaned_data.get("include_media_in_exports", False)
        data_settings.save(update_fields=["backup_enabled", "export_format", "include_media_in_exports", "updated_at"])


class DangerZoneDeactivateForm(forms.Form):
    current_password = forms.CharField(widget=forms.PasswordInput(render_value=False))
    confirm_text = forms.CharField(help_text="Type DEACTIVATE to continue.")

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("confirm_text", "").strip().upper() != "DEACTIVATE":
            raise ValidationError("Type DEACTIVATE exactly to confirm.")
        if not self.user.check_password(cleaned_data.get("current_password", "")):
            raise ValidationError("Current password is incorrect.")
        return cleaned_data


class DangerZoneDeleteForm(forms.Form):
    current_password = forms.CharField(widget=forms.PasswordInput(render_value=False))
    confirm_text = forms.CharField(help_text="Type DELETE MY ACCOUNT to continue.")

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("confirm_text", "").strip().upper() != "DELETE MY ACCOUNT":
            raise ValidationError("Type DELETE MY ACCOUNT exactly to confirm.")
        if not self.user.check_password(cleaned_data.get("current_password", "")):
            raise ValidationError("Current password is incorrect.")
        return cleaned_data
