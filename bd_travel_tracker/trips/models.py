from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.text import slugify

from .validators import validate_album_media_upload

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

TRIP_SOURCE_CHOICES = [
    ("self", "Self Trip"),
    ("agency", "Agency Trip"),
]

ACCOUNT_TYPE_CHOICES = [
    ("personal", "Personal"),
    ("company", "Company / Agency"),
]

COMPANY_VERIFICATION_STATUS_CHOICES = [
    ("not_required", "Not Required"),
    ("pending", "Pending Review"),
    ("verified", "Verified"),
    ("rejected", "Rejected"),
]


class Division(models.Model):
    name = models.CharField(max_length=120, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class District(models.Model):
    division = models.ForeignKey(
        Division,
        on_delete=models.PROTECT,
        related_name="districts",
    )
    name = models.CharField(max_length=120)

    class Meta:
        ordering = ["division__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["division", "name"],
                name="uniq_district_name_per_division",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.division.name})"


class Upazila(models.Model):
    district = models.ForeignKey(
        District,
        on_delete=models.PROTECT,
        related_name="upazilas",
    )
    name = models.CharField(max_length=120)

    class Meta:
        ordering = ["district__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["district", "name"],
                name="uniq_upazila_name_per_district",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.district.name})"


class TourSpot(models.Model):
    upazila = models.ForeignKey(
        Upazila,
        on_delete=models.PROTECT,
        related_name="spots",
    )
    name = models.CharField(max_length=180)
    category = models.CharField(max_length=80, blank=True)
    description = models.TextField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["upazila", "name"],
                name="uniq_spot_name_per_upazila",
            )
        ]

    def __str__(self):
        return self.name

    @property
    def district(self):
        return self.upazila.district

    @property
    def division(self):
        return self.upazila.district.division


class Trip(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="trips",
    )
    division = models.ForeignKey(
        Division,
        on_delete=models.PROTECT,
        related_name="trips",
    )
    district = models.ForeignKey(
        District,
        on_delete=models.PROTECT,
        related_name="trips",
    )
    upazila = models.ForeignKey(
        Upazila,
        on_delete=models.PROTECT,
        related_name="trips",
    )
    spot = models.ForeignKey(
        TourSpot,
        on_delete=models.PROTECT,
        related_name="trips",
    )
    trip_source = models.CharField(
        max_length=12,
        choices=TRIP_SOURCE_CHOICES,
        default="self",
    )
    agency_name = models.CharField(max_length=180, blank=True)
    from_date = models.DateField()
    to_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    hotel_name = models.CharField(max_length=150, blank=True)
    transport_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    food_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    hotel_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    ticket_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    other_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-from_date", "-created_at"]

    def __str__(self):
        return f"{self.user} - {self.spot.name} ({self.from_date})"

    def clean(self):
        errors = {}

        if self.to_date and self.from_date and self.to_date < self.from_date:
            errors["to_date"] = "To date cannot be earlier than from date."

        if self.district_id and self.division_id and self.district.division_id != self.division_id:
            errors["district"] = "Selected district does not belong to the selected division."

        if self.upazila_id and self.district_id and self.upazila.district_id != self.district_id:
            errors["upazila"] = "Selected upazila does not belong to the selected district."

        if self.spot_id and self.upazila_id and self.spot.upazila_id != self.upazila_id:
            errors["spot"] = "Selected spot does not belong to the selected upazila."

        if self.trip_source == "agency" and not (self.agency_name or "").strip():
            errors["agency_name"] = "Agency name is required for agency trips."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.trip_source != "agency":
            self.agency_name = ""
        costs = [
            self.transport_cost or Decimal("0"),
            self.food_cost or Decimal("0"),
            self.hotel_cost or Decimal("0"),
            self.ticket_cost or Decimal("0"),
            self.other_cost or Decimal("0"),
        ]
        self.total_cost = sum(costs, Decimal("0"))
        super().save(*args, **kwargs)


