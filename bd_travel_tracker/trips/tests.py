from decimal import Decimal
import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import CommunityCommentForm, TripForm
from .location_resolver import SpotAdminResolver
from .models import (
    Album,
    AlbumItem,
    Conversation,
    CommunityMembership,
    CommunityComment,
    CommunityCommentEditHistory,
    CommunityNotification,
    CommunityPost,
    CommunityPostMedia,
    CommunityPostReaction,
    CommunityPostSave,
    CommunityPostView,
    CommunityTag,
    District,
    Division,
    Message,
    MessageAttachment,
    SavedSpot,
    TourSpot,
    Trip,
    TripReminder,
    UserFollow,
    UserAppearanceSettings,
    UserCommunitySettings,
    UserDataSettings,
    UserNotificationSettings,
    Upazila,
    UserPrivacySettings,
    UserProfile,
    UserRegionalSettings,
    UserSecuritySettings,
    UserTravelPreferences,
)


class TravelTrackerTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._temp_media = tempfile.mkdtemp()
        cls._media_override = override_settings(MEDIA_ROOT=cls._temp_media)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._temp_media, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user(username="traveler", password="secret123")
        self.user.email = "traveler@example.com"
        self.user.save(update_fields=["email"])
        self.user.profile.full_name = "Traveler User"
        self.user.profile.phone = "01700000000"
        self.user.profile.save(update_fields=["full_name", "phone"])

        self.division = Division.objects.create(name="Dhaka")
        self.district = District.objects.create(name="Gazipur", division=self.division)
        self.upazila = Upazila.objects.create(name="Sreepur", district=self.district)
        self.spot = TourSpot.objects.create(
            name="Bhawal National Park",
            upazila=self.upazila,
            category="Nature",
            latitude=Decimal("24.170321"),
            longitude=Decimal("90.398962"),
        )

    def _create_trip(self, **overrides):
        payload = {
            "user": self.user,
            "division": self.division,
            "district": self.district,
            "upazila": self.upazila,
            "spot": self.spot,
            "from_date": "2026-03-01",
            "hotel_name": "City Inn",
            "transport_cost": Decimal("500"),
            "food_cost": Decimal("300"),
            "hotel_cost": Decimal("1200"),
            "ticket_cost": Decimal("100"),
            "other_cost": Decimal("50"),
        }
        payload.update(overrides)
        return Trip.objects.create(**payload)

    def test_total_cost_auto_calculation(self):
        trip = self._create_trip()
        self.assertEqual(trip.total_cost, Decimal("2150"))

    def test_trip_form_validates_hierarchy(self):
        wrong_division = Division.objects.create(name="Sylhet")

        form = TripForm(
            data={
                "division": wrong_division.id,
                "district": self.district.id,
                "upazila": self.upazila.id,
                "spot": self.spot.id,
                "from_date": "2026-03-01",
                "to_date": "2026-03-02",
                "notes": "Weekend trip",
                "hotel_name": "Hotel",
                "transport_cost": "100",
                "food_cost": "100",
                "hotel_cost": "100",
                "ticket_cost": "100",
                "other_cost": "100",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("district", form.errors)

    def test_trip_form_requires_agency_name_for_agency_trip(self):
        form = TripForm(
            data={
                "division": self.division.id,
                "district": self.district.id,
                "upazila": self.upazila.id,
                "spot": self.spot.id,
                "trip_source": "agency",
                "agency_name": "",
                "from_date": "2026-03-01",
                "to_date": "2026-03-02",
                "hotel_name": "Hotel",
                "transport_cost": "100",
                "food_cost": "100",
                "hotel_cost": "100",
                "ticket_cost": "100",
                "other_cost": "100",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("agency_name", form.errors)

    def test_api_cascade_endpoints(self):
        self.client.force_login(self.user)

        district_response = self.client.get(reverse("api_districts"), {"division_id": self.division.id})
        upazila_response = self.client.get(reverse("api_upazilas"), {"district_id": self.district.id})
        spot_response = self.client.get(reverse("api_spots"), {"upazila_id": self.upazila.id})

        self.assertEqual(district_response.status_code, 200)
        self.assertEqual(upazila_response.status_code, 200)
        self.assertEqual(spot_response.status_code, 200)

        self.assertEqual(district_response.json()["results"][0]["name"], "Gazipur")
        self.assertEqual(upazila_response.json()["results"][0]["name"], "Sreepur")
        self.assertEqual(spot_response.json()["results"][0]["name"], "Bhawal National Park")

    def test_public_and_protected_pages_access(self):
        home_response = self.client.get(reverse("home"))
        map_response = self.client.get(reverse("travel_map"))
        destinations_response = self.client.get(reverse("destinations"))
        community_response = self.client.get(reverse("community"))

        self.assertEqual(home_response.status_code, 200)
        self.assertEqual(map_response.status_code, 200)
        self.assertEqual(destinations_response.status_code, 302)
        self.assertEqual(community_response.status_code, 302)

    def test_destinations_page_supports_filtering_and_actions(self):
        sylhet = Division.objects.create(name="Sylhet")
        sylhet_district = District.objects.create(name="Moulvibazar", division=sylhet)
        sylhet_upazila = Upazila.objects.create(name="Sreemangal", district=sylhet_district)
        other_spot = TourSpot.objects.create(
            name="Lalakhal",
            upazila=sylhet_upazila,
            category="Beach",
            latitude=Decimal("25.170321"),
            longitude=Decimal("91.998962"),
        )
        Trip.objects.create(
            user=self.user,
            division=sylhet,
            district=sylhet_district,
            upazila=sylhet_upazila,
            spot=other_spot,
            from_date="2026-03-05",
        )

        self.client.force_login(self.user)
        response = self.client.get(
            reverse("destinations"),
            {
                "q": "Bhawal",
                "division": self.division.id,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Smart Search + Filters")
        self.assertContains(response, "View Details")
        self.assertContains(response, self.spot.name)
        self.assertEqual(response.context["result_count"], 1)
        self.assertEqual(response.context["destination_rows"][0]["name"], self.spot.name)

    def test_destination_detail_page_renders_sections(self):
        trip = self._create_trip(notes="Carry water and start early.")
        CommunityPost.objects.create(
            user=self.user,
            post_type="travel_experience",
            title="Morning walk at Bhawal",
            content="Great place for a short nature break.",
            district=self.district,
            spot=self.spot,
            location_name=self.spot.name,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("destination_detail", args=[self.spot.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.spot.name)
        self.assertContains(response, "Travel Tips")
        self.assertContains(response, "Community Discussions")
        self.assertContains(response, trip.notes)

    def test_trip_create_prefills_location_from_destination_action(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("trip_create"),
            {
                "division": self.division.id,
                "district": self.district.id,
                "upazila": self.upazila.id,
                "spot": self.spot.id,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'<option value="{self.division.id}" selected>')
        self.assertContains(response, f'<option value="{self.spot.id}" selected>')

    def test_saved_spot_quick_save_redirects_to_next_url(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("saved_spots"),
            {
                "spot": self.spot.id,
                "note": "",
                "next": reverse("destinations"),
            },
        )

        self.assertRedirects(response, reverse("destinations"))
        self.assertTrue(SavedSpot.objects.filter(user=self.user, spot=self.spot).exists())

    def test_first_login_redirects_to_profile_until_completed(self):
        newcomer = User.objects.create_user(username="newbie", password="secret123")

        response = self.client.post(
            reverse("login"),
            {
                "username": "newbie",
                "password": "secret123",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("profile"), response.url)

        protected_response = self.client.get(reverse("dashboard"))
        self.assertEqual(protected_response.status_code, 302)
        self.assertIn(reverse("profile"), protected_response.url)

        profile_submit = self.client.post(
            reverse("profile"),
            {
                "full_name": "New User",
                "email": "newbie@example.com",
                "phone": "01800000000",
                "location": "",
                "website": "",
                "gender": "",
                "date_of_birth": "",
                "avatar_url": "",
                "bio": "",
                "preferred_language": "en",
                "theme_mode": "light",
                "contact_visibility": "private",
                "default_album_visibility": "private",
                "default_story_visibility": "public",
                "receive_community_updates": "on",
                "public_profile": "on",
                "allow_dm": "on",
            },
        )
        self.assertEqual(profile_submit.status_code, 302)
        self.assertEqual(profile_submit.url, reverse("home"))

    def test_authenticated_user_does_not_need_login_again(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")

    def test_account_entry_redirect_logic(self):
        anonymous_response = self.client.get(reverse("account_entry"))
        self.assertEqual(anonymous_response.status_code, 302)
        self.assertIn(reverse("login"), anonymous_response.url)

        self.client.force_login(self.user)
        complete_profile_response = self.client.get(reverse("account_entry"))
        self.assertEqual(complete_profile_response.status_code, 302)
        self.assertEqual(complete_profile_response.url, reverse("home"))

        newcomer = User.objects.create_user(username="fresh", password="secret123")
        self.client.force_login(newcomer)
        incomplete_profile_response = self.client.get(reverse("account_entry"))
        self.assertEqual(incomplete_profile_response.status_code, 302)
        self.assertEqual(incomplete_profile_response.url, reverse("profile"))

    def test_spot_insight_api_returns_stats(self):
        self._create_trip()
        other_user = User.objects.create_user(username="other", password="secret123")
        self._create_trip(user=other_user, hotel_name="Riverside")

        self.client.force_login(self.user)
        response = self.client.get(reverse("api_spot_insight"), {"spot_id": self.spot.id})

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["stats"]["total_visits"], 2)
        self.assertEqual(payload["stats"]["unique_visitors"], 2)
        self.assertEqual(payload["spot"]["name"], "Bhawal National Park")
        self.assertEqual(len(payload["recent_history"]), 2)

    def test_my_trips_shows_merged_summary_and_dashboard_redirects(self):
        self._create_trip()
        self.client.force_login(self.user)

        response = self.client.get(reverse("my_trips"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Trips")
        self.assertContains(response, "2150.00")
        self.assertContains(response, "Bhawal National Park")
        self.assertContains(response, "Explore More Districts")
        self.assertContains(response, "trip-reminder-districts")
        self.assertContains(response, "trip-reminder-upazilas")
        self.assertContains(response, "trip-reminder-spots")

        dashboard_response = self.client.get(reverse("dashboard"))
        self.assertEqual(dashboard_response.status_code, 302)
        self.assertEqual(dashboard_response.url, reverse("my_trips"))

    def test_home_page_uses_dynamic_district_list(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gazipur")
        self.assertContains(response, "Bangladesh districts loaded")

    def test_authenticated_home_shows_profile_avatar_in_account_trigger(self):
        self.user.profile.avatar_url = "https://example.com/avatar.jpg"
        self.user.profile.save(update_fields=["avatar_url"])
        self.client.force_login(self.user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "account-trigger-avatar")
        self.assertContains(response, "account-avatar-image")
        self.assertContains(response, "https://example.com/avatar.jpg")

    def test_trip_edit_updates_existing_trip(self):
        trip = self._create_trip(notes="Old note", food_cost=Decimal("300"))
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("trip_edit", args=[trip.id]),
            {
                "division": self.division.id,
                "district": self.district.id,
                "upazila": self.upazila.id,
                "spot": self.spot.id,
                "from_date": "2026-03-01",
                "to_date": "2026-03-03",
                "notes": "Updated note",
                "hotel_name": "Updated Hotel",
                "transport_cost": "500",
                "food_cost": "700",
                "hotel_cost": "1200",
                "ticket_cost": "100",
                "other_cost": "50",
            },
        )

        self.assertEqual(response.status_code, 302)
        trip.refresh_from_db()
        self.assertEqual(trip.notes, "Updated note")
        self.assertEqual(trip.hotel_name, "Updated Hotel")
        self.assertEqual(trip.food_cost, Decimal("700.00"))
        self.assertEqual(trip.total_cost, Decimal("2550.00"))

    def test_trip_create_can_save_agency_trip(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("trip_create"),
            {
                "division": self.division.id,
                "district": self.district.id,
                "upazila": self.upazila.id,
                "spot": self.spot.id,
                "trip_source": "agency",
                "agency_name": "Green Route Travels",
                "from_date": "2026-03-10",
                "to_date": "2026-03-12",
                "notes": "Booked via agency package",
                "hotel_name": "Updated Hotel",
                "transport_cost": "500",
                "food_cost": "700",
                "hotel_cost": "1200",
                "ticket_cost": "100",
                "other_cost": "50",
            },
        )

        self.assertEqual(response.status_code, 302)
        trip = Trip.objects.get(user=self.user, agency_name="Green Route Travels")
        self.assertEqual(trip.trip_source, "agency")

    def test_profile_auto_created_with_user(self):
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.user.username, "traveler")
        self.assertEqual(profile.theme_mode, "light")

    def test_profile_details_form_updates_profile_fields(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("profile"),
            {
                "full_name": "Updated Traveler",
                "email": "updated@example.com",
                "phone": "01811111111",
                "location": "Dhaka",
                "website": "https://example.com",
                "gender": "male",
                "date_of_birth": "2000-01-01",
                "avatar_url": "",
                "bio": "Updated bio",
                "preferred_language": "bn",
                "theme_mode": "dark",
                "contact_visibility": "public",
                "default_album_visibility": "public",
                "default_story_visibility": "private",
                "receive_community_updates": "on",
                "public_profile": "on",
                "allow_dm": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.email, "updated@example.com")
        self.assertEqual(self.user.profile.full_name, "Updated Traveler")
        self.assertEqual(self.user.profile.location, "Dhaka")
        self.assertEqual(self.user.profile.website, "https://example.com")
        self.assertEqual(self.user.profile.bio, "Updated bio")
        self.assertEqual(self.user.profile.preferred_language, "bn")
        self.assertEqual(self.user.profile.theme_mode, "dark")
        self.assertEqual(self.user.profile.contact_visibility, "public")
        self.assertEqual(self.user.profile.default_album_visibility, "public")
        self.assertEqual(self.user.profile.default_story_visibility, "private")

    def test_profile_details_form_can_upload_cover_photo(self):
        self.client.force_login(self.user)
        cover = SimpleUploadedFile("profile-cover.jpg", b"cover-bits", content_type="image/jpeg")

        response = self.client.post(
            reverse("profile"),
            {
                "full_name": "Traveler User",
                "email": "traveler@example.com",
                "phone": "01700000000",
                "location": "",
                "website": "",
                "gender": "",
                "date_of_birth": "",
                "avatar_url": "",
                "bio": "",
                "preferred_language": "en",
                "theme_mode": "light",
                "contact_visibility": "private",
                "default_album_visibility": "private",
                "default_story_visibility": "public",
                "receive_community_updates": "on",
                "public_profile": "on",
                "allow_dm": "on",
                "cover_photo": cover,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.cover_photo.name.startswith("covers/"))

    def test_profile_details_form_updates_even_if_old_cover_file_is_missing(self):
        self.user.profile.cover_photo.name = "covers/missing-cover.jpg"
        self.user.profile.save(update_fields=["cover_photo"])
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("profile"),
            {
                "full_name": "Traveler User",
                "email": "traveler@example.com",
                "phone": "01700000000",
                "location": "Dhaka",
                "website": "",
                "gender": "",
                "date_of_birth": "",
                "avatar_url": "",
                "bio": "Bio after missing file",
                "preferred_language": "en",
                "theme_mode": "light",
                "contact_visibility": "private",
                "default_album_visibility": "private",
                "default_story_visibility": "public",
                "receive_community_updates": "on",
                "public_profile": "on",
                "allow_dm": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.location, "Dhaka")
        self.assertEqual(self.user.profile.bio, "Bio after missing file")

    def test_profile_media_quick_upload_updates_cover(self):
        self.client.force_login(self.user)
        cover = SimpleUploadedFile("cover.jpg", b"cover-bytes", content_type="image/jpeg")

        response = self.client.post(
            reverse("profile"),
            {
                "action": "update_cover",
                "cover_upload-cover_photo": cover,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.cover_photo.name.startswith("covers/"))

    def test_profile_recent_posts_shows_post_image(self):
        post_image = SimpleUploadedFile("post.jpg", b"post-image", content_type="image/jpeg")
        CommunityPost.objects.create(
            user=self.user,
            post_type="travel_experience",
            title="Rangamati",
            content="Beautiful lake view",
            district=self.district,
            spot=self.spot,
            image_file=post_image,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "community/posts/images/post")
        self.assertContains(response, '<img class="img-fluid rounded mb-3 community-post-image"', html=False)

    def test_settings_page_uses_sidebar_sections(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("settings"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Manage account, privacy, profile, and platform preferences")
        self.assertContains(response, "Account")
        self.assertContains(response, "Profile Settings")
        self.assertContains(response, "Danger Zone")
        self.assertContains(response, "Recovery email")
        self.assertNotContains(response, "Travel Preferences")
        self.assertNotContains(response, "Media")

    def test_settings_account_section_updates_private_account_fields(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("settings_section", args=["account"]),
            {
                "action": "save_section",
                "email": "settings@example.com",
                "phone": "01911111111",
                "recovery_email": "recovery@example.com",
                "recovery_phone": "01822222222",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("settings_section", args=["account"]))
        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()
        security_settings = UserSecuritySettings.objects.get(user=self.user)
        self.assertEqual(self.user.email, "settings@example.com")
        self.assertEqual(self.user.profile.phone, "01911111111")
        self.assertEqual(security_settings.recovery_email, "recovery@example.com")
        self.assertEqual(security_settings.recovery_phone, "01822222222")
        self.assertFalse(security_settings.email_verified)

    def test_settings_profile_section_updates_public_identity_fields(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("settings_section", args=["profile"]),
            {
                "action": "save_section",
                "full_name": "Settings User",
                "username": "traveler_settings",
                "avatar_url": "https://example.com/avatar.jpg",
                "bio": "Traveler bio",
                "location": "Dhaka",
                "website": "https://example.com",
                "social_links": "https://facebook.com/example\nhttps://youtube.com/example",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.username, "traveler_settings")
        self.assertEqual(self.user.profile.full_name, "Settings User")
        self.assertEqual(self.user.profile.bio, "Traveler bio")
        self.assertEqual(self.user.profile.location, "Dhaka")
        self.assertEqual(self.user.profile.website, "https://example.com")
        self.assertEqual(
            self.user.profile.social_links,
            ["https://facebook.com/example", "https://youtube.com/example"],
        )

    def test_settings_privacy_section_updates_profile_and_privacy_settings(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("settings_section", args=["privacy"]),
            {
                "action": "save_section",
                "public_profile": "on",
                "contact_visibility": "public",
                "default_album_visibility": "public",
                "default_story_visibility": "private",
                "trip_visibility": "followers",
                "history_visibility": "public",
                "who_can_message": "no_one",
                "who_can_comment": "followers",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.user.profile.refresh_from_db()
        privacy_settings = UserPrivacySettings.objects.get(user=self.user)
        community_settings = UserCommunitySettings.objects.get(user=self.user)
        self.assertTrue(self.user.profile.public_profile)
        self.assertEqual(self.user.profile.contact_visibility, "public")
        self.assertEqual(self.user.profile.default_album_visibility, "public")
        self.assertEqual(self.user.profile.default_story_visibility, "private")
        self.assertEqual(privacy_settings.trip_visibility, "followers")
        self.assertEqual(privacy_settings.history_visibility, "public")
        self.assertEqual(community_settings.who_can_message, "no_one")
        self.assertEqual(community_settings.who_can_comment, "followers")
        self.assertFalse(self.user.profile.allow_dm)

    def test_settings_security_section_can_change_password(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("settings_section", args=["security"]),
            {
                "action": "save_section",
                "current_password": "secret123",
                "new_password": "NewStrongPass123!",
                "confirm_password": "NewStrongPass123!",
                "two_factor_enabled": "on",
                "login_alerts": "on",
                "suspicious_activity_alerts": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        security_settings = UserSecuritySettings.objects.get(user=self.user)
        self.assertTrue(self.user.check_password("NewStrongPass123!"))
        self.assertTrue(security_settings.two_factor_enabled)

    def test_settings_appearance_section_updates_theme_and_language_preferences(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("settings_section", args=["appearance"]),
            {
                "action": "save_section",
                "theme_mode": "night",
                "preferred_language": "bn",
                "font_size": "lg",
                "layout_density": "compact",
                "map_style": "terrain",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.user.profile.refresh_from_db()
        appearance_settings = UserAppearanceSettings.objects.get(user=self.user)
        self.assertEqual(self.user.profile.theme_mode, "night")
        self.assertEqual(self.user.profile.preferred_language, "bn")
        self.assertEqual(appearance_settings.font_size, "lg")
        self.assertEqual(appearance_settings.layout_density, "compact")
        self.assertEqual(appearance_settings.map_style, "terrain")

    def test_settings_notifications_section_updates_alert_preferences(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("settings_section", args=["notifications"]),
            {
                "action": "save_section",
                "email_notifications": "on",
                "push_notifications": "on",
                "comment_alerts": "on",
                "trip_reminders": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.user.profile.refresh_from_db()
        notification_settings = UserNotificationSettings.objects.get(user=self.user)
        self.assertFalse(notification_settings.community_updates)
        self.assertTrue(notification_settings.email_notifications)
        self.assertTrue(notification_settings.push_notifications)
        self.assertTrue(notification_settings.comment_alerts)
        self.assertFalse(notification_settings.follower_alerts)
        self.assertTrue(notification_settings.trip_reminders)
        self.assertFalse(self.user.profile.receive_community_updates)

    def test_settings_danger_zone_can_deactivate_account(self):
        guarded_user = User.objects.create_user(username="guarded", password="secret123", email="guarded@example.com")
        guarded_user.profile.full_name = "Guarded User"
        guarded_user.profile.phone = "01799999999"
        guarded_user.profile.save(update_fields=["full_name", "phone"])
        self.client.force_login(guarded_user)

        response = self.client.post(
            reverse("settings_section", args=["danger_zone"]),
            {
                "action": "deactivate_account",
                "current_password": "secret123",
                "confirm_text": "DEACTIVATE",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))
        guarded_user.refresh_from_db()
        self.assertFalse(guarded_user.is_active)

    def test_settings_danger_zone_can_delete_account(self):
        removable_user = User.objects.create_user(username="removable", password="secret123", email="removable@example.com")
        removable_user.profile.full_name = "Removable User"
        removable_user.profile.phone = "01688888888"
        removable_user.profile.save(update_fields=["full_name", "phone"])
        self.client.force_login(removable_user)

        response = self.client.post(
            reverse("settings_section", args=["danger_zone"]),
            {
                "action": "delete_account",
                "current_password": "secret123",
                "confirm_text": "DELETE MY ACCOUNT",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))
        self.assertFalse(User.objects.filter(username="removable").exists())

    def test_incomplete_profile_can_still_upload_media(self):
        newcomer = User.objects.create_user(username="photographer", password="secret123")
        self.client.force_login(newcomer)
        avatar = SimpleUploadedFile("avatar.png", b"avatar-bytes", content_type="image/png")

        response = self.client.post(
            reverse("profile"),
            {
                "action": "update_avatar",
                "avatar_upload-avatar_file": avatar,
            },
        )

        self.assertEqual(response.status_code, 302)
        newcomer.profile.refresh_from_db()
        self.assertTrue(newcomer.profile.avatar_file.name.startswith("avatars/"))
        self.assertFalse(newcomer.profile.is_profile_complete)

    def test_my_trips_can_create_next_trip_reminder(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("my_trips"),
            {
                "action": "set_next_trip",
                "title": "Sajek Tour",
                "reminder_date": "2026-12-20",
                "reminder_time": "20:30",
                "note": "Book transport",
            },
        )

        self.assertEqual(response.status_code, 302)
        reminder = TripReminder.objects.get(user=self.user, title="Sajek Tour")
        self.assertEqual(str(reminder.reminder_date), "2026-12-20")
        self.assertEqual(reminder.note, "Book transport")

    def test_my_trips_can_create_agency_next_trip_reminder(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("my_trips"),
            {
                "action": "set_next_trip",
                "title": "Agency Sajek Tour",
                "trip_source": "agency",
                "agency_name": "Green Route Travels",
                "reminder_date": "2026-12-20",
                "reminder_time": "20:30",
                "note": "Agency confirmed bus seats",
            },
        )

        self.assertEqual(response.status_code, 302)
        reminder = TripReminder.objects.get(user=self.user, title="Agency Sajek Tour")
        self.assertEqual(reminder.trip_source, "agency")
        self.assertEqual(reminder.agency_name, "Green Route Travels")

    def test_my_trips_can_save_destination_spot_with_reminder(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("my_trips"),
            {
                "action": "set_next_trip",
                "title": "Bhawal Plan",
                "division": str(self.division.id),
                "district": str(self.district.id),
                "upazila": str(self.upazila.id),
                "spot": str(self.spot.id),
                "reminder_date": "2026-12-22",
                "reminder_time": "09:15",
                "note": "Leave early",
            },
        )

        self.assertEqual(response.status_code, 302)
        reminder = TripReminder.objects.get(user=self.user, title="Bhawal Plan")
        self.assertEqual(reminder.spot, self.spot)

    def test_my_trips_shows_live_route_tracker_for_destination_reminder(self):
        TripReminder.objects.create(
            user=self.user,
            title="Forest Escape",
            spot=self.spot,
            reminder_date="2026-12-24",
            reminder_time="07:30",
            note="Route check",
            is_active=True,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("my_trips"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Next Trip Alert")
        self.assertContains(response, "Fastest Route")
        self.assertContains(response, "Drive")
        self.assertContains(response, self.spot.name)
        self.assertContains(response, "next-trip-route-data")
        self.assertContains(response, "nextTripRouteFallbackMap")

    def test_my_trips_shows_agency_trip_metadata_in_log_and_alert(self):
        self._create_trip(trip_source="agency", agency_name="Green Route Travels")
        TripReminder.objects.create(
            user=self.user,
            title="Agency Forest Escape",
            trip_source="agency",
            agency_name="Green Route Travels",
            spot=self.spot,
            reminder_date="2026-12-24",
            reminder_time="07:30",
            note="Agency route check",
            is_active=True,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("my_trips"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Agency Trip")
        self.assertContains(response, "Green Route Travels")

    def test_register_company_account_stays_pending_verification(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "agency_owner",
                "email": "owner@agency.example",
                "password1": "AgencyStrongPass123!",
                "password2": "AgencyStrongPass123!",
                "account_type": "company",
                "agency_name": "Green Route Travels",
                "agency_license_number": "TL-2026-1001",
                "agency_contact_person": "Owner Name",
                "agency_contact_phone": "01812345678",
                "agency_email": "contact@agency.example",
                "agency_address": "Dhaka, Bangladesh",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("login"))
        company_user = User.objects.get(username="agency_owner")
        company_user.refresh_from_db()
        company_user.profile.refresh_from_db()
        self.assertFalse(company_user.is_active)
        self.assertEqual(company_user.profile.account_type, "company")
        self.assertEqual(company_user.profile.agency_name, "Green Route Travels")
        self.assertEqual(company_user.profile.company_verification_status, "pending")

    def test_new_account_pages_load(self):
        album = Album.objects.create(
            user=self.user,
            title="Cox Trip",
            description="Beach memories",
            trip_date="2026-03-01",
            spot=self.spot,
        )
        self.client.force_login(self.user)

        endpoints = [
            reverse("albums"),
            reverse("album_detail", args=[album.id]),
            reverse("stories"),
            reverse("travel_history"),
            reverse("saved_spots"),
            reverse("profile"),
            reverse("settings"),
            reverse("community"),
        ]

        for url in endpoints:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)

    def test_album_quick_upload_from_main_page(self):
        album = Album.objects.create(
            user=self.user,
            title="Main Upload Album",
            description="For quick upload",
            trip_date="2026-03-08",
            spot=self.spot,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("albums"),
            {
                "action": "quick_upload",
                "target_album_id": album.id,
                "item-external_url": "https://example.com/photo1",
                "item-caption": "Sunset",
                "item-taken_at": "2026-03-08",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            AlbumItem.objects.filter(album=album, external_url="https://example.com/photo1").exists()
        )

    def test_community_like_and_save_toggle(self):
        post = CommunityPost.objects.create(
            user=self.user,
            post_type="travel_question",
            title="Need Sajek transport advice",
            content="How to go from Dhaka?",
            district=self.district,
            spot=self.spot,
            location_name="Sajek Valley",
            hashtags="#sajek,#transport",
        )
        self.client.force_login(self.user)

        like_url = reverse("community_toggle_like", args=[post.id])
        save_url = reverse("community_toggle_save", args=[post.id])

        like_on = self.client.post(like_url)
        save_on = self.client.post(save_url)
        like_off = self.client.post(like_url)
        save_off = self.client.post(save_url)

        self.assertEqual(like_on.status_code, 200)
        self.assertEqual(save_on.status_code, 200)
        self.assertEqual(like_off.status_code, 200)
        self.assertEqual(save_off.status_code, 200)
        self.assertFalse(CommunityPostReaction.objects.filter(post=post, user=self.user).exists())
        self.assertFalse(CommunityPostSave.objects.filter(post=post, user=self.user).exists())

    def test_community_reaction_can_switch_types(self):
        post = CommunityPost.objects.create(
            user=self.user,
            post_type="travel_experience",
            title="Reaction options",
            content="Checking multiple reactions.",
            district=self.district,
            spot=self.spot,
        )
        self.client.force_login(self.user)

        reaction_url = reverse("community_toggle_like", args=[post.id])

        love_response = self.client.post(reaction_url, {"reaction": "love"})
        helpful_response = self.client.post(reaction_url, {"reaction": "helpful"})
        off_response = self.client.post(reaction_url, {"reaction": "helpful"})

        self.assertEqual(love_response.status_code, 200)
        self.assertEqual(love_response.json()["selected_reaction"], "love")
        self.assertEqual(helpful_response.status_code, 200)
        self.assertEqual(helpful_response.json()["selected_reaction"], "helpful")
        self.assertEqual(off_response.status_code, 200)
        self.assertEqual(off_response.json()["selected_reaction"], "")
        self.assertFalse(CommunityPostReaction.objects.filter(post=post, user=self.user).exists())

    def test_like_notification_created_for_post_owner(self):
        post = CommunityPost.objects.create(
            user=self.user,
            post_type="travel_experience",
            title="Nilgiri sunrise",
            content="Morning clouds everywhere.",
            district=self.district,
            spot=self.spot,
        )
        liker = User.objects.create_user(username="liker", password="secret123")
        liker.email = "liker@example.com"
        liker.save(update_fields=["email"])
        liker.profile.full_name = "Liker User"
        liker.profile.phone = "01711111111"
        liker.profile.save(update_fields=["full_name", "phone"])

        self.client.force_login(liker)
        response = self.client.post(reverse("community_toggle_like", args=[post.id]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            CommunityNotification.objects.filter(
                user=self.user,
                actor=liker,
                post=post,
                kind="like",
            ).exists()
        )

    def test_notification_open_redirects_to_follow_actor_profile_and_marks_read(self):
        follower = User.objects.create_user(username="follower1", password="secret123")
        notification = CommunityNotification.objects.create(
            user=self.user,
            actor=follower,
            kind="follow",
            message="follower1 started following you.",
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("notification_open", args=[notification.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("traveler_profile", args=[follower.id]))
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_notification_open_redirects_to_liked_post_and_marks_read(self):
        liker = User.objects.create_user(username="liker2", password="secret123")
        post = CommunityPost.objects.create(
            user=self.user,
            post_type="travel_experience",
            title="Sreemangal tea garden",
            content="Green everywhere.",
            district=self.district,
            spot=self.spot,
        )
        notification = CommunityNotification.objects.create(
            user=self.user,
            actor=liker,
            post=post,
            kind="like",
            message="liker2 liked your post.",
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("notification_open", args=[notification.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"{reverse('community')}#post-{post.id}")
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_account_dropdown_shows_notification_link_and_unread_badge(self):
        CommunityNotification.objects.create(
            user=self.user,
            kind="comment",
            message="A new comment arrived.",
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("notifications"))
        self.assertContains(response, "account-trigger-badge")

    def test_authenticated_request_updates_last_active_at(self):
        self.client.force_login(self.user)

        self.client.get(reverse("home"))
        self.user.profile.refresh_from_db()

        self.assertIsNotNone(self.user.profile.last_active_at)

    def test_community_page_shows_online_indicator_and_notifications_panel(self):
        helper = User.objects.create_user(username="helperonline", password="secret123")
        helper.email = "helper@example.com"
        helper.save(update_fields=["email"])
        helper.profile.full_name = "Helper Online"
        helper.profile.phone = "01800000000"
        helper.profile.last_active_at = timezone.now()
        helper.profile.save(update_fields=["full_name", "phone", "last_active_at"])
        CommunityMembership.objects.create(user=helper, is_active=True)
        CommunityNotification.objects.create(
            user=self.user,
            actor=helper,
            kind="follow",
            message="helperonline started following you.",
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("community"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Helper Online")
        self.assertContains(response, "started following you")
        self.assertContains(response, "community-online-dot")

    def test_community_post_syncs_tags_and_inline_media_records(self):
        image = SimpleUploadedFile("community.png", b"png-bytes", content_type="image/png")
        post = CommunityPost.objects.create(
            user=self.user,
            post_type="discussion",
            title="Tagged post",
            content="Testing tags and media",
            district=self.district,
            spot=self.spot,
            hashtags="budget, #Gazipur, #budget",
            image_file=image,
        )

        self.assertEqual(post.hashtags_list, ["#budget", "#gazipur"])
        self.assertTrue(CommunityTag.objects.filter(name="#budget").exists())
        self.assertTrue(post.tags.filter(name="#gazipur").exists())
        self.assertTrue(CommunityPostMedia.objects.filter(post=post, media_type="image", source="inline").exists())

    def test_community_section_routes_render_and_badge_counts(self):
        my_post = CommunityPost.objects.create(
            user=self.user,
            post_type="discussion",
            title="My discussion",
            content="Home feed post",
            district=self.district,
            spot=self.spot,
        )
        saved_post = CommunityPost.objects.create(
            user=User.objects.create_user(username="savedauthor", password="secret123"),
            post_type="help",
            title="Saved help post",
            content="Need transport support",
            district=self.district,
            spot=self.spot,
        )
        CommunityPostSave.objects.create(post=saved_post, user=self.user)
        CommunityPostView.objects.create(post=my_post, user=self.user)
        CommunityPostMedia.objects.create(post=my_post, media_type="image", external_url="https://example.com/demo.png")

        self.client.force_login(self.user)
        route_map = {
            "community": "home",
            "community_discussions": "discussions",
            "community_help": "help",
            "community_trip_planning": "trip_planning",
            "community_budget": "budget",
            "community_hotels": "hotels",
            "community_transport": "transport",
            "community_guides": "guides",
            "community_popular": "popular",
            "community_my_posts": "my_posts",
            "community_saved_posts": "saved",
            "community_media_gallery": "media",
            "community_members": "members",
        }

        for route_name, section_key in route_map.items():
            response = self.client.get(reverse(route_name))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context["active_section"], section_key)

        home_response = self.client.get(reverse("community"))
        self.assertEqual(home_response.context["my_posts_count"], 1)
        self.assertEqual(home_response.context["saved_posts_count"], 1)
        self.assertEqual(home_response.context["media_posts_count"], 1)

    def test_help_section_resolved_filter_and_members_search(self):
        unresolved = CommunityPost.objects.create(
            user=self.user,
            post_type="help",
            title="Need train advice",
            content="Unresolved route issue",
            district=self.district,
            spot=self.spot,
            is_resolved=False,
        )
        resolved = CommunityPost.objects.create(
            user=self.user,
            post_type="help",
            title="Resolved hotel question",
            content="Found the answer",
            district=self.district,
            spot=self.spot,
            is_resolved=True,
        )
        helper = User.objects.create_user(username="memberfinder", password="secret123")
        helper.email = "memberfinder@example.com"
        helper.save(update_fields=["email"])
        helper.profile.full_name = "Member Finder"
        helper.profile.phone = "01911111111"
        helper.profile.save(update_fields=["full_name", "phone"])
        CommunityMembership.objects.create(user=helper, is_active=True)

        self.client.force_login(self.user)
        help_response = self.client.get(reverse("community_help"), {"resolved": "unresolved"})
        members_response = self.client.get(reverse("community_members"), {"member_q": "Finder"})

        self.assertEqual(help_response.status_code, 200)
        self.assertContains(help_response, unresolved.title)
        self.assertNotContains(help_response, resolved.title)
        self.assertEqual(members_response.status_code, 200)
        self.assertContains(members_response, "Member Finder")

    def test_private_profile_blocks_mini_profile_api_for_other_member(self):
        stranger = User.objects.create_user(username="stranger", password="secret123")
        stranger.email = "stranger@example.com"
        stranger.save(update_fields=["email"])
        stranger.profile.full_name = "Stranger"
        stranger.profile.phone = "01900000000"
        stranger.profile.save(update_fields=["full_name", "phone"])
        self.user.profile.public_profile = False
        self.user.profile.save(update_fields=["public_profile"])

        self.client.force_login(stranger)
        response = self.client.get(reverse("community_user_profile_api", args=[self.user.id]))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "This profile is private.")

    def test_comment_notification_respects_receive_community_updates(self):
        post = CommunityPost.objects.create(
            user=self.user,
            post_type="travel_question",
            title="Need Sajek transport advice",
            content="How to go from Dhaka?",
            district=self.district,
            spot=self.spot,
            location_name="Sajek Valley",
            hashtags="#sajek,#transport",
        )
        commenter = User.objects.create_user(username="helper", password="secret123")
        self.user.profile.receive_community_updates = False
        self.user.profile.save(update_fields=["receive_community_updates"])

        self.client.force_login(commenter)
        response = self.client.post(
            reverse("community_add_comment", args=[post.id]),
            {"content": "Take the night coach and reserve early."},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(CommunityNotification.objects.filter(user=self.user, post=post).exists())

    def test_comment_notification_respects_comment_alert_setting(self):
        post = CommunityPost.objects.create(
            user=self.user,
            post_type="travel_experience",
            title="Bandarban help",
            content="Need route idea.",
            district=self.district,
            spot=self.spot,
        )
        commenter = User.objects.create_user(username="quietcommenter", password="secret123")
        self.user.notification_settings.comment_alerts = False
        self.user.notification_settings.save(update_fields=["comment_alerts"])

        self.client.force_login(commenter)
        response = self.client.post(
            reverse("community_add_comment", args=[post.id]),
            {"content": "Take the early bus."},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            CommunityNotification.objects.filter(user=self.user, actor=commenter, post=post, kind="comment").exists()
        )

    def test_comment_owner_can_edit_and_history_is_saved(self):
        post = CommunityPost.objects.create(
            user=self.user,
            post_type="travel_experience",
            title="Editing comments",
            content="Original post body.",
            district=self.district,
            spot=self.spot,
        )
        comment = CommunityComment.objects.create(
            post=post,
            user=self.user,
            content="Initial comment text.",
        )

        self.client.force_login(self.user)
        response = self.client.post(
            reverse("community_edit_comment", args=[comment.id]),
            {
                f"comment-{comment.id}-content": "Updated comment text.",
            },
        )

        self.assertRedirects(response, f"{reverse('community')}#comments-{post.id}")
        comment.refresh_from_db()
        self.assertEqual(comment.content, "Updated comment text.")
        self.assertIsNotNone(comment.edited_at)
        self.assertTrue(
            CommunityCommentEditHistory.objects.filter(
                comment=comment,
                edited_by=self.user,
                previous_content="Initial comment text.",
            ).exists()
        )

    def test_other_user_cannot_edit_someone_else_comment(self):
        other_user = User.objects.create_user(username="othereditor", password="secret123")
        other_user.email = "othereditor@example.com"
        other_user.save(update_fields=["email"])
        other_user.profile.full_name = "Other Editor"
        other_user.profile.phone = "01888888888"
        other_user.profile.save(update_fields=["full_name", "phone"])
        post = CommunityPost.objects.create(
            user=self.user,
            post_type="travel_experience",
            title="Protected comments",
            content="Post body.",
            district=self.district,
            spot=self.spot,
        )
        comment = CommunityComment.objects.create(
            post=post,
            user=self.user,
            content="Do not change me.",
        )

        self.client.force_login(other_user)
        response = self.client.post(
            reverse("community_edit_comment", args=[comment.id]),
            {
                f"comment-{comment.id}-content": "Tampered",
            },
        )

        self.assertRedirects(response, f"{reverse('community')}#comments-{post.id}")
        comment.refresh_from_db()
        self.assertEqual(comment.content, "Do not change me.")
        self.assertFalse(CommunityCommentEditHistory.objects.filter(comment=comment).exists())

    def test_community_page_shows_comment_edit_and_history_controls(self):
        post = CommunityPost.objects.create(
            user=self.user,
            post_type="travel_experience",
            title="Community controls",
            content="Body",
            district=self.district,
            spot=self.spot,
        )
        comment = CommunityComment.objects.create(
            post=post,
            user=self.user,
            content="Original",
            edited_at=timezone.now(),
        )
        CommunityCommentEditHistory.objects.create(
            comment=comment,
            edited_by=self.user,
            previous_content="Older version",
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("community"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Update Comment")
        self.assertContains(response, "Edit History (1)")

    def test_community_page_shows_comment_suggestions_and_action_hooks(self):
        post = CommunityPost.objects.create(
            user=self.user,
            post_type="travel_question",
            title="Need Cox's Bazar route help",
            content="Please suggest the best bus and budget plan.",
            district=self.district,
            spot=self.spot,
            location_name="Cox's Bazar",
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("community"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI reply suggestions")
        self.assertContains(response, "js-comment-suggestions")
        self.assertContains(response, "js-refresh-comment-suggestions")
        self.assertContains(response, "js-focus-comment-btn")
        self.assertContains(response, "js-reaction-option")
        self.assertContains(response, f'data-post-id="{post.id}"', html=False)

    def test_community_page_shows_group_header_and_modal_composer_hooks(self):
        CommunityPost.objects.create(
            user=self.user,
            post_type="discussion",
            title="Header smoke check",
            content="Testing the community layout.",
            district=self.district,
            spot=self.spot,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("community"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "community-cover-card")
        self.assertContains(response, "community-group-tabs")
        self.assertContains(response, "communityPostModal")
        self.assertContains(response, "js-open-post-modal")
        self.assertContains(response, "communityKeyword")

    def test_upload_form_rejects_unsafe_extension(self):
        upload = SimpleUploadedFile(
            "malware.exe",
            b"fake-binary",
            content_type="application/octet-stream",
        )
        form = CommunityCommentForm(
            data={"content": "See attachment"},
            files={"image_file": upload},
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Comment image must use one of these file types", str(form.errors))

    def test_location_resolver_maps_official_name_to_existing_upazila(self):
        division = Division.objects.create(name="Reference Division")
        district = District.objects.create(name="Reference District", division=division)
        upazila = Upazila.objects.create(name="Reference Upazila", district=district)

        resolver = SpotAdminResolver(
            reference_payload={
                "divisions": [{"name_en": "Chattogram", "name_bn": "Reference Division"}],
                "districts": [{"name_en": "Rangamati", "name_bn": "Reference District"}],
                "upazilas": [
                    {
                        "division_name_en": "Chattogram",
                        "district_name_en": "Rangamati",
                        "name_en": "Bagaichhari",
                        "name_bn": "Reference Upazila",
                    }
                ],
            }
        )

        resolved = resolver.resolve_db_location("Chattogram", "Rangamati", "Baghai Chhari")

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved[0].id, division.id)
        self.assertEqual(resolved[1].id, district.id)
        self.assertEqual(resolved[2].id, upazila.id)

    def test_location_resolver_creates_missing_official_upazila(self):
        division = Division.objects.create(name="Metro Division")
        district = District.objects.create(name="Metro District", division=division)

        resolver = SpotAdminResolver(
            reference_payload={
                "divisions": [{"name_en": "Dhaka", "name_bn": "Metro Division"}],
                "districts": [{"name_en": "Dhaka", "name_bn": "Metro District"}],
                "upazilas": [],
            }
        )

        resolved = resolver.resolve_db_location("Dhaka", "Dhaka", "Adabor")

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved[2].district_id, district.id)
        self.assertEqual(resolved[2].name, "Adabor")

    def test_location_resolver_matches_bangla_name_variants(self):
        division = Division.objects.create(name="Barishal Division")
        district = District.objects.create(
            name="\u09aa\u099f\u09c1\u09df\u09be\u0996\u09be\u09b2\u09c0",
            division=division,
        )
        upazila = Upazila.objects.create(
            name="\u0995\u09b2\u09be\u09aa\u09be\u09a1\u09bc\u09be",
            district=district,
        )

        resolver = SpotAdminResolver(
            reference_payload={
                "divisions": [{"name_en": "Barishal", "name_bn": "Barishal Division"}],
                "districts": [
                    {
                        "name_en": "Patuakhali",
                        "name_bn": "\u09aa\u099f\u09c1\u09af\u09bc\u09be\u0996\u09be\u09b2\u09c0",
                    }
                ],
                "upazilas": [
                    {
                        "division_name_en": "Barishal",
                        "district_name_en": "Patuakhali",
                        "name_en": "Kalapara",
                        "name_bn": "\u0995\u09b2\u09be\u09aa\u09be\u09a1\u09bc\u09be",
                    }
                ],
            }
        )

        resolved = resolver.resolve_db_location("Barishal", "Patuakhali", "Kalapara")

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved[1].id, district.id)
        self.assertEqual(resolved[2].id, upazila.id)

    def test_location_resolver_supports_legacy_nawabganj_official_name(self):
        division = Division.objects.create(name="Rajshahi Division")
        district = District.objects.create(name="Chapainawabganj", division=division)
        upazila = Upazila.objects.create(name="Chapainawabganj Sadar", district=district)

        resolver = SpotAdminResolver(
            reference_payload={
                "divisions": [{"name_en": "Rajshahi", "name_bn": "Rajshahi Division"}],
                "districts": [{"name_en": "Chapainawabganj", "name_bn": "Chapainawabganj"}],
                "upazilas": [
                    {
                        "division_name_en": "Rajshahi",
                        "district_name_en": "Chapainawabganj",
                        "name_en": "Chapainawabganj Sadar",
                        "name_bn": "Chapainawabganj Sadar",
                    }
                ],
            }
        )

        resolved = resolver.resolve_db_location("Rajshahi", "Nawabganj", "Nawabganj Sadar")

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved[1].id, district.id)
        self.assertEqual(resolved[2].id, upazila.id)

    def test_location_resolver_supports_legacy_nawabganj_reference_names_for_bangla_db(self):
        division = Division.objects.create(name="Rajshahi Division")
        district = District.objects.create(
            name="\u099a\u09be\u0981\u09aa\u09be\u0987\u09a8\u09ac\u09be\u09ac\u0997\u099e\u09cd\u099c",
            division=division,
        )
        upazila = Upazila.objects.create(
            name="\u099a\u09be\u0981\u09aa\u09be\u0987\u09a8\u09ac\u09be\u09ac\u0997\u099e\u09cd\u099c \u09b8\u09a6\u09b0",
            district=district,
        )
        Upazila.objects.create(
            name="\u09a8\u0993\u09af\u09bc\u09be\u09ac\u0997\u099e\u09cd\u099c \u09b8\u09a6\u09b0",
            district=district,
        )

        resolver = SpotAdminResolver(
            reference_payload={
                "divisions": [{"name_en": "Rajshahi", "name_bn": "Rajshahi Division"}],
                "districts": [
                    {
                        "name_en": "Nawabganj",
                        "name_bn": "\u09a8\u0993\u09af\u09bc\u09be\u09ac\u0997\u099e\u09cd\u099c",
                    }
                ],
                "upazilas": [
                    {
                        "division_name_en": "Rajshahi",
                        "district_name_en": "Nawabganj",
                        "name_en": "Nawabganj Sadar",
                        "name_bn": "\u09a8\u0993\u09af\u09bc\u09be\u09ac\u0997\u099e\u09cd\u099c \u09b8\u09a6\u09b0",
                    }
                ],
            }
        )

        resolved = resolver.resolve_db_location("Rajshahi", "Nawabganj", "Nawabganj Sadar")

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved[1].id, district.id)
        self.assertEqual(resolved[2].id, upazila.id)

    def test_can_follow_and_unfollow_another_user(self):
        other_user = User.objects.create_user(username="guide", password="secret123")

        self.client.force_login(self.user)

        follow_response = self.client.post(
            reverse("community_toggle_follow", args=[other_user.id]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(follow_response.status_code, 200)
        self.assertTrue(follow_response.json()["following"])
        self.assertTrue(
            UserFollow.objects.filter(follower=self.user, following=other_user).exists()
        )
        self.assertTrue(
            CommunityNotification.objects.filter(
                user=other_user,
                actor=self.user,
                kind="follow",
            ).exists()
        )

        unfollow_response = self.client.post(
            reverse("community_toggle_follow", args=[other_user.id]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(unfollow_response.status_code, 200)
        self.assertFalse(unfollow_response.json()["following"])
        self.assertFalse(
            UserFollow.objects.filter(follower=self.user, following=other_user).exists()
        )

    def test_follower_only_message_permission_blocks_non_followers(self):
        other_user = User.objects.create_user(username="lockedguide", password="secret123")
        other_user.community_settings.who_can_message = "followers"
        other_user.community_settings.save(update_fields=["who_can_message", "updated_at"])

        self.client.force_login(self.user)

        blocked_response = self.client.get(reverse("direct_message_start", args=[other_user.id]))

        self.assertRedirects(blocked_response, reverse("traveler_profile", args=[other_user.id]))
        self.assertFalse(Conversation.objects.exists())

        UserFollow.objects.create(follower=self.user, following=other_user)

        allowed_response = self.client.get(reverse("direct_message_start", args=[other_user.id]))
        conversation = Conversation.objects.get()

        self.assertRedirects(
            allowed_response,
            f"{reverse('direct_messages')}?conversation={conversation.id}",
        )

    def test_direct_message_send_creates_message_and_notification(self):
        other_user = User.objects.create_user(username="host", password="secret123")
        other_user.profile.full_name = "Tour Host"
        other_user.profile.save(update_fields=["full_name"])
        other_user.community_settings.who_can_message = "everyone"
        other_user.community_settings.save(update_fields=["who_can_message", "updated_at"])

        self.client.force_login(self.user)
        self.client.get(reverse("direct_message_start", args=[other_user.id]))
        conversation = Conversation.objects.get()

        send_response = self.client.post(
            reverse("direct_message_send", args=[conversation.id]),
            {"content": "Hello, I want to join your trip."},
        )

        self.assertRedirects(
            send_response,
            f"{reverse('direct_messages')}?conversation={conversation.id}",
        )
        self.assertTrue(
            Message.objects.filter(
                conversation=conversation,
                sender=self.user,
                content="Hello, I want to join your trip.",
            ).exists()
        )
        self.assertTrue(
            CommunityNotification.objects.filter(
                user=other_user,
                actor=self.user,
                kind="direct_message",
            ).exists()
        )

        inbox_response = self.client.get(reverse("direct_messages"), {"conversation": conversation.id})

        self.assertEqual(inbox_response.status_code, 200)
        self.assertContains(inbox_response, "Hello, I want to join your trip.")
        self.assertContains(inbox_response, "Tour Host")

    def test_direct_message_notification_respects_message_alert_setting(self):
        other_user = User.objects.create_user(username="hostquiet", password="secret123")
        other_user.community_settings.who_can_message = "everyone"
        other_user.community_settings.save(update_fields=["who_can_message", "updated_at"])
        other_user.notification_settings.message_alerts = False
        other_user.notification_settings.save(update_fields=["message_alerts"])

        self.client.force_login(self.user)
        self.client.get(reverse("direct_message_start", args=[other_user.id]))
        conversation = Conversation.objects.get()
        response = self.client.post(
            reverse("direct_message_send", args=[conversation.id]),
            {"content": "Checking notification settings."},
        )

        self.assertRedirects(response, f"{reverse('direct_messages')}?conversation={conversation.id}")
        self.assertFalse(
            CommunityNotification.objects.filter(user=other_user, actor=self.user, kind="direct_message").exists()
        )

    def test_direct_message_call_request_creates_notification(self):
        other_user = User.objects.create_user(username="callhost", password="secret123")
        other_user.community_settings.who_can_message = "everyone"
        other_user.community_settings.save(update_fields=["who_can_message", "updated_at"])

        self.client.force_login(self.user)
        self.client.get(reverse("direct_message_start", args=[other_user.id]))
        conversation = Conversation.objects.get()
        response = self.client.post(
            reverse("direct_message_call_request", args=[conversation.id]),
            {"mode": "video"},
        )

        self.assertRedirects(response, f"{reverse('direct_messages')}?conversation={conversation.id}")
        self.assertTrue(
            CommunityNotification.objects.filter(
                user=other_user,
                actor=self.user,
                conversation=conversation,
                kind="call",
            ).exists()
        )

    def test_notifications_page_shows_message_and_call_entries(self):
        other_user = User.objects.create_user(username="noticefriend", password="secret123")
        other_user.profile.full_name = "Notice Friend"
        other_user.profile.save(update_fields=["full_name"])
        conversation = Conversation.objects.create()
        conversation.participants.set([self.user, other_user])
        CommunityNotification.objects.create(
            user=self.user,
            actor=other_user,
            conversation=conversation,
            kind="direct_message",
            message="noticefriend sent you a direct message.",
        )
        CommunityNotification.objects.create(
            user=self.user,
            actor=other_user,
            conversation=conversation,
            kind="call",
            message="noticefriend started a video call request.",
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("notifications"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Notice Friend")
        self.assertContains(response, "Direct Message")
        self.assertContains(response, "Call")

    def test_public_traveler_profile_shows_follow_and_message_actions(self):
        other_user = User.objects.create_user(username="travelfriend", password="secret123")
        other_user.profile.full_name = "Travel Friend"
        other_user.profile.bio = "Hiking and group tour planner."
        other_user.profile.save(update_fields=["full_name", "bio"])
        other_user.community_settings.who_can_message = "everyone"
        other_user.community_settings.save(update_fields=["who_can_message", "updated_at"])

        self.client.force_login(self.user)
        response = self.client.get(reverse("traveler_profile", args=[other_user.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Travel Friend")
        self.assertContains(response, "Follow")
        self.assertContains(response, "Message")

    def test_public_traveler_profile_shows_recent_post_image(self):
        other_user = User.objects.create_user(username="photouser", password="secret123")
        other_user.profile.full_name = "Photo User"
        other_user.profile.save(update_fields=["full_name"])
        post_image = SimpleUploadedFile("post-photo.jpg", b"image-bits", content_type="image/jpeg")
        CommunityPost.objects.create(
            user=other_user,
            post_type="travel_experience",
            title="Bandarban memories",
            content="Clouds above the hills.",
            district=self.district,
            spot=self.spot,
            image_file=post_image,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("traveler_profile", args=[other_user.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bandarban memories")
        self.assertContains(response, "post-photo.jpg")

    def test_send_message_api_creates_attachment_and_returns_payload(self):
        other_user = User.objects.create_user(username="apihost", password="secret123")
        other_user.community_settings.who_can_message = "everyone"
        other_user.community_settings.save(update_fields=["who_can_message", "updated_at"])
        upload = SimpleUploadedFile("note.jpg", b"file-bits", content_type="image/jpeg")

        self.client.force_login(self.user)
        response = self.client.post(
            reverse("api_send_message"),
            {
                "receiver_id": other_user.id,
                "content": "Assalamu Alaikum",
                "attachment": upload,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("conversation_id", payload)
        self.assertEqual(payload["message"]["content"], "Assalamu Alaikum")
        self.assertEqual(len(payload["message"]["attachments"]), 1)
        self.assertTrue(MessageAttachment.objects.filter(message_id=payload["message"]["id"]).exists())

    def test_conversation_and_message_api_return_user_data(self):
        other_user = User.objects.create_user(username="reader", password="secret123")
        other_user.community_settings.who_can_message = "everyone"
        other_user.community_settings.save(update_fields=["who_can_message", "updated_at"])

        self.client.force_login(self.user)
        self.client.get(reverse("direct_message_start", args=[other_user.id]))
        conversation = Conversation.objects.get()
        Message.objects.create(
            conversation=conversation,
            sender=other_user,
            content="Welcome to the thread.",
        )

        conversations_response = self.client.get(reverse("api_conversations"))
        messages_response = self.client.get(reverse("api_messages"), {"conversation_id": conversation.id})
        mark_read_response = self.client.post(reverse("api_mark_read"), {"conversation_id": conversation.id})

        self.assertEqual(conversations_response.status_code, 200)
        self.assertEqual(messages_response.status_code, 200)
        self.assertEqual(mark_read_response.status_code, 200)
        self.assertEqual(conversations_response.json()["results"][0]["partner"]["username"], "reader")
        self.assertEqual(messages_response.json()["results"][0]["content"], "Welcome to the thread.")
        self.assertEqual(mark_read_response.json()["updated"], 1)
