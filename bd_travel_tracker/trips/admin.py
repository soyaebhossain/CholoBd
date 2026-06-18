from django.contrib import admin
from django.utils import timezone

from .models import (
    Album,
    AlbumItem,
    CommunityComment,
    CommunityCommentEditHistory,
    Conversation,
    DirectConversation,
    DirectMessage,
    Message,
    MessageAttachment,
    CommunityNotification,
    CommunityMembership,
    CommunityPost,
    CommunityPostReaction,
    CommunityPostSave,
    District,
    Division,
    SavedSpot,
    Story,
    TourSpot,
    TravelHistory,
    Trip,
    TripReminder,
    Upazila,
    UserFollow,
    UserProfile,
)


@admin.register(Division)
class DivisionAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "district_count")
    search_fields = ("name",)

    def district_count(self, obj):
        return obj.districts.count()


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "division", "upazila_count")
    list_filter = ("division",)
    search_fields = ("name", "division__name")

    def upazila_count(self, obj):
        return obj.upazilas.count()


@admin.register(Upazila)
class UpazilaAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "district", "division", "spot_count")
    list_filter = ("district__division", "district")
    search_fields = ("name", "district__name", "district__division__name")

    def division(self, obj):
        return obj.district.division

    def spot_count(self, obj):
        return obj.spots.count()


@admin.register(TourSpot)
class TourSpotAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "upazila", "district", "division", "category")
    list_filter = ("upazila__district__division", "upazila__district", "upazila", "category")
    search_fields = ("name", "upazila__name", "upazila__district__name")

    def district(self, obj):
        return obj.upazila.district

    def division(self, obj):
        return obj.upazila.district.division


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "spot",
        "trip_source",
        "agency_name",
        "from_date",
        "to_date",
        "division",
        "district",
        "total_cost",
    )
    list_filter = ("division", "district", "upazila", "from_date")
    search_fields = ("user__username", "spot__name", "hotel_name", "notes")
    autocomplete_fields = ("user", "division", "district", "upazila", "spot")
    readonly_fields = ("total_cost", "created_at", "updated_at")


@admin.register(TripReminder)
class TripReminderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "title",
        "trip_source",
        "agency_name",
        "reminder_date",
        "reminder_time",
        "is_active",
    )
    list_filter = ("trip_source", "is_active", "reminder_date")
    search_fields = ("user__username", "title", "agency_name", "note")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "account_type",
        "agency_name",
        "company_verification_status",
        "full_name",
        "phone",
        "preferred_language",
        "theme_mode",
    )
    list_filter = (
        "account_type",
        "company_verification_status",
        "preferred_language",
        "theme_mode",
        "public_profile",
    )
    search_fields = ("user__username", "full_name", "phone", "agency_name", "agency_license_number")
    actions = ("approve_company_accounts", "reject_company_accounts")

    @admin.action(description="Approve selected company accounts")
    def approve_company_accounts(self, request, queryset):
        approved = 0
        for profile in queryset.filter(account_type="company"):
            profile.company_verification_status = "verified"
            profile.company_verified_at = timezone.now()
            profile.save(update_fields=["company_verification_status", "company_verified_at", "updated_at"])
            profile.user.is_active = True
            profile.user.save(update_fields=["is_active"])
            approved += 1
        self.message_user(request, f"Approved {approved} company account(s).")

    @admin.action(description="Reject selected company accounts")
    def reject_company_accounts(self, request, queryset):
        rejected = 0
        for profile in queryset.filter(account_type="company"):
            profile.company_verification_status = "rejected"
            profile.company_verified_at = None
            profile.save(update_fields=["company_verification_status", "company_verified_at", "updated_at"])
            profile.user.is_active = False
            profile.user.save(update_fields=["is_active"])
            rejected += 1
        self.message_user(request, f"Rejected {rejected} company account(s).")


class AlbumItemInline(admin.TabularInline):
    model = AlbumItem
    extra = 0
    fields = ("file", "external_url", "caption", "taken_at")