class TripReminder(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="trip_reminders",
    )
    title = models.CharField(max_length=120, default="Next Trip")
    trip_source = models.CharField(
        max_length=12,
        choices=TRIP_SOURCE_CHOICES,
        default="self",
    )
    agency_name = models.CharField(max_length=180, blank=True)
    spot = models.ForeignKey(
        TourSpot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trip_reminders",
    )
    reminder_date = models.DateField()
    reminder_time = models.TimeField()
    note = models.CharField(max_length=220, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["reminder_date", "reminder_time", "-created_at"]
        indexes = [
            models.Index(fields=["user", "is_active", "reminder_date", "reminder_time"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.title} ({self.reminder_date} {self.reminder_time})"

    def clean(self):
        errors = {}
        if self.trip_source == "agency" and not (self.agency_name or "").strip():
            errors["agency_name"] = "Agency name is required for agency trips."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.trip_source != "agency":
            self.agency_name = ""
        super().save(*args, **kwargs)


class UserProfile(models.Model):
    LANGUAGE_CHOICES = [
        ("en", "English"),
        ("bn", "Bangla"),
    ]
    GENDER_CHOICES = [
        ("", "Prefer not to say"),
        ("male", "Male"),
        ("female", "Female"),
        ("other", "Other"),
    ]
    THEME_CHOICES = [
        ("light", "Light"),
        ("dark", "Dark"),
        ("night", "Night"),
    ]
    VISIBILITY_CHOICES = [
        ("private", "Private"),
        ("public", "Public"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    account_type = models.CharField(
        max_length=16,
        choices=ACCOUNT_TYPE_CHOICES,
        default="personal",
    )
    full_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    agency_name = models.CharField(max_length=180, blank=True)
    agency_license_number = models.CharField(max_length=120, blank=True)
    agency_contact_person = models.CharField(max_length=150, blank=True)
    agency_contact_phone = models.CharField(max_length=30, blank=True)
    agency_email = models.EmailField(blank=True)
    agency_address = models.TextField(blank=True)
    company_verification_status = models.CharField(
        max_length=16,
        choices=COMPANY_VERIFICATION_STATUS_CHOICES,
        default="not_required",
    )
    company_verified_at = models.DateTimeField(blank=True, null=True)
    company_verification_notes = models.TextField(blank=True)
    avatar_file = models.FileField(upload_to="avatars/", blank=True, null=True)
    cover_photo = models.FileField(upload_to="covers/", blank=True, null=True)
    avatar_url = models.URLField(blank=True)
    bio = models.TextField(blank=True)
    location = models.CharField(max_length=120, blank=True)
    website = models.URLField(blank=True)
    social_links = models.JSONField(default=list, blank=True)
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES, blank=True)
    date_of_birth = models.DateField(blank=True, null=True)
    preferred_language = models.CharField(
        max_length=12,
        choices=LANGUAGE_CHOICES,
        default="en",
    )
    theme_mode = models.CharField(
        max_length=12,
        choices=THEME_CHOICES,
        default="light",
    )
    receive_community_updates = models.BooleanField(default=True)
    public_profile = models.BooleanField(default=True)
    allow_dm = models.BooleanField(default=True)
    last_active_at = models.DateTimeField(blank=True, null=True)
    contact_visibility = models.CharField(
        max_length=12,
        choices=VISIBILITY_CHOICES,
        default="private",
    )
    default_album_visibility = models.CharField(
        max_length=12,
        choices=VISIBILITY_CHOICES,
        default="private",
    )
    default_story_visibility = models.CharField(
        max_length=12,
        choices=VISIBILITY_CHOICES,
        default="public",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self):
        return f"Profile: {self.user.username}"

    @property
    def avatar(self):
        if self.avatar_file:
            return self.avatar_file.url
        return self.avatar_url

    @property
    def is_profile_complete(self):
        return bool(
            (self.full_name or "").strip()
            and (self.phone or "").strip()
            and (self.user.email or "").strip()
        )

    @property
    def is_online(self):
        if not self.last_active_at:
            return False
        return self.last_active_at >= timezone.now() - timezone.timedelta(minutes=5)


class UserPrivacySettings(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="privacy_settings",
    )
    trip_visibility = models.CharField(
        max_length=16,
        choices=VISIBILITY_CHOICES,
        default="private",
    )
    saved_spots_visibility = models.CharField(
        max_length=16,
        choices=VISIBILITY_CHOICES,
        default="private",
    )
    history_visibility = models.CharField(
        max_length=16,
        choices=VISIBILITY_CHOICES,
        default="private",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self):
        return f"Privacy Settings: {self.user.username}"


class UserSecuritySettings(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="security_settings",
    )
    email_verified = models.BooleanField(default=False)
    recovery_email = models.EmailField(blank=True)
    recovery_phone = models.CharField(max_length=30, blank=True)
    two_factor_enabled = models.BooleanField(default=False)
    login_alerts = models.BooleanField(default=True)
    suspicious_activity_alerts = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self):
        return f"Security Settings: {self.user.username}"


class UserAppearanceSettings(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="appearance_settings",
    )
    font_size = models.CharField(
        max_length=12,
        choices=FONT_SIZE_CHOICES,
        default="md",
    )
    layout_density = models.CharField(
        max_length=16,
        choices=LAYOUT_DENSITY_CHOICES,
        default="comfortable",
    )
    map_style = models.CharField(
        max_length=16,
        choices=MAP_STYLE_CHOICES,
        default="roadmap",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self):
        return f"Appearance Settings: {self.user.username}"


class UserRegionalSettings(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="regional_settings",
    )
    timezone = models.CharField(
        max_length=64,
        choices=TIMEZONE_CHOICES,
        default="Asia/Dhaka",
    )
    date_format = models.CharField(
        max_length=16,
        choices=DATE_FORMAT_CHOICES,
        default="DD/MM/YYYY",
    )
    currency = models.CharField(
        max_length=8,
        choices=CURRENCY_CHOICES,
        default="BDT",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self):
        return f"Regional Settings: {self.user.username}"


class UserNotificationSettings(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_settings",
    )
    email_notifications = models.BooleanField(default=True)
    push_notifications = models.BooleanField(default=False)
    comment_alerts = models.BooleanField(default=True)
    like_alerts = models.BooleanField(default=True)
    follower_alerts = models.BooleanField(default=True)
    message_alerts = models.BooleanField(default=True)
    call_alerts = models.BooleanField(default=True)
    trip_reminders = models.BooleanField(default=True)
    community_updates = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self):
        return f"Notification Settings: {self.user.username}"


class UserMediaSettings(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="media_settings",
    )
    image_upload_quality = models.CharField(
        max_length=16,
        choices=IMAGE_QUALITY_CHOICES,
        default="high",
    )
    auto_image_compression = models.BooleanField(default=True)
    video_upload_limit = models.CharField(
        max_length=8,
        choices=VIDEO_UPLOAD_LIMIT_CHOICES,
        default="250",
    )
    external_storage_provider = models.CharField(
        max_length=32,
        choices=STORAGE_PROVIDER_CHOICES,
        default="none",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self):
        return f"Media Settings: {self.user.username}"


class UserCommunitySettings(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="community_settings",
    )
    who_can_message = models.CharField(
        max_length=16,
        choices=INTERACTION_CHOICES,
        default="followers",
    )
    who_can_comment = models.CharField(
        max_length=16,
        choices=INTERACTION_CHOICES,
        default="everyone",
    )
    who_can_tag = models.CharField(
        max_length=16,
        choices=INTERACTION_CHOICES,
        default="followers",
    )
    who_can_mention = models.CharField(
        max_length=16,
        choices=INTERACTION_CHOICES,
        default="everyone",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self):
        return f"Community Settings: {self.user.username}"


class UserTravelPreferences(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="travel_preferences",
    )
    default_currency = models.CharField(
        max_length=8,
        choices=CURRENCY_CHOICES,
        default="BDT",
    )
    default_trip_visibility = models.CharField(
        max_length=16,
        choices=VISIBILITY_CHOICES,
        default="private",
    )
    preferred_map_view = models.CharField(
        max_length=16,
        choices=MAP_VIEW_CHOICES,
        default="district",
    )
    distance_unit = models.CharField(
        max_length=8,
        choices=DISTANCE_UNIT_CHOICES,
        default="km",
    )
    default_expense_categories = models.JSONField(
        default=list,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self):
        return f"Travel Preferences: {self.user.username}"


class UserDataSettings(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="data_settings",
    )
    backup_enabled = models.BooleanField(default=False)
    export_format = models.CharField(
        max_length=12,
        choices=EXPORT_FORMAT_CHOICES,
        default="zip",
    )
    include_media_in_exports = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self):
        return f"Data Settings: {self.user.username}"


class SettingsAuditLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="settings_audit_logs",
    )
    section = models.CharField(max_length=32)
    action = models.CharField(max_length=64)
    changed_fields = models.JSONField(default=list, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} - {self.section} - {self.action}"


