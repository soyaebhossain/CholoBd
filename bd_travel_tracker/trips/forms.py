from datetime import datetime

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone

from .models import (
    Album,
    AlbumItem,
    CommunityComment,
    CommunityPost,
    District,
    Division,
    Message,
    SavedSpot,
    Story,
    TourSpot,
    TravelHistory,
    Trip,
    TripReminder,
    Upazila,
    UserProfile,
)
from .validators import (
    AUDIO_EXTENSIONS,
    AUDIO_MAX_BYTES,
    AVATAR_MAX_BYTES,
    IMAGE_EXTENSIONS,
    IMAGE_MAX_BYTES,
    VIDEO_EXTENSIONS,
    VIDEO_MAX_BYTES,
    validate_album_media_upload,
    validate_upload,
)


def _validate_profile_media(cleaned_data):
    validate_upload(
        cleaned_data.get("avatar_file"),
        allowed_extensions=IMAGE_EXTENSIONS,
        max_size_bytes=AVATAR_MAX_BYTES,
        label="Avatar",
    )
    validate_upload(
        cleaned_data.get("cover_photo"),
        allowed_extensions=IMAGE_EXTENSIONS,
        max_size_bytes=IMAGE_MAX_BYTES,
        label="Cover photo",
    )
    return cleaned_data


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=False)
    account_type = forms.ChoiceField(
        choices=UserProfile._meta.get_field("account_type").choices,
        initial="personal",
    )
    agency_name = forms.CharField(required=False, max_length=180)
    agency_license_number = forms.CharField(required=False, max_length=120)
    agency_contact_person = forms.CharField(required=False, max_length=150)
    agency_contact_phone = forms.CharField(required=False, max_length=30)
    agency_email = forms.EmailField(required=False)
    agency_address = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        self.fields["account_type"].widget.attrs["class"] = "form-select"
        self.fields["agency_name"].widget.attrs.setdefault("placeholder", "Agency or company name")
        self.fields["agency_license_number"].widget.attrs.setdefault(
            "placeholder",
            "Trade license / registration no.",
        )
        self.fields["agency_contact_person"].widget.attrs.setdefault(
            "placeholder",
            "Authorized contact person",
        )
        self.fields["agency_contact_phone"].widget.attrs.setdefault(
            "placeholder",
            "Official agency phone",
        )
        self.fields["agency_email"].widget.attrs.setdefault("placeholder", "agency@example.com")
        self.fields["agency_address"].widget.attrs.setdefault("placeholder", "Registered office address")

    def clean(self):
        cleaned_data = super().clean()
        account_type = cleaned_data.get("account_type")
        if account_type != "company":
            return cleaned_data

        required_fields = [
            "email",
            "agency_name",
            "agency_license_number",
            "agency_contact_person",
            "agency_contact_phone",
            "agency_email",
            "agency_address",
        ]
        for field_name in required_fields:
            value = cleaned_data.get(field_name)
            if isinstance(value, str):
                value = value.strip()
            if not value:
                self.add_error(field_name, "This field is required for company accounts.")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data.get("email", "")

        if self.cleaned_data.get("account_type") == "company":
            user.is_active = False

        if commit:
            user.save()
            profile = user.profile
            profile.account_type = self.cleaned_data.get("account_type", "personal")
            profile.agency_name = self.cleaned_data.get("agency_name", "").strip()
            profile.agency_license_number = self.cleaned_data.get("agency_license_number", "").strip()
            profile.agency_contact_person = self.cleaned_data.get("agency_contact_person", "").strip()
            profile.agency_contact_phone = self.cleaned_data.get("agency_contact_phone", "").strip()
            profile.agency_email = self.cleaned_data.get("agency_email", "").strip()
            profile.agency_address = self.cleaned_data.get("agency_address", "").strip()
            if profile.account_type == "company":
                profile.company_verification_status = "pending"
                profile.company_verified_at = None
            else:
                profile.company_verification_status = "not_required"
                profile.company_verified_at = None
                profile.company_verification_notes = ""
            profile.save(
                update_fields=[
                    "account_type",
                    "agency_name",
                    "agency_license_number",
                    "agency_contact_person",
                    "agency_contact_phone",
                    "agency_email",
                    "agency_address",
                    "company_verification_status",
                    "company_verified_at",
                    "company_verification_notes",
                ]
            )
        return user