@admin.register(Album)
class AlbumAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "user", "trip_date", "spot", "external_source")
    list_filter = ("trip_date", "spot__upazila__district__division")
    search_fields = ("title", "user__username", "spot__name")
    inlines = [AlbumItemInline]


@admin.register(Story)
class StoryAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "user", "trip_date", "spot", "is_public")
    list_filter = ("is_public", "trip_date")
    search_fields = ("title", "content", "user__username")


@admin.register(TravelHistory)
class TravelHistoryAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "user", "place_name", "visit_date")
    list_filter = ("visit_date",)
    search_fields = ("title", "place_name", "short_note", "history_note")


@admin.register(SavedSpot)
class SavedSpotAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "spot", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__username", "spot__name", "note")


class CommunityCommentInline(admin.TabularInline):
    model = CommunityComment
    extra = 0
    fields = ("user", "content", "created_at", "edited_at")
    readonly_fields = ("created_at", "edited_at")


@admin.register(CommunityPost)
class CommunityPostAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "post_type", "user", "district", "spot", "is_resolved", "created_at")
    list_filter = ("post_type", "is_resolved", "created_at", "district")
    search_fields = ("title", "content", "hashtags", "location_name", "user__username", "spot__name")
    inlines = [CommunityCommentInline]


@admin.register(CommunityPostReaction)
class CommunityPostReactionAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "user", "reaction", "created_at")
    list_filter = ("reaction", "created_at")
    search_fields = ("post__title", "user__username")


@admin.register(CommunityPostSave)
class CommunityPostSaveAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "user", "created_at")
    list_filter = ("created_at",)
    search_fields = ("post__title", "user__username")


@admin.register(CommunityCommentEditHistory)
class CommunityCommentEditHistoryAdmin(admin.ModelAdmin):
    list_display = ("id", "comment", "edited_by", "created_at")
    list_filter = ("created_at",)
    search_fields = ("comment__content", "edited_by__username", "previous_content")


@admin.register(CommunityNotification)
class CommunityNotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "actor", "kind", "is_read", "created_at")
    list_filter = ("kind", "is_read", "created_at")
    search_fields = ("user__username", "actor__username", "message")


@admin.register(CommunityMembership)
class CommunityMembershipAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "is_active", "joined_at", "updated_at")
    list_filter = ("is_active", "joined_at")
    search_fields = ("user__username",)


@admin.register(UserFollow)
class UserFollowAdmin(admin.ModelAdmin):
    list_display = ("id", "follower", "following", "created_at")
    list_filter = ("created_at",)
    search_fields = ("follower__username", "following__username")


class DirectMessageInline(admin.TabularInline):
    model = DirectMessage
    extra = 0
    fields = ("sender", "body", "is_read", "created_at")
    readonly_fields = ("created_at",)


@admin.register(DirectConversation)
class DirectConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "user_one", "user_two", "updated_at", "created_at")
    list_filter = ("updated_at", "created_at")
    search_fields = ("user_one__username", "user_two__username")
    inlines = [DirectMessageInline]


@admin.register(DirectMessage)
class DirectMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "sender", "is_read", "created_at")
    list_filter = ("is_read", "created_at")
    search_fields = ("sender__username", "body")


class MessageAttachmentInline(admin.TabularInline):
    model = MessageAttachment
    extra = 0
    fields = ("file", "created_at")
    readonly_fields = ("created_at",)


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    fields = ("sender", "content", "is_read", "is_deleted", "created_at")
    readonly_fields = ("created_at",)


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "updated_at")
    filter_horizontal = ("participants",)
    list_filter = ("updated_at", "created_at")
    inlines = [MessageInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "sender", "is_read", "is_deleted", "created_at", "edited_at")
    list_filter = ("is_read", "is_deleted", "created_at")
    search_fields = ("sender__username", "content")
    inlines = [MessageAttachmentInline]


@admin.register(MessageAttachment)
class MessageAttachmentAdmin(admin.ModelAdmin):
    list_display = ("id", "message", "created_at")
    list_filter = ("created_at",)