class Album(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="albums",
    )
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    trip_date = models.DateField()
    spot = models.ForeignKey(
        TourSpot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="albums",
    )
    external_source = models.CharField(
        max_length=120,
        blank=True,
        help_text="Optional source like Google Photos",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-trip_date", "-created_at"]

    def __str__(self):
        return f"{self.title} ({self.user.username})"


class AlbumItem(models.Model):
    album = models.ForeignKey(
        Album,
        on_delete=models.CASCADE,
        related_name="items",
    )
    file = models.FileField(upload_to="album_items/", blank=True, null=True)
    external_url = models.URLField(blank=True)
    caption = models.CharField(max_length=220, blank=True)
    taken_at = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-taken_at", "-created_at"]

    def __str__(self):
        return f"AlbumItem #{self.id} - {self.album.title}"

    def clean(self):
        if not self.file and not self.external_url:
            raise ValidationError("Upload a file or provide an external photo URL.")


class Story(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="stories",
    )
    title = models.CharField(max_length=180)
    content = models.TextField()
    trip_date = models.DateField()
    spot = models.ForeignKey(
        TourSpot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stories",
    )
    cover_file = models.FileField(upload_to="stories/covers/", blank=True, null=True)
    snap_url = models.URLField(blank=True)
    is_public = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-trip_date", "-created_at"]

    def __str__(self):
        return f"{self.title} ({self.user.username})"


class TravelHistory(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="travel_histories",
    )
    title = models.CharField(max_length=180)
    place_name = models.CharField(max_length=180)
    visit_date = models.DateField()
    short_note = models.CharField(max_length=220)
    history_note = models.TextField(
        help_text="Write useful historical background and traveler guidance."
    )
    reference_link = models.URLField(blank=True)
    photo = models.FileField(upload_to="history/photos/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-visit_date", "-created_at"]

    def __str__(self):
        return f"{self.title} ({self.user.username})"


class SavedSpot(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_spots",
    )
    spot = models.ForeignKey(
        TourSpot,
        on_delete=models.CASCADE,
        related_name="saved_by_users",
    )
    note = models.CharField(max_length=220, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "spot"],
                name="uniq_saved_spot_per_user",
            )
        ]

    def __str__(self):
        return f"{self.user.username} saved {self.spot.name}"