class MessageForm(forms.ModelForm):
    attachment = forms.FileField(required=False)

    class Meta:
        model = Message
        fields = ("content",)
        widgets = {
            "content": forms.Textarea(
                attrs={
                    "rows": 2,
                    "placeholder": "Aa",
                    "class": "form-control message-composer-textarea",
                    "data-message-composer": "true",
                    "autocomplete": "off",
                    "spellcheck": "true",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["content"].widget.attrs.update(
            {
                "class": "form-control message-composer-textarea",
                "data-message-composer": "true",
                "autocomplete": "off",
                "spellcheck": "true",
            }
        )
        self.fields["attachment"].widget.attrs.update(
            {
                "class": "message-attachment-input",
                "accept": "image/*,video/*,audio/*,.jpg,.jpeg,.png,.webp,.gif,.mp4,.webm,.mov,.mp3,.wav,.ogg,.m4a",
                "data-message-attachment": "true",
            }
        )

    def clean_attachment(self):
        attachment = self.cleaned_data.get("attachment")
        validate_album_media_upload(attachment, label="Message attachment")
        return attachment

    def clean(self):
        cleaned_data = super().clean()
        content = (cleaned_data.get("content") or "").strip()
        attachment = cleaned_data.get("attachment")
        if not content and not attachment:
            raise forms.ValidationError("Write a message or attach a file before sending.")
        cleaned_data["content"] = content
        self.instance._has_pending_attachment = bool(attachment)
        return cleaned_data


class TripForm(forms.ModelForm):
    class Meta:
        model = Trip
        fields = (
            "division",
            "district",
            "upazila",
            "spot",
            "trip_source",
            "agency_name",
            "from_date",
            "to_date",
            "notes",
            "hotel_name",
            "transport_cost",
            "food_cost",
            "hotel_cost",
            "ticket_cost",
            "other_cost",
        )
        widgets = {
            "from_date": forms.DateInput(attrs={"type": "date"}),
            "to_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["division"].queryset = Division.objects.order_by("name")
        self.fields["district"].queryset = District.objects.none()
        self.fields["upazila"].queryset = Upazila.objects.none()
        self.fields["spot"].queryset = TourSpot.objects.none()

        self.fields["to_date"].required = False
        self.fields["notes"].required = False
        self.fields["hotel_name"].required = False
        self.fields["trip_source"].required = False
        self.fields["agency_name"].required = False
        self.fields["trip_source"].widget.attrs.setdefault("data-trip-source-field", "true")
        self.fields["agency_name"].widget.attrs.setdefault("placeholder", "Agency name")
        self.fields["agency_name"].widget.attrs.setdefault("data-agency-name-field", "true")

        for field_name, field in self.fields.items():
            css_class = "form-control"
            if isinstance(field.widget, forms.Select):
                css_class = "form-select"
            if isinstance(field.widget, forms.Textarea):
                css_class = "form-control"
            field.widget.attrs.setdefault("class", css_class)

        for money_field in [
            "transport_cost",
            "food_cost",
            "hotel_cost",
            "ticket_cost",
            "other_cost",
        ]:
            self.fields[money_field].widget.attrs["min"] = "0"
            self.fields[money_field].widget.attrs["step"] = "0.01"

        division_id = self._selected_id("division")
        district_id = self._selected_id("district")
        upazila_id = self._selected_id("upazila")

        if division_id:
            self.fields["district"].queryset = District.objects.filter(
                division_id=division_id
            ).order_by("name")

        if district_id:
            self.fields["upazila"].queryset = Upazila.objects.filter(
                district_id=district_id
            ).order_by("name")

        if upazila_id:
            self.fields["spot"].queryset = TourSpot.objects.filter(
                upazila_id=upazila_id
            ).order_by("name")

    def _selected_id(self, field_name):
        if self.is_bound:
            value = self.data.get(field_name)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
            return None

        if self.instance.pk:
            return getattr(self.instance, f"{field_name}_id", None)

        initial_value = self.initial.get(field_name)
        if hasattr(initial_value, "pk"):
            return initial_value.pk
        if isinstance(initial_value, int):
            return initial_value
        return None

    def clean(self):
        cleaned_data = super().clean()

        division = cleaned_data.get("division")
        district = cleaned_data.get("district")
        upazila = cleaned_data.get("upazila")
        spot = cleaned_data.get("spot")
        trip_source = cleaned_data.get("trip_source") or "self"
        from_date = cleaned_data.get("from_date")
        to_date = cleaned_data.get("to_date")
        cleaned_data["trip_source"] = trip_source

        if to_date and from_date and to_date < from_date:
            self.add_error("to_date", "To date cannot be earlier than from date.")

        if division and district and district.division_id != division.id:
            self.add_error("district", "District does not match selected division.")

        if district and upazila and upazila.district_id != district.id:
            self.add_error("upazila", "Upazila does not match selected district.")

        if upazila and spot and spot.upazila_id != upazila.id:
            self.add_error("spot", "Spot does not match selected upazila.")

        if trip_source == "agency" and not (
            cleaned_data.get("agency_name") or ""
        ).strip():
            self.add_error("agency_name", "Agency name is required for agency trips.")

        return cleaned_data


class TripReminderForm(forms.ModelForm):
    division = forms.ModelChoiceField(
        queryset=Division.objects.order_by("name"),
        required=False,
    )
    district = forms.ModelChoiceField(
        queryset=District.objects.none(),
        required=False,
    )
    upazila = forms.ModelChoiceField(
        queryset=Upazila.objects.none(),
        required=False,
    )

    class Meta:
        model = TripReminder
        fields = (
            "title",
            "trip_source",
            "agency_name",
            "spot",
            "reminder_date",
            "reminder_time",
            "note",
        )
        widgets = {
            "reminder_date": forms.DateInput(attrs={"type": "date"}),
            "reminder_time": forms.TimeInput(attrs={"type": "time"}),
            "note": forms.TextInput(attrs={"placeholder": "Optional note"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["spot"].queryset = TourSpot.objects.none()
        self.fields["division"].label = "Division"
        self.fields["district"].label = "District"
        self.fields["upazila"].label = "Upazila"
        self.fields["spot"].label = "Destination spot"
        self.fields["trip_source"].label = "Trip source"
        self.fields["agency_name"].label = "Agency name"
        self.fields["division"].widget.attrs.setdefault("autocomplete", "off")
        self.fields["district"].widget.attrs.setdefault("autocomplete", "off")
        self.fields["upazila"].widget.attrs.setdefault("autocomplete", "off")
        self.fields["spot"].widget.attrs.setdefault("autocomplete", "off")
        self.fields["trip_source"].required = False
        self.fields["agency_name"].required = False

        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select")
            else:
                field.widget.attrs.setdefault("class", "form-control")
        self.fields["title"].widget.attrs.setdefault("placeholder", "Next Trip")
        self.fields["spot"].widget.attrs.setdefault("data-route-destination", "true")
        self.fields["trip_source"].widget.attrs.setdefault("data-trip-source-field", "true")
        self.fields["agency_name"].widget.attrs.setdefault("placeholder", "Agency name")
        self.fields["agency_name"].widget.attrs.setdefault("data-agency-name-field", "true")

        division_id = self._selected_id("division")
        district_id = self._selected_id("district")
        upazila_id = self._selected_id("upazila")
        spot_id = self._selected_id("spot")

        if division_id:
            self.fields["district"].queryset = District.objects.filter(
                division_id=division_id
            ).order_by("name")

        if district_id:
            self.fields["upazila"].queryset = Upazila.objects.filter(
                district_id=district_id
            ).order_by("name")

        if upazila_id:
            self.fields["spot"].queryset = TourSpot.objects.filter(
                upazila_id=upazila_id
            ).order_by("name")
        elif spot_id:
            self.fields["spot"].queryset = TourSpot.objects.filter(id=spot_id)

        if not self.is_bound and self.instance.pk and self.instance.spot_id:
            self.fields["division"].initial = self.instance.spot.division.pk
            self.fields["district"].initial = self.instance.spot.district.pk
            self.fields["upazila"].initial = self.instance.spot.upazila_id

        self.order_fields(
            [
                "title",
                "trip_source",
                "agency_name",
                "division",
                "district",
                "upazila",
                "spot",
                "reminder_date",
                "reminder_time",
                "note",
            ]
        )

    def _selected_id(self, field_name):
        if self.is_bound:
            value = self.data.get(field_name)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
            return None

        initial_value = self.initial.get(field_name)
        if hasattr(initial_value, "pk"):
            return initial_value.pk
        if isinstance(initial_value, int):
            return initial_value

        if not self.instance.pk:
            return None

        if field_name == "division" and self.instance.spot_id:
            return self.instance.spot.division.pk
        if field_name == "district" and self.instance.spot_id:
            return self.instance.spot.district.pk
        if field_name == "upazila" and self.instance.spot_id:
            return self.instance.spot.upazila_id
        return getattr(self.instance, f"{field_name}_id", None)

    def clean(self):
        cleaned_data = super().clean()
        division = cleaned_data.get("division")
        district = cleaned_data.get("district")
        upazila = cleaned_data.get("upazila")
        spot = cleaned_data.get("spot")
        trip_source = cleaned_data.get("trip_source") or "self"
        reminder_date = cleaned_data.get("reminder_date")
        reminder_time = cleaned_data.get("reminder_time")
        cleaned_data["trip_source"] = trip_source

        if division and district and district.division_id != division.id:
            self.add_error("district", "District does not match selected division.")

        if district and upazila and upazila.district_id != district.id:
            self.add_error("upazila", "Upazila does not match selected district.")

        if upazila and spot and spot.upazila_id != upazila.id:
            self.add_error("spot", "Destination spot does not match selected upazila.")

        if any([division, district, upazila]) and not spot:
            self.add_error("spot", "Select a destination spot to enable route tracking.")

        if trip_source == "agency" and not (
            cleaned_data.get("agency_name") or ""
        ).strip():
            self.add_error("agency_name", "Agency name is required for agency trips.")

        if not reminder_date or not reminder_time:
            return cleaned_data

        local_now = timezone.localtime()
        reminder_datetime = timezone.make_aware(
            datetime.combine(reminder_date, reminder_time),
            timezone.get_current_timezone(),
        )
        if reminder_datetime <= local_now:
            self.add_error("reminder_time", "Please choose a future date and time.")
        return cleaned_data


class UserProfileForm(forms.ModelForm):
    email = forms.EmailField(required=False)

    class Meta:
        model = UserProfile
        fields = (
            "full_name",
            "phone",
            "avatar_file",
            "cover_photo",
            "avatar_url",
            "bio",
            "location",
            "website",
            "gender",
            "date_of_birth",
            "preferred_language",
            "theme_mode",
            "receive_community_updates",
            "public_profile",
            "allow_dm",
            "contact_visibility",
            "default_album_visibility",
            "default_story_visibility",
        )
        widgets = {
            "bio": forms.Textarea(attrs={"rows": 4}),
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        self.enforce_required = kwargs.pop("enforce_required", False)
        super().__init__(*args, **kwargs)
        if self.user:
            self.fields["email"].initial = self.user.email

        self.fields["gender"].choices = [
            ("", "◎ Prefer not to say"),
            ("male", "♂ Male"),
            ("female", "♀ Female"),
            ("other", "⚧ Other"),
        ]

        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select")
            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs.setdefault("class", "form-control")
            else:
                field.widget.attrs.setdefault("class", "form-control")

        self.fields["email"].widget.attrs.setdefault("class", "form-control")
        self.fields["full_name"].widget.attrs.setdefault("placeholder", "Your full name")
        self.fields["phone"].widget.attrs.setdefault("placeholder", "01XXXXXXXXX")
        self.fields["location"].widget.attrs.setdefault("placeholder", "City or region")
        self.fields["website"].widget.attrs.setdefault("placeholder", "https://your-site.com")
        self.fields["avatar_url"].widget.attrs.setdefault("placeholder", "https://example.com/avatar.jpg")
        self.fields["bio"].widget.attrs.setdefault(
            "placeholder",
            "Share your travel style, favorite routes, or what people can expect from your profile.",
        )
        self.fields["avatar_file"].widget.attrs.setdefault("accept", "image/*")
        self.fields["cover_photo"].widget.attrs.setdefault("accept", "image/*")

        if self.enforce_required:
            self.fields["full_name"].required = True
            self.fields["phone"].required = True
            self.fields["email"].required = True

    def save(self, commit=True):
        profile = super().save(commit=commit)
        if self.user is not None:
            self.user.email = self.cleaned_data.get("email", "")
            if commit:
                self.user.save(update_fields=["email"])
        return profile

    def clean(self):
        cleaned_data = super().clean()
        return _validate_profile_media(cleaned_data)


class ProfileAvatarUploadForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ("avatar_file",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["avatar_file"].widget.attrs.update(
            {
                "class": "visually-hidden profile-media-input",
                "accept": "image/*",
                "data-upload-label": "avatar",
            }
        )

    def clean(self):
        cleaned_data = super().clean()
        avatar_file = cleaned_data.get("avatar_file")
        if not avatar_file:
            raise forms.ValidationError("Select an avatar image to upload.")
        validate_upload(
            avatar_file,
            allowed_extensions=IMAGE_EXTENSIONS,
            max_size_bytes=AVATAR_MAX_BYTES,
            label="Avatar",
        )
        return cleaned_data


class ProfileCoverUploadForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ("cover_photo",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cover_photo"].widget.attrs.update(
            {
                "class": "visually-hidden profile-media-input",
                "accept": "image/*",
                "data-upload-label": "cover photo",
            }
        )

    def clean(self):
        cleaned_data = super().clean()
        cover_photo = cleaned_data.get("cover_photo")
        if not cover_photo:
            raise forms.ValidationError("Select a cover image to upload.")
        validate_upload(
            cover_photo,
            allowed_extensions=IMAGE_EXTENSIONS,
            max_size_bytes=IMAGE_MAX_BYTES,
            label="Cover photo",
        )
        return cleaned_data


class ProfileSettingsForm(forms.ModelForm):
    email = forms.EmailField(required=False)

    class Meta:
        model = UserProfile
        fields = (
            "preferred_language",
            "theme_mode",
            "receive_community_updates",
            "public_profile",
            "allow_dm",
        )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if self.user:
            self.fields["email"].initial = self.user.email

        self.fields["email"].widget.attrs.setdefault("class", "form-control")
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            else:
                field.widget.attrs.setdefault("class", "form-select")

    def save(self, commit=True):
        profile = super().save(commit=commit)
        if self.user is not None:
            self.user.email = self.cleaned_data.get("email", "")
            if commit:
                self.user.save(update_fields=["email"])
        return profile


class AlbumForm(forms.ModelForm):
    class Meta:
        model = Album
        fields = ("title", "description", "trip_date", "spot", "external_source")
        widgets = {
            "trip_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["spot"].required = False
        self.fields["spot"].queryset = TourSpot.objects.order_by("name")
        for field in self.fields.values():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select")
            else:
                field.widget.attrs.setdefault("class", "form-control")


class AlbumItemForm(forms.ModelForm):
    class Meta:
        model = AlbumItem
        fields = ("file", "external_url", "caption", "taken_at")
        widgets = {
            "taken_at": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.DateInput):
                field.widget.attrs.setdefault("class", "form-control")
            else:
                field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("file") and not cleaned_data.get("external_url"):
            raise forms.ValidationError("Upload a file or provide an external photo URL.")
        validate_album_media_upload(cleaned_data.get("file"))
        return cleaned_data


class StoryForm(forms.ModelForm):
    class Meta:
        model = Story
        fields = (
            "title",
            "content",
            "trip_date",
            "spot",
            "cover_file",
            "snap_url",
            "is_public",
        )
        widgets = {
            "content": forms.Textarea(attrs={"rows": 4}),
            "trip_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["spot"].required = False
        self.fields["spot"].queryset = TourSpot.objects.order_by("name")
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select")
            else:
                field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        cleaned_data = super().clean()
        validate_upload(
            cleaned_data.get("cover_file"),
            allowed_extensions=IMAGE_EXTENSIONS,
            max_size_bytes=IMAGE_MAX_BYTES,
            label="Story cover",
        )
        return cleaned_data


class TravelHistoryForm(forms.ModelForm):
    class Meta:
        model = TravelHistory
        fields = (
            "title",
            "place_name",
            "visit_date",
            "short_note",
            "history_note",
            "reference_link",
            "photo",
        )
        widgets = {
            "visit_date": forms.DateInput(attrs={"type": "date"}),
            "history_note": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        cleaned_data = super().clean()
        validate_upload(
            cleaned_data.get("photo"),
            allowed_extensions=IMAGE_EXTENSIONS,
            max_size_bytes=IMAGE_MAX_BYTES,
            label="History photo",
        )
        return cleaned_data


class SavedSpotForm(forms.ModelForm):
    class Meta:
        model = SavedSpot
        fields = ("spot", "note")
        widgets = {
            "note": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["spot"].queryset = TourSpot.objects.order_by("name")
        for field in self.fields.values():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select")
            else:
                field.widget.attrs.setdefault("class", "form-control")


class CommunityPostForm(forms.ModelForm):
    class Meta:
        model = CommunityPost
        fields = (
            "post_type",
            "title",
            "content",
            "district",
            "spot",
            "location_name",
            "hashtags",
            "poll_question",
            "poll_options",
            "image_file",
            "audio_file",
            "video_file",
            "is_resolved",
        )
        widgets = {
            "content": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Write something about your travel...",
                }
            ),
            "hashtags": forms.TextInput(
                attrs={
                    "placeholder": "#sylhet, #budget, #family_trip",
                }
            ),
            "poll_options": forms.Textarea(
                attrs={
                    "rows": 2,
                    "placeholder": "Option 1\nOption 2",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["post_type"].choices = CommunityPost.CANONICAL_POST_TYPE_CHOICES
        self.fields["spot"].required = False
        self.fields["district"].required = False
        self.fields["location_name"].required = False
        self.fields["hashtags"].required = False
        self.fields["poll_question"].required = False
        self.fields["poll_options"].required = False
        self.fields["district"].queryset = District.objects.order_by("name")
        self.fields["spot"].queryset = TourSpot.objects.order_by("name")
        self.fields["title"].widget.attrs.setdefault("placeholder", "Add a short headline")
        self.fields["content"].widget.attrs["placeholder"] = "Create a public post..."
        self.fields["location_name"].widget.attrs.setdefault("placeholder", "Tag a route or place")
        self.fields["poll_question"].widget.attrs.setdefault("placeholder", "Ask one clear poll question")
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select")
            else:
                field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        cleaned_data = super().clean()
        has_media = any(
            cleaned_data.get(name)
            for name in ("image_file", "audio_file", "video_file")
        )
        validate_upload(
            cleaned_data.get("image_file"),
            allowed_extensions=IMAGE_EXTENSIONS,
            max_size_bytes=IMAGE_MAX_BYTES,
            label="Post image",
        )
        validate_upload(
            cleaned_data.get("audio_file"),
            allowed_extensions=AUDIO_EXTENSIONS,
            max_size_bytes=AUDIO_MAX_BYTES,
            label="Post audio",
        )
        validate_upload(
            cleaned_data.get("video_file"),
            allowed_extensions=VIDEO_EXTENSIONS,
            max_size_bytes=VIDEO_MAX_BYTES,
            label="Post video",
        )
        has_poll = bool(
            cleaned_data.get("poll_question")
            and (cleaned_data.get("poll_options") or "").strip()
        )
        if not cleaned_data.get("content") and not has_media and not has_poll:
            raise forms.ValidationError("Write content or attach media or poll.")
        return cleaned_data


class CommunityCommentForm(forms.ModelForm):
    class Meta:
        model = CommunityComment
        fields = ("content", "image_file", "audio_file", "video_file")
        widgets = {
            "content": forms.Textarea(attrs={"rows": 2, "placeholder": "Write a helpful comment..."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        cleaned_data = super().clean()
        has_media = any(
            cleaned_data.get(name)
            for name in ("image_file", "audio_file", "video_file")
        )
        validate_upload(
            cleaned_data.get("image_file"),
            allowed_extensions=IMAGE_EXTENSIONS,
            max_size_bytes=IMAGE_MAX_BYTES,
            label="Comment image",
        )
        validate_upload(
            cleaned_data.get("audio_file"),
            allowed_extensions=AUDIO_EXTENSIONS,
            max_size_bytes=AUDIO_MAX_BYTES,
            label="Comment audio",
        )
        validate_upload(
            cleaned_data.get("video_file"),
            allowed_extensions=VIDEO_EXTENSIONS,
            max_size_bytes=VIDEO_MAX_BYTES,
            label="Comment video",
        )
        if not cleaned_data.get("content") and not has_media:
            raise forms.ValidationError("Comment needs text or media.")
        return cleaned_data