class CommunityTag(models.Model):
    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=60, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @staticmethod
    def normalize_name(value):
        token = (value or "").strip().lower()
        if not token:
            return ""
        token = token.lstrip("#").replace(" ", "_")
        return f"#{token}"

    def save(self, *args, **kwargs):
        self.name = self.normalize_name(self.name)
        if not self.slug:
            self.slug = slugify(self.name.lstrip("#"))[:60] or "tag"
        super().save(*args, **kwargs)


class CommunityPost(models.Model):
    CANONICAL_POST_TYPE_CHOICES = [
        ("discussion", "Discussion"),
        ("help", "Help & Questions"),
        ("trip_planning", "Trip Planning"),
        ("budget_travel", "Budget Travel"),
        ("hotels_stay", "Hotels & Stay"),
        ("transport_advice", "Transport Advice"),
        ("travel_guide", "Travel Guide"),
    ]
    LEGACY_POST_TYPE_CHOICES = [
        ("travel_question", "Travel Question"),
        ("travel_experience", "Travel Experience"),
        ("budget_help", "Budget Help"),
        ("hotel_recommendation", "Hotel Recommendation"),
        ("trip_plan", "Trip Plan"),
        ("travel_warning", "Travel Warning"),
        ("lost_found", "Lost & Found"),
    ]
    POST_TYPE_CHOICES = CANONICAL_POST_TYPE_CHOICES + LEGACY_POST_TYPE_CHOICES

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="community_posts",
    )
    post_type = models.CharField(
        max_length=40,
        choices=POST_TYPE_CHOICES,
        default="discussion",
    )
    title = models.CharField(max_length=180)
    content = models.TextField(blank=True)
    district = models.ForeignKey(
        District,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="community_posts",
    )
    spot = models.ForeignKey(
        TourSpot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="community_posts",
    )
    location_name = models.CharField(max_length=180, blank=True)
    hashtags = models.CharField(
        max_length=280,
        blank=True,
        help_text="Comma separated hashtags, e.g. #sylhet,#budget",
    )
    tags = models.ManyToManyField(
        CommunityTag,
        blank=True,
        related_name="posts",
    )
    poll_question = models.CharField(max_length=220, blank=True)
    poll_options = models.TextField(
        blank=True,
        help_text="One option per line.",
    )
    image_file = models.FileField(upload_to="community/posts/images/", blank=True, null=True)
    audio_file = models.FileField(upload_to="community/posts/audio/", blank=True, null=True)
    video_file = models.FileField(upload_to="community/posts/video/", blank=True, null=True)
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.user.username})"

    def clean(self):
        has_media = any([self.image_file, self.audio_file, self.video_file])
        has_poll = bool(self.poll_question and self.poll_options.strip())
        if not self.content and not has_media and not has_poll:
            raise ValidationError("Write text or upload at least one media file.")

    @property
    def hashtags_list(self):
        tokens = []
        seen = set()
        for tag in self.hashtags.split(","):
            normalized = CommunityTag.normalize_name(tag)
            if normalized and normalized not in seen:
                seen.add(normalized)
                tokens.append(normalized)
        return tokens

    @property
    def has_media(self):
        return bool(self.image_file or self.audio_file or self.video_file or self.media_items.exists())

    def save(self, *args, **kwargs):
        self.hashtags = ", ".join(self.hashtags_list)
        super().save(*args, **kwargs)
        self.sync_tags()
        self.sync_inline_media()

    def sync_tags(self):
        if not self.pk:
            return
        tags = []
        for token in self.hashtags_list:
            slug = slugify(token.lstrip("#"))[:60] or "tag"
            tag, _ = CommunityTag.objects.get_or_create(
                slug=slug,
                defaults={"name": token},
            )
            if tag.name != token:
                tag.name = token
                tag.save(update_fields=["name"])
            tags.append(tag)
        self.tags.set(tags)

    def sync_inline_media(self):
        if not self.pk:
            return

        inline_media = {
            "image": self.image_file,
            "audio": self.audio_file,
            "video": self.video_file,
        }
        for media_type, file_field in inline_media.items():
            defaults = {
                "caption": self.title,
                "sort_order": 0,
                "external_url": "",
                "file": file_field,
            }
            if file_field:
                CommunityPostMedia.objects.update_or_create(
                    post=self,
                    source="inline",
                    media_type=media_type,
                    sort_order=0,
                    defaults=defaults,
                )
            else:
                CommunityPostMedia.objects.filter(
                    post=self,
                    source="inline",
                    media_type=media_type,
                ).delete()


class CommunityPostMedia(models.Model):
    MEDIA_TYPE_CHOICES = [
        ("image", "Image"),
        ("video", "Video"),
        ("audio", "Audio"),
    ]
    SOURCE_CHOICES = [
        ("attachment", "Attachment"),
        ("inline", "Inline Post Field"),
    ]

    post = models.ForeignKey(
        CommunityPost,
        on_delete=models.CASCADE,
        related_name="media_items",
    )
    media_type = models.CharField(max_length=16, choices=MEDIA_TYPE_CHOICES)
    file = models.FileField(upload_to="community/posts/attachments/", blank=True, null=True)
    external_url = models.URLField(blank=True)
    caption = models.CharField(max_length=220, blank=True)
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES, default="attachment")
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["post", "source", "media_type", "sort_order"],
                name="uniq_community_post_media_slot",
            )
        ]

    def __str__(self):
        return f"{self.post.title} - {self.media_type}"

    def clean(self):
        if not self.file and not self.external_url:
            raise ValidationError("Upload a file or provide an external media URL.")

    @property
    def preview_url(self):
        if self.file:
            return self.file.url
        return self.external_url


class CommunityPostView(models.Model):
    post = models.ForeignKey(
        CommunityPost,
        on_delete=models.CASCADE,
        related_name="views",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="community_post_views",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["post", "user"],
                name="uniq_community_post_view_per_user",
            )
        ]

    def __str__(self):
        return f"{self.user.username} viewed post {self.post_id}"


class CommunityComment(models.Model):
    post = models.ForeignKey(
        CommunityPost,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="community_comments",
    )
    content = models.TextField(blank=True)
    image_file = models.FileField(upload_to="community/comments/images/", blank=True, null=True)
    audio_file = models.FileField(upload_to="community/comments/audio/", blank=True, null=True)
    video_file = models.FileField(upload_to="community/comments/video/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    edited_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment #{self.id} on {self.post_id}"

    def clean(self):
        if not self.content and not any([self.image_file, self.audio_file, self.video_file]):
            raise ValidationError("Comment needs text or media.")

    @property
    def is_edited(self):
        return bool(self.edited_at)


class CommunityCommentEditHistory(models.Model):
    comment = models.ForeignKey(
        CommunityComment,
        on_delete=models.CASCADE,
        related_name="history_entries",
    )
    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="community_comment_histories",
    )
    previous_content = models.TextField(blank=True)
    previous_image_file = models.FileField(blank=True, null=True, upload_to="community/comments/images/")
    previous_audio_file = models.FileField(blank=True, null=True, upload_to="community/comments/audio/")
    previous_video_file = models.FileField(blank=True, null=True, upload_to="community/comments/video/")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Comment history #{self.id} for comment {self.comment_id}"


class CommunityPostReaction(models.Model):
    REACTION_CHOICES = [
        ("like", "Like"),
        ("love", "Love"),
        ("care", "Care"),
        ("wow", "Wow"),
        ("helpful", "Helpful"),
    ]

    post = models.ForeignKey(
        CommunityPost,
        on_delete=models.CASCADE,
        related_name="reactions",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="community_reactions",
    )
    reaction = models.CharField(max_length=20, choices=REACTION_CHOICES, default="like")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["post", "user"],
                name="uniq_post_reaction_per_user",
            )
        ]

    def __str__(self):
        return f"{self.user} reacted on post {self.post_id}"


class CommunityPostSave(models.Model):
    post = models.ForeignKey(
        CommunityPost,
        on_delete=models.CASCADE,
        related_name="saves",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="community_saved_posts",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["post", "user"],
                name="uniq_saved_post_per_user",
            )
        ]

    def __str__(self):
        return f"{self.user} saved post {self.post_id}"


class CommunityNotification(models.Model):
    NOTIFICATION_CHOICES = [
        ("post_reply", "Post Reply"),
        ("comment", "Comment"),
        ("mention", "Mention"),
        ("answer", "Answer"),
        ("like", "Like"),
        ("follow", "Follow"),
        ("direct_message", "Direct Message"),
        ("call", "Call"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="community_notifications",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="community_notifications_sent",
    )
    post = models.ForeignKey(
        CommunityPost,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    conversation = models.ForeignKey(
        "Conversation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    kind = models.CharField(max_length=20, choices=NOTIFICATION_CHOICES)
    message = models.CharField(max_length=240)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} - {self.kind}"


class CommunityMembership(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="community_membership",
    )
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-joined_at"]

    def __str__(self):
        return f"{self.user.username} community member"


class UserFollow(models.Model):
    follower = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="following_links",
    )
    following = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="follower_links",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["follower", "following"],
                name="uniq_user_follow_pair",
            )
        ]

    def __str__(self):
        return f"{self.follower.username} follows {self.following.username}"

    def clean(self):
        if self.follower_id and self.following_id and self.follower_id == self.following_id:
            raise ValidationError("Users cannot follow themselves.")


class Conversation(models.Model):
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="conversations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-created_at"]

    def __str__(self):
        participant_names = ", ".join(
            self.participants.order_by("username").values_list("username", flat=True)[:3]
        )
        return f"Conversation #{self.id}: {participant_names or 'pending'}"

    def other_participant(self, user):
        return self.participants.exclude(id=user.id).first()


class CallSession(models.Model):
    MODE_CHOICES = [
        ("audio", "Audio"),
        ("video", "Video"),
    ]
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("declined", "Declined"),
        ("ended", "Ended"),
    ]

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="call_sessions",
    )
    initiator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="initiated_call_sessions",
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_call_sessions",
    )
    mode = models.CharField(max_length=8, choices=MODE_CHOICES, default="audio")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    room_name = models.SlugField(max_length=120, unique=True, blank=True)
    responded_at = models.DateTimeField(blank=True, null=True)
    ended_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_mode_display()} call #{self.id} in conversation {self.conversation_id}"

    def clean(self):
        if self.initiator_id and self.recipient_id and self.initiator_id == self.recipient_id:
            raise ValidationError("Call participants must be different users.")
        if self.conversation_id:
            participant_ids = set(self.conversation.participants.values_list("id", flat=True))
            if self.initiator_id and self.initiator_id not in participant_ids:
                raise ValidationError("Call initiator must belong to the conversation.")
            if self.recipient_id and self.recipient_id not in participant_ids:
                raise ValidationError("Call recipient must belong to the conversation.")

    def save(self, *args, **kwargs):
        if not self.room_name and self.conversation_id and self.initiator_id and self.recipient_id:
            timestamp = timezone.now().strftime("%Y%m%d%H%M%S%f")
            self.room_name = slugify(
                f"tour-point-{self.conversation_id}-{self.mode}-{self.initiator_id}-{self.recipient_id}-{timestamp}"
            )[:120]
        super().save(*args, **kwargs)

    def other_participant(self, user):
        if user.id == self.initiator_id:
            return self.recipient
        return self.initiator


class Message(models.Model):
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="messages_sent",
    )
    content = models.TextField(blank=True)
    is_read = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    edited_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Message #{self.id} in conversation {self.conversation_id}"

    def clean(self):
        content = (self.content or "").strip()
        has_attachments = bool(
            getattr(self, "_has_pending_attachment", False)
            or (self.pk and self.attachments.exists())
        )
        if not content and not has_attachments:
            raise ValidationError("Message needs text or an attachment.")
        if self.conversation_id and not self.conversation.participants.filter(id=self.sender_id).exists():
            raise ValidationError("Sender must belong to the conversation.")


class MessageAttachment(models.Model):
    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(
        upload_to="chat/",
        validators=[validate_album_media_upload],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Attachment #{self.id} for message {self.message_id}"

    @property
    def file_extension(self):
        return (self.file.name.rsplit(".", 1)[-1] if "." in (self.file.name or "") else "").lower()

    @property
    def kind(self):
        extension = self.file_extension
        if extension in {"jpg", "jpeg", "png", "webp", "gif"}:
            return "image"
        if extension in {"mp4", "webm", "mov"}:
            return "video"
        if extension in {"mp3", "wav", "ogg", "m4a"}:
            return "audio"
        return "file"


class DirectConversation(models.Model):
    user_one = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="direct_conversations_as_user_one",
    )
    user_two = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="direct_conversations_as_user_two",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user_one", "user_two"],
                name="uniq_direct_conversation_pair",
            )
        ]

    def __str__(self):
        return f"{self.user_one.username} <-> {self.user_two.username}"

    def clean(self):
        if self.user_one_id and self.user_two_id and self.user_one_id == self.user_two_id:
            raise ValidationError("Conversation participants must be different users.")

    def save(self, *args, **kwargs):
        if self.user_one_id and self.user_two_id and self.user_one_id > self.user_two_id:
            self.user_one_id, self.user_two_id = self.user_two_id, self.user_one_id
        super().save(*args, **kwargs)

    def other_user(self, user):
        if user.id == self.user_one_id:
            return self.user_two
        return self.user_one


class DirectMessage(models.Model):
    conversation = models.ForeignKey(
        DirectConversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="direct_messages_sent",
    )
    body = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Message #{self.id} in conversation {self.conversation_id}"

    def clean(self):
        if not (self.body or "").strip():
            raise ValidationError("Message body cannot be empty.")
        if self.conversation_id and self.sender_id not in {
            self.conversation.user_one_id,
            self.conversation.user_two_id,
        }:
            raise ValidationError("Sender must be part of the conversation.")


@receiver(post_save, sender=get_user_model())
def ensure_profile_exists(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)
    else:
        UserProfile.objects.get_or_create(user=instance)
    UserPrivacySettings.objects.get_or_create(user=instance)
    UserSecuritySettings.objects.get_or_create(user=instance)
    UserAppearanceSettings.objects.get_or_create(user=instance)
    UserRegionalSettings.objects.get_or_create(user=instance)
    UserNotificationSettings.objects.get_or_create(user=instance)
    UserMediaSettings.objects.get_or_create(user=instance)
    UserCommunitySettings.objects.get_or_create(user=instance)
    UserTravelPreferences.objects.get_or_create(user=instance)
    UserDataSettings.objects.get_or_create(user=instance)
