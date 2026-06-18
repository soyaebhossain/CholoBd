from django.contrib import messages
from collections import Counter
from datetime import datetime
import re

from django.contrib.auth import get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import IntegrityError, OperationalError, ProgrammingError
from django.db.models import Avg, Count, ExpressionWrapper, F, IntegerField, Q, Sum, Value
from django.http import JsonResponse
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateformat import format as date_format
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from django.conf import settings
from .forms import (
    AlbumForm,
    AlbumItemForm,
    CommunityCommentForm,
    CommunityPostForm,
    MessageForm,
    ProfileAvatarUploadForm,
    ProfileCoverUploadForm,
    RegisterForm,
    SavedSpotForm,
    StoryForm,
    TravelHistoryForm,
    TripForm,
    TripReminderForm,
    UserProfileForm,
)
from .settings_forms import (
    AccountSettingsForm,
    AppearanceSettingsForm,
    DangerZoneDeactivateForm,
    DangerZoneDeleteForm,
    NotificationSettingsForm,
    PrivacySettingsForm,
    ProfileSettingsSectionForm,
    SecuritySettingsForm,
)
from .settings_service import (
    build_settings_sidebar,
    get_or_create_settings_bundle,
    get_settings_section_meta,
    log_settings_change,
    normalize_settings_section,
)
from .models import (
    Album,
    CallSession,
    CommunityComment,
    CommunityCommentEditHistory,
    Conversation,
    CommunityMembership,
    CommunityNotification,
    CommunityPost,
    CommunityPostReaction,
    CommunityPostSave,
    CommunityPostView,
    CommunityTag,
    Message,
    MessageAttachment,
    District,
    Division,
    SavedSpot,
    Story,
    TourSpot,
    TravelHistory,
    Trip,
    TripReminder,
    Upazila,
    UserCommunitySettings,
    UserFollow,
    UserNotificationSettings,
    UserProfile,
)


COMMUNITY_REACTION_CHOICES = [
    {"key": "like", "label": "Like", "emoji": "👍", "color": "like"},
    {"key": "love", "label": "Love", "emoji": "❤️", "color": "love"},
    {"key": "care", "label": "Care", "emoji": "🤗", "color": "care"},
    {"key": "wow", "label": "Wow", "emoji": "😮", "color": "wow"},
    {"key": "helpful", "label": "Helpful", "emoji": "💡", "color": "helpful"},
]
COMMUNITY_REACTION_META = {
    item["key"]: item
    for item in COMMUNITY_REACTION_CHOICES
}


def _get_community_reaction_meta(reaction_key):
    fallback = COMMUNITY_REACTION_META["like"]
    if not reaction_key:
        return fallback
    return COMMUNITY_REACTION_META.get(reaction_key, fallback)


def _serialize_community_reaction_counts(counter):
    items = []
    for reaction in COMMUNITY_REACTION_CHOICES:
        count = counter.get(reaction["key"], 0)
        if count:
            items.append({**reaction, "count": count})
    return items


def _get_or_create_profile(user):
    try:
        return user.profile
    except UserProfile.DoesNotExist:
        return UserProfile.objects.create(user=user)


def _needs_profile_completion(user):
    if not user.is_authenticated:
        return False

    profile = _get_or_create_profile(user)
    return not profile.is_profile_complete


def _allows_profile_preview(viewer, target_user, profile=None):
    if viewer.is_authenticated and (
        viewer.id == target_user.id or viewer.is_staff or viewer.is_superuser
    ):
        return True

    target_profile = profile or _get_or_create_profile(target_user)
    return bool(target_profile.public_profile)


def _allows_community_updates(user, profile=None):
    target_profile = profile or _get_or_create_profile(user)
    return bool(target_profile.receive_community_updates)


def _get_notification_settings(user):
    return UserNotificationSettings.objects.get_or_create(user=user)[0]


def _should_create_notification(user, preference_name, profile=None):
    if not _allows_community_updates(user, profile=profile):
        return False
    settings = _get_notification_settings(user)
    return bool(settings.community_updates and getattr(settings, preference_name, True))


def _is_user_online(user, profile=None):
    target_profile = profile or _get_or_create_profile(user)
    return bool(
        target_profile.last_active_at
        and target_profile.last_active_at >= timezone.now() - timezone.timedelta(minutes=5)
    )


def _is_following_user(viewer, target_user):
    if not viewer.is_authenticated or viewer.id == target_user.id:
        return False
    return UserFollow.objects.filter(
        follower=viewer,
        following=target_user,
    ).exists()


def _allows_direct_message(viewer, target_user, profile=None, community_settings=None):
    if not viewer.is_authenticated or viewer.id == target_user.id:
        return False

    target_profile = profile or _get_or_create_profile(target_user)
    if not target_profile.allow_dm:
        return False

    target_community_settings = (
        community_settings
        or UserCommunitySettings.objects.get_or_create(user=target_user)[0]
    )
    message_rule = target_community_settings.who_can_message

    if message_rule == "no_one":
        return False
    if message_rule == "everyone":
        return True
    if message_rule == "followers":
        return _is_following_user(viewer, target_user)
    if message_rule == "community":
        return (
            CommunityMembership.objects.filter(user=viewer, is_active=True).exists()
            and CommunityMembership.objects.filter(user=target_user, is_active=True).exists()
        )
    return False


def _ordered_user_pair(user_a, user_b):
    if user_a.id == user_b.id:
        raise ValueError("Users must be different.")
    if user_a.id < user_b.id:
        return user_a, user_b
    return user_b, user_a


def _get_or_create_direct_conversation(user_a, user_b):
    existing = (
        Conversation.objects.annotate(participant_total=Count("participants", distinct=True))
        .filter(participant_total=2, participants=user_a)
        .filter(participants=user_b)
        .first()
    )
    if existing:
        return existing, False

    conversation = Conversation.objects.create()
    conversation.participants.set([user_a, user_b])
    return conversation, True


def _conversation_belongs_to_user(conversation, user):
    return conversation.participants.filter(id=user.id).exists()


def _get_conversation_partner(conversation, user):
    return conversation.participants.exclude(id=user.id).first()


def _message_rate_limited(user):
    return (
        Message.objects.filter(
            sender=user,
            created_at__gte=timezone.now() - timezone.timedelta(seconds=15),
        ).count()
        >= 5
    )


def _serialize_attachment(attachment):
    return {
        "id": attachment.id,
        "kind": attachment.kind,
        "url": attachment.file.url,
        "name": attachment.file.name.rsplit("/", 1)[-1],
    }


def _serialize_message(message, viewer):
    return {
        "id": message.id,
        "sender_id": message.sender_id,
        "sender_name": message.sender.profile.full_name or message.sender.username,
        "content": "" if message.is_deleted else message.content,
        "is_read": message.is_read,
        "is_deleted": message.is_deleted,
        "created_at": message.created_at.isoformat(),
        "created_label": date_format(timezone.localtime(message.created_at), "M j, Y P"),
        "is_mine": message.sender_id == viewer.id,
        "attachments": [_serialize_attachment(item) for item in message.attachments.all()],
    }


def _find_direct_conversation(user_a, user_b):
    if not user_a or not user_b or user_a.id == user_b.id:
        return None
    return (
        Conversation.objects.annotate(participant_total=Count("participants", distinct=True))
        .filter(participant_total=2, participants=user_a)
        .filter(participants=user_b)
        .first()
    )


def _notification_target_url(note):
    if note.kind == "follow" and note.actor_id:
        return reverse("traveler_profile", args=[note.actor_id])

    if note.kind in {"comment", "answer", "post_reply", "mention"} and note.post_id:
        return f"{reverse('community')}#comments-{note.post_id}"

    if note.kind == "like" and note.post_id:
        return f"{reverse('community')}#post-{note.post_id}"

    if note.kind == "call":
        conversation = note.conversation
        call_session = (
            CallSession.objects.filter(
                conversation=conversation,
                status__in=["pending", "accepted"],
            )
            .filter(Q(initiator=note.user) | Q(recipient=note.user))
            .order_by("-created_at")
            .first()
        )
        if call_session and call_session.status == "accepted":
            return reverse("direct_call_room", args=[call_session.id])

    if note.kind in {"direct_message", "call"}:
        conversation = note.conversation
        if not conversation and note.actor_id:
            conversation = _find_direct_conversation(note.user, note.actor)
        if conversation:
            return f"{reverse('direct_messages')}?conversation={conversation.id}"
        if note.actor_id:
            return reverse("direct_message_start", args=[note.actor_id])
    if note.post_id:
        return f"{reverse('community')}#post-{note.post_id}"
    if note.actor_id:
        return reverse("traveler_profile", args=[note.actor_id])
    return reverse("community")


def _call_session_belongs_to_user(call_session, user):
    return user.id in {call_session.initiator_id, call_session.recipient_id}


def _get_conversation_active_call(conversation, user):
    if not conversation:
        return None
    return (
        CallSession.objects.filter(
            conversation=conversation,
            status__in=["pending", "accepted"],
        )
        .filter(Q(initiator=user) | Q(recipient=user))
        .select_related("initiator__profile", "recipient__profile", "conversation")
        .order_by("-created_at")
        .first()
    )


def _build_call_room_url(call_session):
    start_with_video_muted = "false" if call_session.mode == "video" else "true"
    return (
        f"https://meet.jit.si/{call_session.room_name}"
        f"#config.prejoinPageEnabled=false"
        f"&config.startWithVideoMuted={start_with_video_muted}"
        f"&config.startWithAudioMuted=false"
    )


def _decorate_notification(note):
    actor_profile = getattr(note.actor, "profile", None) if note.actor else None
    note.actor_avatar = actor_profile.avatar if actor_profile and actor_profile.avatar else ""
    note.actor_name = (
        actor_profile.full_name
        if actor_profile and actor_profile.full_name
        else (note.actor.username if note.actor else "System")
    )
    note.actor_is_online = bool(note.actor and actor_profile and _is_user_online(note.actor, actor_profile))
    note.target_url = _notification_target_url(note)
    return note


def _build_relationship_context(viewer, target_user, profile=None, community_settings=None):
    target_profile = profile or _get_or_create_profile(target_user)
    follower_count = UserFollow.objects.filter(following=target_user).count()
    following_count = UserFollow.objects.filter(follower=target_user).count()
    is_self = viewer.is_authenticated and viewer.id == target_user.id
    is_following = _is_following_user(viewer, target_user)
    can_follow = viewer.is_authenticated and not is_self
    can_message = _allows_direct_message(
        viewer,
        target_user,
        profile=target_profile,
        community_settings=community_settings,
    )

    return {
        "is_self": is_self,
        "can_follow": can_follow,
        "is_following": is_following,
        "follower_count": follower_count,
        "following_count": following_count,
        "can_message": can_message,
        "profile_url": reverse("traveler_profile", args=[target_user.id]),
        "message_url": reverse("direct_message_start", args=[target_user.id]),
    }


def _capture_comment_state(comment):
    return {
        "content": comment.content or "",
        "image_file": comment.image_file.name if comment.image_file else "",
        "audio_file": comment.audio_file.name if comment.audio_file else "",
        "video_file": comment.video_file.name if comment.video_file else "",
    }


def _comment_has_changes(original_state, cleaned_data):
    return any(
        [
            (original_state["content"]) != (cleaned_data.get("content") or ""),
            (original_state["image_file"]) != (
                cleaned_data.get("image_file").name if cleaned_data.get("image_file") else ""
            ),
            (original_state["audio_file"]) != (
                cleaned_data.get("audio_file").name if cleaned_data.get("audio_file") else ""
            ),
            (original_state["video_file"]) != (
                cleaned_data.get("video_file").name if cleaned_data.get("video_file") else ""
            ),
        ]
    )


def _create_comment_history_snapshot(comment, editor, original_state):
    CommunityCommentEditHistory.objects.create(
        comment=comment,
        edited_by=editor,
        previous_content=original_state["content"],
        previous_image_file=original_state["image_file"] or None,
        previous_audio_file=original_state["audio_file"] or None,
        previous_video_file=original_state["video_file"] or None,
    )


def _build_trip_overview_context(trips):
    summary = trips.aggregate(
        total_trips=Count("id"),
        total_spent=Sum("total_cost"),
        visited_divisions=Count("division", distinct=True),
        visited_districts=Count("district", distinct=True),
        visited_spots=Count("spot", distinct=True),
    )

    total_trips = summary["total_trips"] or 0
    total_spent = summary["total_spent"] or 0
    visited_districts = summary["visited_districts"] or 0

    top_district_row = (
        trips.values("district__name")
        .annotate(total=Count("id"))
        .order_by("-total", "district__name")
        .first()
    )
    top_district = top_district_row["district__name"] if top_district_row else None
    average_trip_cost = (total_spent / total_trips) if total_trips else 0

    if total_trips == 0:
        cta_title = "Start Your Journey"
        cta_text = "Add your first trip to unlock personal analytics and travel goals."
        cta_button = "Add First Trip"
        cta_url_name = "trip_create"
    elif visited_districts < 5:
        cta_title = "Explore More Districts"
        cta_text = f"You explored {visited_districts} district(s). Next target: a new district this month."
        cta_button = "Open Travel Map"
        cta_url_name = "travel_map"
    else:
        cta_title = "Personal Insight"
        cta_text = f"Avg cost/trip: Tk {average_trip_cost:.0f}. Most visits: {top_district or 'N/A'}."
        cta_button = "Add Next Trip"
        cta_url_name = "trip_create"

    return {
        "total_trips": total_trips,
        "total_spent": total_spent,
        "visited_divisions": summary["visited_divisions"] or 0,
        "visited_districts": visited_districts,
        "visited_spots": summary["visited_spots"] or 0,
        "cta_title": cta_title,
        "cta_text": cta_text,
        "cta_button": cta_button,
        "cta_url_name": cta_url_name,
    }


def _build_next_trip_route_context(reminder):
    if not reminder or not reminder.spot_id:
        return None

    spot = reminder.spot
    return {
        "title": reminder.title,
        "spot_name": spot.name,
        "division": spot.division.name,
        "district": spot.district.name,
        "upazila": spot.upazila.name,
        "latitude": float(spot.latitude) if spot.latitude is not None else None,
        "longitude": float(spot.longitude) if spot.longitude is not None else None,
        "destination_query": f"{spot.name}, {spot.upazila.name}, {spot.district.name}, Bangladesh",
    }


class TravelLoginView(LoginView):
    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        if _needs_profile_completion(self.request.user):
            return "/profile/"
        redirect_to = self.get_redirect_url()
        return redirect_to or "/"

    def form_invalid(self, form):
        username = (self.request.POST.get("username") or "").strip()
        if username:
            candidate = (
                get_user_model()
                .objects.filter(username__iexact=username)
                .select_related("profile")
                .first()
            )
            if (
                candidate
                and not candidate.is_active
                and hasattr(candidate, "profile")
                and candidate.profile.account_type == "company"
                and candidate.profile.company_verification_status == "pending"
            ):
                messages.error(
                    self.request,
                    "Company account is pending verification. We will activate login access after review.",
                )
        return super().form_invalid(form)


def home(request):
    try:
        trip_summary = Trip.objects.aggregate(
            total_trips=Count("id"),
            explored_districts=Count("district", distinct=True),
            spots_visited=Count("spot", distinct=True),
            total_spent=Sum("total_cost"),
            transport_total=Sum("transport_cost"),
            food_total=Sum("food_cost"),
            hotel_total=Sum("hotel_cost"),
            ticket_total=Sum("ticket_cost"),
            other_total=Sum("other_cost"),
        )

        featured_spots = (
            TourSpot.objects.select_related("upazila__district")
            .annotate(total_visits=Count("trips"))
            .order_by("-total_visits", "name")[:3]
        )
        top_districts_footer = (
            Trip.objects.values("district__name")
            .annotate(total=Count("id"))
            .order_by("-total", "district__name")[:4]
        )
        top_spots_footer = (
            Trip.objects.values("spot__name")
            .annotate(total=Count("id"))
            .order_by("-total", "spot__name")[:4]
        )
        traveler_count = get_user_model().objects.count()
        spot_count = TourSpot.objects.count()
        division_count = Division.objects.count()
        district_count = District.objects.count()
        upazila_count = Upazila.objects.count()
        all_districts = District.objects.select_related("division").order_by("name")
    except (OperationalError, ProgrammingError):
        trip_summary = {
            "total_trips": 0,
            "explored_districts": 0,
            "spots_visited": 0,
            "total_spent": 0,
            "transport_total": 0,
            "food_total": 0,
            "hotel_total": 0,
            "ticket_total": 0,
            "other_total": 0,
        }
        featured_spots = []
        top_districts_footer = []
        top_spots_footer = []
        traveler_count = 0
        spot_count = 0
        division_count = 0
        district_count = 0
        upazila_count = 0
        all_districts = []

    context = {
        "total_trips": trip_summary["total_trips"] or 0,
        "explored_districts": trip_summary["explored_districts"] or 0,
        "spots_visited": trip_summary["spots_visited"] or 0,
        "total_spent": trip_summary["total_spent"] or 0,
        "traveler_count": traveler_count,
        "spot_count": spot_count,
        "featured_spots": featured_spots,
        "top_districts_footer": top_districts_footer,
        "top_spots_footer": top_spots_footer,
        "division_count": division_count,
        "district_count": district_count,
        "upazila_count": upazila_count,
        "all_districts": all_districts,
        "current_year": timezone.now().year,
        "expense_breakdown": {
            "Transport": float(trip_summary["transport_total"] or 0),
            "Food": float(trip_summary["food_total"] or 0),
            "Hotel": float(trip_summary["hotel_total"] or 0),
            "Ticket": float(trip_summary["ticket_total"] or 0),
            "Other": float(trip_summary["other_total"] or 0),
        },
    }
    return render(request, "home.html", context)


def account_entry(request):
    if request.user.is_authenticated:
        if _needs_profile_completion(request.user):
            return redirect("profile")
        return redirect("home")
    return redirect("login")


def register_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            if user.profile.account_type == "company":
                messages.success(
                    request,
                    "Company account created. Login will be enabled after agency verification is completed.",
                )
                return redirect("login")
            login(request, user)
            return redirect("profile")
    else:
        form = RegisterForm()

    return render(request, "registration/register.html", {"form": form})


DESTINATION_CATEGORY_META = [
    {
        "key": "beaches",
        "label": "Beaches",
        "icon": "bi-water",
        "keywords": ("beach", "sea", "coast", "marine", "shore"),
    },
    {
        "key": "nature",
        "label": "Nature",
        "icon": "bi-flower1",
        "keywords": ("nature", "forest", "garden", "lake", "waterfall", "eco", "zoo"),
    },
    {
        "key": "historical",
        "label": "Historical",
        "icon": "bi-bank",
        "keywords": ("historic", "historical", "museum", "monument", "fort", "palace", "heritage"),
    },
    {
        "key": "religious",
        "label": "Religious",
        "icon": "bi-stars",
        "keywords": ("mosque", "temple", "church", "shrine", "religious", "monastery", "mazar"),
    },
    {
        "key": "hills",
        "label": "Hills",
        "icon": "bi-triangle",
        "keywords": ("hill", "mountain", "valley", "peak"),
    },
    {
        "key": "camps",
        "label": "Camps",
        "icon": "bi-backpack3",
        "keywords": ("camp", "camping", "resort", "eco park"),
    },
    {
        "key": "parks",
        "label": "Parks",
        "icon": "bi-tree",
        "keywords": ("park", "national park", "theme park", "recreation"),
    },
    {
        "key": "islands",
        "label": "Islands",
        "icon": "bi-globe-central-south-asia",
        "keywords": ("island", "char"),
    },
]

DEFAULT_DESTINATION_CATEGORY = {
    "key": "landmarks",
    "label": "Landmarks",
    "icon": "bi-compass",
}

DESTINATION_SORT_CHOICES = {
    "popular": "Most Visited",
    "score": "Traveler Score",
    "name": "Name A-Z",
}


def _normalize_destination_category(raw_category):
    category_value = (raw_category or "").strip().lower()
    for meta in DESTINATION_CATEGORY_META:
        if any(keyword in category_value for keyword in meta["keywords"]):
            return meta
    return DEFAULT_DESTINATION_CATEGORY


def _build_destination_score(total_visits, unique_visitors, saved_count):
    activity_boost = min(
        1.2,
        (min(total_visits, 20) * 0.03)
        + (min(unique_visitors, 15) * 0.04)
        + (min(saved_count, 10) * 0.03),
    )
    return round(3.7 + activity_boost, 1)


def _build_destination_filter_url(request, **updates):
    params = request.GET.copy()
    for key, value in updates.items():
        if value in ("", None):
            params.pop(key, None)
        else:
            params[key] = value
    query_string = params.urlencode()
    if not query_string:
        return request.path
    return f"{request.path}?{query_string}"


def _build_destination_card_data(spot, saved_ids):
    category_meta = _normalize_destination_category(spot.category)
    saved_count = getattr(spot, "saved_count", 0) or 0
    total_visits = getattr(spot, "total_visits", 0) or 0
    unique_visitors = getattr(spot, "unique_visitors", 0) or 0
    my_visits = getattr(spot, "my_visits", 0) or 0

    return {
        "id": spot.id,
        "name": spot.name,
        "description": spot.description,
        "summary": (
            spot.description
            or f"Explore {spot.name} in {spot.upazila.name}, {spot.district.name}."
        ),
        "category": spot.category or "Destination",
        "category_key": category_meta["key"],
        "category_label": category_meta["label"],
        "category_icon": category_meta["icon"],
        "division": spot.division.name,
        "district": spot.district.name,
        "upazila": spot.upazila.name,
        "latitude": float(spot.latitude) if spot.latitude is not None else None,
        "longitude": float(spot.longitude) if spot.longitude is not None else None,
        "has_coordinates": spot.latitude is not None and spot.longitude is not None,
        "total_visits": total_visits,
        "unique_visitors": unique_visitors,
        "saved_count": saved_count,
        "my_visits": my_visits,
        "traveler_score": _build_destination_score(total_visits, unique_visitors, saved_count),
        "is_saved": spot.id in saved_ids,
        "detail_url": reverse("destination_detail", args=[spot.id]),
        "trip_url": (
            f"{reverse('trip_create')}?division={spot.division.id}"
            f"&district={spot.district.id}&upazila={spot.upazila.id}&spot={spot.id}"
        ),
    }


def _safe_redirect_url(request, fallback_name):
    next_url = (request.POST.get("next") or request.GET.get("next") or "").strip()
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return reverse(fallback_name)


@login_required
def destinations(request):
    search_query = request.GET.get("q", "").strip()
    selected_division = request.GET.get("division", "").strip()
    selected_district = request.GET.get("district", "").strip()
    selected_upazila = request.GET.get("upazila", "").strip()
    selected_category = request.GET.get("category", "").strip()
    selected_sort = request.GET.get("sort", "popular").strip()
    if selected_sort not in DESTINATION_SORT_CHOICES:
        selected_sort = "popular"

    overall_queryset = (
        TourSpot.objects.select_related("upazila__district__division")
        .annotate(
            total_visits=Count("trips"),
            unique_visitors=Count("trips__user", distinct=True),
            saved_count=Count("saved_by_users", distinct=True),
            my_visits=Count("trips", filter=Q(trips__user=request.user)),
        )
    )

    spot_queryset = overall_queryset
    if search_query:
        spot_queryset = spot_queryset.filter(
            Q(name__icontains=search_query)
            | Q(description__icontains=search_query)
            | Q(category__icontains=search_query)
            | Q(upazila__name__icontains=search_query)
            | Q(upazila__district__name__icontains=search_query)
            | Q(upazila__district__division__name__icontains=search_query)
        )

    if selected_division.isdigit():
        spot_queryset = spot_queryset.filter(upazila__district__division_id=int(selected_division))
    else:
        selected_division = ""

    if selected_district.isdigit():
        spot_queryset = spot_queryset.filter(upazila__district_id=int(selected_district))
    else:
        selected_district = ""

    if selected_upazila.isdigit():
        spot_queryset = spot_queryset.filter(upazila_id=int(selected_upazila))
    else:
        selected_upazila = ""

    spots = list(spot_queryset)
    saved_ids = set(
        SavedSpot.objects.filter(user=request.user, spot_id__in=[spot.id for spot in spots]).values_list(
            "spot_id",
            flat=True,
        )
    )
    all_destination_rows = [_build_destination_card_data(spot, saved_ids) for spot in spots]

    category_counts = {}
    for row in all_destination_rows:
        category_counts[row["category_key"]] = category_counts.get(row["category_key"], 0) + 1

    filtered_destination_rows = all_destination_rows
    if selected_category:
        filtered_destination_rows = [
            row for row in filtered_destination_rows if row["category_key"] == selected_category
        ]

    if selected_sort == "name":
        filtered_destination_rows.sort(key=lambda row: row["name"].lower())
    elif selected_sort == "score":
        filtered_destination_rows.sort(
            key=lambda row: (-row["traveler_score"], -row["total_visits"], row["name"].lower())
        )
    else:
        filtered_destination_rows.sort(
            key=lambda row: (-row["total_visits"], -row["unique_visitors"], row["name"].lower())
        )

    result_count = len(filtered_destination_rows)
    mapped_filtered_count = sum(1 for row in filtered_destination_rows if row["has_coordinates"])
    top_map_rows = [
        {
            "id": row["id"],
            "name": row["name"],
            "division": row["division"],
            "district": row["district"],
            "upazila": row["upazila"],
            "category": row["category_label"],
            "total_visits": row["total_visits"],
            "traveler_score": row["traveler_score"],
            "is_saved": row["is_saved"],
            "my_visits": row["my_visits"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "detail_url": row["detail_url"],
            "trip_url": row["trip_url"],
        }
        for row in filtered_destination_rows
        if row["has_coordinates"]
    ][:200]

    trending_rows = sorted(
        filtered_destination_rows,
        key=lambda row: (-row["total_visits"], -row["traveler_score"], row["name"].lower()),
    )[:5]

    category_chip_lookup = {
        meta["key"]: meta for meta in DESTINATION_CATEGORY_META
    }
    all_count = len(all_destination_rows)
    category_chips = [
        {
            "key": "",
            "label": "All",
            "icon": "bi-grid-3x3-gap",
            "count": all_count,
            "is_active": not selected_category,
            "url": _build_destination_filter_url(request, category=""),
        }
    ]
    for category_key, count in sorted(
        category_counts.items(),
        key=lambda item: (-item[1], category_chip_lookup.get(item[0], DEFAULT_DESTINATION_CATEGORY)["label"]),
    ):
        meta = category_chip_lookup.get(category_key, DEFAULT_DESTINATION_CATEGORY)
        category_chips.append(
            {
                "key": category_key,
                "label": meta["label"],
                "icon": meta["icon"],
                "count": count,
                "is_active": selected_category == category_key,
                "url": _build_destination_filter_url(request, category=category_key),
            }
        )

    top_spot = (
        overall_queryset.order_by("-total_visits", "-unique_visitors", "name").first()
    )
    district_options = (
        District.objects.filter(division_id=selected_division).order_by("name")
        if selected_division
        else District.objects.none()
    )
    upazila_options = (
        Upazila.objects.filter(district_id=selected_district).order_by("name")
        if selected_district
        else Upazila.objects.none()
    )

    context = {
        "spot_count": TourSpot.objects.count(),
        "mapped_spot_count": TourSpot.objects.filter(
            latitude__isnull=False,
            longitude__isnull=False,
        ).count(),
        "district_count": District.objects.count(),
        "community_trip_count": Trip.objects.count(),
        "top_spot_name": top_spot.name if top_spot else "Not enough data",
        "top_spot_visits": getattr(top_spot, "total_visits", 0) if top_spot else 0,
        "search_query": search_query,
        "selected_division": selected_division,
        "selected_district": selected_district,
        "selected_upazila": selected_upazila,
        "selected_category": selected_category,
        "selected_sort": selected_sort,
        "sort_choices": DESTINATION_SORT_CHOICES.items(),
        "division_options": Division.objects.order_by("name"),
        "district_options": district_options,
        "upazila_options": upazila_options,
        "category_chips": category_chips[:9],
        "result_count": result_count,
        "destination_rows": filtered_destination_rows[:18],
        "map_spots_json": top_map_rows,
        "map_preview_count": len(top_map_rows),
        "has_more_map_results": mapped_filtered_count > len(top_map_rows),
        "trending_rows": trending_rows,
        "reset_url": request.path,
    }
    return render(request, "trips/destinations.html", context)


@login_required
def destination_detail(request, spot_id):
    spot = get_object_or_404(
        TourSpot.objects.select_related("upazila__district__division")
        .annotate(
            total_visits=Count("trips"),
            unique_visitors=Count("trips__user", distinct=True),
            saved_count=Count("saved_by_users", distinct=True),
            my_visits=Count("trips", filter=Q(trips__user=request.user)),
        )
        .order_by("name"),
        id=spot_id,
    )

    saved_ids = set(
        SavedSpot.objects.filter(user=request.user, spot_id=spot.id).values_list("spot_id", flat=True)
    )
    destination = _build_destination_card_data(spot, saved_ids)

    recent_trips = (
        Trip.objects.filter(spot=spot)
        .select_related("user")
        .order_by("-from_date", "-created_at")[:5]
    )
    travel_tips = (
        Trip.objects.filter(spot=spot)
        .exclude(notes="")
        .select_related("user")
        .order_by("-from_date", "-created_at")[:3]
    )
    community_posts = (
        CommunityPost.objects.filter(Q(spot=spot) | Q(location_name__icontains=spot.name))
        .select_related("user")
        .annotate(comment_count=Count("comments", distinct=True), reaction_count=Count("reactions", distinct=True))
        .order_by("-created_at")[:4]
    )
    photo_posts = (
        CommunityPost.objects.filter(spot=spot, image_file__isnull=False)
        .exclude(image_file="")
        .order_by("-created_at")[:4]
    )
    nearby_spots = list(
        TourSpot.objects.select_related("upazila__district__division")
        .filter(upazila__district=spot.district)
        .exclude(id=spot.id)
        .annotate(
            total_visits=Count("trips"),
            unique_visitors=Count("trips__user", distinct=True),
            saved_count=Count("saved_by_users", distinct=True),
            my_visits=Count("trips", filter=Q(trips__user=request.user)),
        )
        .order_by("-total_visits", "name")[:6]
    )
    nearby_saved_ids = set(
        SavedSpot.objects.filter(
            user=request.user,
            spot_id__in=[item.id for item in nearby_spots],
        ).values_list("spot_id", flat=True)
    )

    context = {
        "destination": destination,
        "photo_posts": photo_posts,
        "travel_tips": travel_tips,
        "recent_trips": recent_trips,
        "community_posts": community_posts,
        "nearby_rows": [_build_destination_card_data(item, nearby_saved_ids) for item in nearby_spots],
        "detail_map_json": {
            "name": destination["name"],
            "latitude": destination["latitude"],
            "longitude": destination["longitude"],
            "detail_url": destination["detail_url"],
        },
    }
    return render(request, "trips/destination_detail.html", context)


def _extract_mentions(text):
    if not text:
        return []
    return list(set(re.findall(r"@([a-zA-Z0-9_.-]{3,150})", text)))


def _notify_mentions(actor, post, text):
    usernames = _extract_mentions(text)
    if not usernames:
        return
    User = get_user_model()
    targets = User.objects.filter(username__in=usernames).exclude(id=actor.id)
    for target in targets:
        if not _allows_community_updates(target):
            continue
        CommunityNotification.objects.create(
            user=target,
            actor=actor,
            post=post,
            kind="mention",
            message=f"{actor.username} mentioned you in a community post.",
        )


@login_required
def community(request):
    if request.user.is_authenticated:
        membership, created = CommunityMembership.objects.get_or_create(
            user=request.user,
            defaults={"is_active": True},
        )
        if not created and not membership.is_active:
            membership.is_active = True
            membership.save(update_fields=["is_active", "updated_at"])

    feed_filter = request.GET.get("feed", "latest")
    search = request.GET.get("q", "").strip()
    filter_type = request.GET.get("type", "").strip()
    filter_hashtag = request.GET.get("hashtag", "").strip()
    filter_location = request.GET.get("location", "").strip()
    author_filter = request.GET.get("author", "").strip()

    trip_aggregate = Trip.objects.aggregate(
        total_trips=Count("id"),
        total_spent=Sum("total_cost"),
        total_visitors=Count("user", distinct=True),
        total_spots=Count("spot", distinct=True),
    )

    posts_qs = (
        CommunityPost.objects.select_related("user", "user__profile", "district", "spot")
        .prefetch_related("comments__user", "comments__history_entries__edited_by", "reactions", "saves")
        .annotate(
            comment_count=Count("comments", distinct=True),
            like_count=Count("reactions", distinct=True),
            save_count=Count("saves", distinct=True),
        )
    )

    if filter_type:
        posts_qs = posts_qs.filter(post_type=filter_type)

    if author_filter == "me" and request.user.is_authenticated:
        posts_qs = posts_qs.filter(user=request.user)

    if filter_hashtag:
        normalized_tag = filter_hashtag if filter_hashtag.startswith("#") else f"#{filter_hashtag}"
        posts_qs = posts_qs.filter(hashtags__icontains=normalized_tag)

    if filter_location:
        posts_qs = posts_qs.filter(
            Q(location_name__icontains=filter_location)
            | Q(district__name__icontains=filter_location)
            | Q(spot__name__icontains=filter_location)
        )

    if search:
        posts_qs = posts_qs.filter(
            Q(title__icontains=search)
            | Q(content__icontains=search)
            | Q(location_name__icontains=search)
            | Q(hashtags__icontains=search)
            | Q(spot__name__icontains=search)
            | Q(district__name__icontains=search)
        )

    if feed_filter == "most_helpful":
        posts_qs = posts_qs.order_by("-comment_count", "-like_count", "-created_at")
    elif feed_filter == "trending":
        posts_qs = posts_qs.order_by("-like_count", "-comment_count", "-created_at")
    elif feed_filter == "unanswered":
        posts_qs = posts_qs.filter(post_type="travel_question", comment_count=0).order_by("-created_at")
    elif feed_filter == "popular":
        posts_qs = posts_qs.filter(comment_count__gt=0).order_by("-comment_count", "-created_at")
    elif feed_filter == "saved" and request.user.is_authenticated:
        saved_ids = CommunityPostSave.objects.filter(user=request.user).values_list("post_id", flat=True)
        posts_qs = posts_qs.filter(id__in=saved_ids).order_by("-created_at")
    elif feed_filter == "media":
        posts_qs = posts_qs.filter(
            Q(image_file__isnull=False)
            | Q(video_file__isnull=False)
            | Q(audio_file__isnull=False)
        ).order_by("-created_at")
    else:
        posts_qs = posts_qs.order_by("-created_at")

    posts = list(posts_qs[:25])
    post_ids = [post.id for post in posts]

    liked_post_ids = set()
    saved_post_ids = set()
    if request.user.is_authenticated and post_ids:
        liked_post_ids = set(
            CommunityPostReaction.objects.filter(
                user=request.user,
                post_id__in=post_ids,
            ).values_list("post_id", flat=True)
        )
        saved_post_ids = set(
            CommunityPostSave.objects.filter(
                user=request.user,
                post_id__in=post_ids,
            ).values_list("post_id", flat=True)
        )

    author_ids = {post.user_id for post in posts}
    author_trip_rows = (
        Trip.objects.filter(user_id__in=author_ids)
        .values("user_id")
        .annotate(
            trips_completed=Count("id"),
            visited_districts=Count("district", distinct=True),
        )
    )
    author_trip_map = {
        row["user_id"]: {
            "trips_completed": row["trips_completed"],
            "visited_districts": row["visited_districts"],
        }
        for row in author_trip_rows
    }

    for post in posts:
        stats = author_trip_map.get(post.user_id, {"trips_completed": 0, "visited_districts": 0})
        contributions = (post.comment_count or 0) + (post.like_count or 0)
        try:
            author_profile = post.user.profile
        except UserProfile.DoesNotExist:
            author_profile = None
        can_view_profile = _allows_profile_preview(request.user, post.user, author_profile)
        post.author_trips_completed = stats["trips_completed"]
        post.author_visited_districts = stats["visited_districts"]
        post.author_reputation = (stats["trips_completed"] * 2) + contributions
        post.is_liked_by_me = post.id in liked_post_ids
        post.is_saved_by_me = post.id in saved_post_ids
        post.hashtag_tokens = post.hashtags_list
        post.author_name = (
            author_profile.full_name
            if can_view_profile and author_profile and author_profile.full_name
            else post.user.username
        )
        post.author_avatar = (
            author_profile.avatar
            if can_view_profile and author_profile and author_profile.avatar
            else ""
        )
        post.author_is_online = (
            can_view_profile and author_profile and _is_user_online(post.user, author_profile)
        )
        post.can_view_profile = can_view_profile
        for comment in post.comments.all():
            comment.can_edit = request.user.is_authenticated and comment.user_id == request.user.id
            comment.edit_form = CommunityCommentForm(instance=comment, prefix=f"comment-{comment.id}")

    contributor_rows = (
        get_user_model()
        .objects.annotate(
            post_count=Count("community_posts", distinct=True),
            comment_count=Count("community_comments", distinct=True),
        )
        .filter(Q(post_count__gt=0) | Q(comment_count__gt=0))
        .order_by("-post_count", "-comment_count", "username")[:6]
    )
    contributor_rows = list(contributor_rows)
    for person in contributor_rows:
        person.can_view_profile = _allows_profile_preview(request.user, person, person.profile)
        person.is_online = _is_user_online(person, person.profile)

    recent_media = (
        CommunityPost.objects.exclude(image_file="")
        .exclude(image_file__isnull=True)
        .order_by("-created_at")[:6]
    )
    popular_spots = (
        CommunityPost.objects.exclude(spot__isnull=True)
        .values("spot__name")
        .annotate(total=Count("id"))
        .order_by("-total", "spot__name")[:6]
    )

    membership_base_qs = CommunityMembership.objects.filter(is_active=True)
    member_rows = list(
        membership_base_qs.select_related("user__profile")
        .annotate(
            post_count=Count("user__community_posts", distinct=True),
            trip_count=Count("user__trips", distinct=True),
        )
        .order_by("-joined_at")[:12]
    )
    for membership in member_rows:
        membership.can_view_profile = _allows_profile_preview(
            request.user,
            membership.user,
            membership.user.profile,
        )
        membership.is_online = _is_user_online(membership.user, membership.user.profile)
    community_stats = {
        "members": membership_base_qs.count(),
        "online_members": membership_base_qs.filter(
            user__profile__last_active_at__gte=timezone.now() - timezone.timedelta(minutes=5)
        ).count(),
        "posts_today": CommunityPost.objects.filter(created_at__date=timezone.localdate()).count(),
        "trips_shared": trip_aggregate["total_trips"] or 0,
    }

    upcoming_events = [
        {"title": "Weekend Budget Planning", "date": "2026-03-14", "place": "Dhaka (Online)"},
        {"title": "Cox's Bazar Safety Meetup", "date": "2026-03-20", "place": "Cox's Bazar"},
        {"title": "Sajek Group Tour Prep", "date": "2026-03-27", "place": "Khagrachari"},
    ]

    notifications = []
    if request.user.is_authenticated:
        notifications = list(
            CommunityNotification.objects.filter(user=request.user, is_read=False)
            .select_related("actor__profile", "post", "conversation")
            [:8]
        )
        for note in notifications:
            _decorate_notification(note)

    context = {
        "total_trips": trip_aggregate["total_trips"] or 0,
        "total_spent": trip_aggregate["total_spent"] or 0,
        "total_visitors": trip_aggregate["total_visitors"] or 0,
        "total_spots": trip_aggregate["total_spots"] or 0,
        "posts": posts,
        "community_stats": community_stats,
        "recent_media": recent_media,
        "popular_spots": popular_spots,
        "top_contributors": contributor_rows,
        "community_members": member_rows,
        "upcoming_events": upcoming_events,
        "notifications": notifications,
        "feed_filter": feed_filter,
        "search": search,
        "filter_type": filter_type,
        "filter_hashtag": filter_hashtag,
        "filter_location": filter_location,
        "author_filter": author_filter,
        "my_posts_count": CommunityPost.objects.filter(user=request.user).count() if request.user.is_authenticated else 0,
        "saved_posts_count": CommunityPostSave.objects.filter(user=request.user).count() if request.user.is_authenticated else 0,
        "media_posts_count": CommunityPost.objects.filter(
            (Q(image_file__isnull=False) & ~Q(image_file=""))
            | (Q(video_file__isnull=False) & ~Q(video_file=""))
            | (Q(audio_file__isnull=False) & ~Q(audio_file=""))
        ).count(),
        "post_types": CommunityPost.POST_TYPE_CHOICES,
        "districts": District.objects.order_by("name"),
        "spots": TourSpot.objects.order_by("name")[:500],
        "post_form": CommunityPostForm() if request.user.is_authenticated else None,
        "comment_form": CommunityCommentForm() if request.user.is_authenticated else None,
    }
    return render(request, "trips/community.html", context)


COMMUNITY_SECTION_META = {
    "home": {
        "label": "Community Home",
        "description": "Latest community posts with searchable travel filters across Bangladesh.",
        "icon": "bi-house-door",
        "url_name": "community",
        "mode": "posts",
        "default_sort": "latest",
    },
    "discussions": {
        "label": "Travel Discussions",
        "description": "Open-ended travel conversations and community discussions.",
        "icon": "bi-chat-square-text",
        "url_name": "community_discussions",
        "mode": "posts",
        "default_sort": "latest",
    },
    "help": {
        "label": "Help & Questions",
        "description": "Questions, help requests, and unresolved travel problems.",
        "icon": "bi-patch-question",
        "url_name": "community_help",
        "mode": "posts",
        "default_sort": "latest",
    },
    "trip_planning": {
        "label": "Trip Planning",
        "description": "Plan routes, dates, and travel checklists with the community.",
        "icon": "bi-calendar2-check",
        "url_name": "community_trip_planning",
        "mode": "posts",
        "default_sort": "latest",
    },
    "budget": {
        "label": "Budget Travel",
        "description": "Cheap routes, low-cost stays, and money-saving travel tips.",
        "icon": "bi-wallet2",
        "url_name": "community_budget",
        "mode": "posts",
        "default_sort": "popular",
    },
    "hotels": {
        "label": "Hotels & Stay",
        "description": "Hotel, resort, hostel, and guest house recommendations.",
        "icon": "bi-building",
        "url_name": "community_hotels",
        "mode": "posts",
        "default_sort": "latest",
    },
    "transport": {
        "label": "Transport Advice",
        "description": "Bus, launch, train, route, fare, and safety guidance.",
        "icon": "bi-bus-front",
        "url_name": "community_transport",
        "mode": "posts",
        "default_sort": "latest",
    },
    "guides": {
        "label": "Travel Guides",
        "description": "Guides, tutorials, and practical travel information.",
        "icon": "bi-compass",
        "url_name": "community_guides",
        "mode": "posts",
        "default_sort": "latest",
    },
    "popular": {
        "label": "Popular Posts",
        "description": "Posts ranked by likes, comments, and community views.",
        "icon": "bi-fire",
        "url_name": "community_popular",
        "mode": "posts",
        "default_sort": "popular",
    },
    "my_posts": {
        "label": "My Posts",
        "description": "All community posts created from your account.",
        "icon": "bi-file-person",
        "url_name": "community_my_posts",
        "mode": "posts",
        "default_sort": "latest",
    },
    "saved": {
        "label": "Saved Posts",
        "description": "Posts you bookmarked for later reference.",
        "icon": "bi-bookmark-heart",
        "url_name": "community_saved_posts",
        "mode": "posts",
        "default_sort": "latest",
    },
    "media": {
        "label": "Media Gallery",
        "description": "Community posts that include images, videos, or audio attachments.",
        "icon": "bi-images",
        "url_name": "community_media_gallery",
        "mode": "posts",
        "default_sort": "latest",
    },
    "members": {
        "label": "Community Members",
        "description": "Travelers participating in the Cholo Bd community.",
        "icon": "bi-people",
        "url_name": "community_members",
        "mode": "members",
    },
}

COMMUNITY_POST_TYPE_FILTER_MAP = {
    "discussion": ["discussion", "travel_experience"],
    "help": ["help", "travel_question", "lost_found"],
    "trip_planning": ["trip_planning", "trip_plan"],
    "budget_travel": ["budget_travel", "budget_help"],
    "hotels_stay": ["hotels_stay", "hotel_recommendation"],
    "transport_advice": ["transport_advice"],
    "travel_guide": ["travel_guide", "travel_warning"],
}

COMMUNITY_TOPIC_KEYWORDS = {
    "budget": ["budget", "cheap", "backpack", "low cost", "save money", "fare"],
    "hotels": ["hotel", "stay", "resort", "guest house", "guesthouse", "hostel", "room"],
    "transport": ["bus", "launch", "train", "route", "safety", "fare", "flight", "car", "cng"],
    "guides": ["guide", "tutorial", "tips", "itinerary", "what to know", "information"],
}

COMMUNITY_SORT_OPTIONS = [
    ("latest", "Latest first"),
    ("oldest", "Oldest first"),
    ("popular", "Most popular"),
    ("most_discussed", "Most discussed"),
    ("most_viewed", "Most viewed"),
    ("most_liked", "Most liked"),
]

COMMUNITY_RESOLVED_OPTIONS = [
    ("", "All status"),
    ("resolved", "Resolved"),
    ("unresolved", "Unresolved"),
]

COMMUNITY_MEDIA_TYPE_OPTIONS = [
    ("", "All media"),
    ("image", "Image"),
    ("video", "Video"),
    ("audio", "Audio"),
]


def _ensure_community_membership(user):
    membership, created = CommunityMembership.objects.get_or_create(
        user=user,
        defaults={"is_active": True},
    )
    if not created and not membership.is_active:
        membership.is_active = True
        membership.save(update_fields=["is_active", "updated_at"])
    return membership, created


def _community_has_media_q():
    return (
        Q(media_items__isnull=False)
        | (Q(image_file__isnull=False) & ~Q(image_file=""))
        | (Q(video_file__isnull=False) & ~Q(video_file=""))
        | (Q(audio_file__isnull=False) & ~Q(audio_file=""))
    )


def _community_media_type_q(media_type):
    if media_type == "image":
        return Q(media_items__media_type="image") | (Q(image_file__isnull=False) & ~Q(image_file=""))
    if media_type == "video":
        return Q(media_items__media_type="video") | (Q(video_file__isnull=False) & ~Q(video_file=""))
    if media_type == "audio":
        return Q(media_items__media_type="audio") | (Q(audio_file__isnull=False) & ~Q(audio_file=""))
    return _community_has_media_q()


def _community_keyword_q(keywords):
    keyword_query = Q()
    for keyword in keywords:
        keyword_query |= (
            Q(title__icontains=keyword)
            | Q(content__icontains=keyword)
            | Q(location_name__icontains=keyword)
            | Q(hashtags__icontains=keyword)
            | Q(tags__name__icontains=keyword)
            | Q(district__name__icontains=keyword)
            | Q(spot__name__icontains=keyword)
        )
    return keyword_query


def _community_post_type_values(post_type):
    return COMMUNITY_POST_TYPE_FILTER_MAP.get(post_type, [post_type] if post_type else [])


def _build_community_base_posts_queryset():
    return (
        CommunityPost.objects.select_related("user", "user__profile", "district", "spot")
        .prefetch_related(
            "tags",
            "media_items",
            "comments__user",
            "comments__user__profile",
            "comments__history_entries__edited_by",
        )
        .annotate(
            comment_count=Count("comments", distinct=True),
            like_count=Count("reactions", distinct=True),
            save_count=Count("saves", distinct=True),
            view_count=Count("views", distinct=True),
        )
        .annotate(
            popularity_score=ExpressionWrapper(
                F("like_count") * 3 + F("comment_count") * 2 + F("view_count"),
                output_field=IntegerField(),
            )
        )
    )


def _apply_community_section_scope(queryset, active_section, user):
    if active_section == "discussions":
        return queryset.filter(post_type__in=_community_post_type_values("discussion"))
    if active_section == "help":
        return queryset.filter(post_type__in=_community_post_type_values("help"))
    if active_section == "trip_planning":
        return queryset.filter(post_type__in=_community_post_type_values("trip_planning"))
    if active_section == "budget":
        return queryset.filter(
            Q(post_type__in=_community_post_type_values("budget_travel"))
            | _community_keyword_q(COMMUNITY_TOPIC_KEYWORDS["budget"])
            | Q(tags__slug="budget")
        ).distinct()
    if active_section == "hotels":
        return queryset.filter(
            Q(post_type__in=_community_post_type_values("hotels_stay"))
            | _community_keyword_q(COMMUNITY_TOPIC_KEYWORDS["hotels"])
        ).distinct()
    if active_section == "transport":
        return queryset.filter(
            Q(post_type__in=_community_post_type_values("transport_advice"))
            | _community_keyword_q(COMMUNITY_TOPIC_KEYWORDS["transport"])
        ).distinct()
    if active_section == "guides":
        return queryset.filter(
            Q(post_type__in=_community_post_type_values("travel_guide"))
            | _community_keyword_q(COMMUNITY_TOPIC_KEYWORDS["guides"])
        ).distinct()
    if active_section == "my_posts":
        return queryset.filter(user=user)
    if active_section == "saved":
        return queryset.filter(saves__user=user).distinct()
    if active_section == "media":
        return queryset.filter(_community_has_media_q()).distinct()
    return queryset


def _apply_community_post_filters(queryset, request, active_section):
    legacy_sort = (request.GET.get("feed") or "").strip()
    selected_post_type = (request.GET.get("post_type") or request.GET.get("type") or "").strip()
    selected_hashtag = (request.GET.get("hashtag") or "").strip()
    selected_location = (request.GET.get("location") or "").strip()
    selected_keyword = (request.GET.get("q") or "").strip()
    selected_district = (request.GET.get("district") or "").strip()
    selected_spot = (request.GET.get("spot") or "").strip()
    resolved_status = (request.GET.get("resolved") or "").strip()
    media_type = (request.GET.get("media_type") or "").strip()
    author_filter = (request.GET.get("author") or "").strip()
    default_sort = COMMUNITY_SECTION_META[active_section].get("default_sort", "latest")
    selected_sort = (request.GET.get("sort") or "").strip()

    if not selected_sort and legacy_sort:
        legacy_sort_map = {
            "latest": "latest",
            "most_helpful": "most_discussed",
            "trending": "popular",
            "popular": "popular",
        }
        selected_sort = legacy_sort_map.get(legacy_sort, "")

    valid_sorts = {choice[0] for choice in COMMUNITY_SORT_OPTIONS}
    if selected_sort not in valid_sorts:
        selected_sort = default_sort

    if author_filter == "me":
        queryset = queryset.filter(user=request.user)

    if selected_keyword:
        queryset = queryset.filter(
            Q(title__icontains=selected_keyword)
            | Q(content__icontains=selected_keyword)
            | Q(location_name__icontains=selected_keyword)
            | Q(hashtags__icontains=selected_keyword)
            | Q(tags__name__icontains=selected_keyword)
            | Q(district__name__icontains=selected_keyword)
            | Q(spot__name__icontains=selected_keyword)
        ).distinct()

    if selected_location:
        queryset = queryset.filter(
            Q(location_name__icontains=selected_location)
            | Q(district__name__icontains=selected_location)
            | Q(spot__name__icontains=selected_location)
        )

    if selected_hashtag:
        normalized_hashtag = CommunityTag.normalize_name(selected_hashtag)
        queryset = queryset.filter(
            Q(hashtags__icontains=normalized_hashtag)
            | Q(tags__name=normalized_hashtag)
        ).distinct()

    if selected_district.isdigit():
        queryset = queryset.filter(district_id=int(selected_district))

    if selected_spot.isdigit():
        queryset = queryset.filter(spot_id=int(selected_spot))

    if selected_post_type:
        queryset = queryset.filter(post_type__in=_community_post_type_values(selected_post_type))

    if resolved_status == "resolved":
        queryset = queryset.filter(is_resolved=True)
    elif resolved_status == "unresolved":
        queryset = queryset.filter(is_resolved=False)

    if media_type:
        queryset = queryset.filter(_community_media_type_q(media_type)).distinct()

    if selected_sort == "oldest":
        queryset = queryset.order_by("created_at")
    elif selected_sort == "popular":
        queryset = queryset.order_by("-popularity_score", "-like_count", "-comment_count", "-view_count", "-created_at")
    elif selected_sort == "most_discussed":
        queryset = queryset.order_by("-comment_count", "-like_count", "-created_at")
    elif selected_sort == "most_viewed":
        queryset = queryset.order_by("-view_count", "-created_at")
    elif selected_sort == "most_liked":
        queryset = queryset.order_by("-like_count", "-created_at")
    else:
        queryset = queryset.order_by("-created_at")

    return queryset, {
        "q": selected_keyword,
        "location": selected_location,
        "hashtag": selected_hashtag,
        "district": selected_district,
        "spot": selected_spot,
        "post_type": selected_post_type,
        "resolved": resolved_status,
        "media_type": media_type,
        "sort": selected_sort,
    }


def _record_community_post_views(user, posts):
    if not user.is_authenticated or not posts:
        return
    CommunityPostView.objects.bulk_create(
        [CommunityPostView(post=post, user=user) for post in posts],
        ignore_conflicts=True,
    )


def _build_post_media_items(post):
    media_items = list(post.media_items.all())
    inline_types = {item.media_type for item in media_items if getattr(item, "source", "") == "inline"}

    if post.image_file and "image" not in inline_types:
        media_items.append({"media_type": "image", "preview_url": post.image_file.url, "caption": post.title})
    if post.video_file and "video" not in inline_types:
        media_items.append({"media_type": "video", "preview_url": post.video_file.url, "caption": post.title})
    if post.audio_file and "audio" not in inline_types:
        media_items.append({"media_type": "audio", "preview_url": post.audio_file.url, "caption": post.title})
    return media_items


def _decorate_community_posts(request, posts):
    post_ids = [post.id for post in posts]
    user_reaction_map = dict(
        CommunityPostReaction.objects.filter(user=request.user, post_id__in=post_ids).values_list("post_id", "reaction")
    )
    saved_post_ids = set(
        CommunityPostSave.objects.filter(user=request.user, post_id__in=post_ids).values_list("post_id", flat=True)
    )

    author_ids = {post.user_id for post in posts}
    author_trip_map = {
        row["user_id"]: {
            "trips_completed": row["trips_completed"],
            "visited_districts": row["visited_districts"],
        }
        for row in (
            Trip.objects.filter(user_id__in=author_ids)
            .values("user_id")
            .annotate(
                trips_completed=Count("id"),
                visited_districts=Count("district", distinct=True),
            )
        )
    }

    for post in posts:
        author_profile = _get_or_create_profile(post.user)
        can_view_profile = _allows_profile_preview(request.user, post.user, author_profile)
        stats = author_trip_map.get(post.user_id, {"trips_completed": 0, "visited_districts": 0})
        post.author_name = (
            author_profile.full_name
            if can_view_profile and author_profile.full_name
            else post.user.username
        )
        post.author_avatar = author_profile.avatar if can_view_profile and author_profile.avatar else ""
        post.author_is_online = can_view_profile and _is_user_online(post.user, author_profile)
        post.can_view_profile = can_view_profile
        post.author_trips_completed = stats["trips_completed"]
        post.author_visited_districts = stats["visited_districts"]
        post.author_reputation = (stats["trips_completed"] * 2) + (post.comment_count or 0) + (post.like_count or 0)
        post.reaction_counter = Counter(reaction.reaction for reaction in post.reactions.all() if reaction.reaction)
        post.reaction_summary = _serialize_community_reaction_counts(post.reaction_counter)
        post.current_reaction = user_reaction_map.get(post.id, "")
        post.current_reaction_meta = _get_community_reaction_meta(post.current_reaction)
        post.is_liked_by_me = bool(post.current_reaction)
        post.is_saved_by_me = post.id in saved_post_ids
        post.hashtag_tokens = post.hashtags_list
        post.display_media_items = _build_post_media_items(post)
        post.primary_media = post.display_media_items[0] if post.display_media_items else None
        for comment in post.comments.all():
            comment_profile = _get_or_create_profile(comment.user)
            comment.can_view_profile = _allows_profile_preview(request.user, comment.user, comment_profile)
            comment.author_name = (
                comment_profile.full_name
                if comment.can_view_profile and comment_profile.full_name
                else comment.user.username
            )
            comment.author_avatar = (
                comment_profile.avatar
                if comment.can_view_profile and comment_profile.avatar
                else ""
            )
            comment.author_initial = (comment.author_name or comment.user.username or "?")[:1].upper()
            comment.can_edit = comment.user_id == request.user.id
            comment.edit_form = CommunityCommentForm(instance=comment, prefix=f"comment-{comment.id}")


def _build_recent_media_cards():
    cards = []
    media_posts = (
        CommunityPost.objects.select_related("district", "spot")
        .prefetch_related("media_items")
        .filter(_community_has_media_q())
        .distinct()
        .order_by("-created_at")[:6]
    )
    for post in media_posts:
        media_items = _build_post_media_items(post)
        if not media_items:
            continue
        primary_media = media_items[0]
        if isinstance(primary_media, dict):
            media_type = primary_media["media_type"]
            preview_url = primary_media["preview_url"]
        else:
            media_type = primary_media.media_type
            preview_url = primary_media.preview_url
        cards.append(
            {
                "post_id": post.id,
                "title": post.title,
                "media_type": media_type,
                "preview_url": preview_url,
            }
        )
    return cards


def _build_top_contributors(viewer):
    rows = list(
        get_user_model()
        .objects.annotate(
            post_count=Count("community_posts", distinct=True),
            comment_count=Count("community_comments", distinct=True),
        )
        .filter(Q(post_count__gt=0) | Q(comment_count__gt=0))
        .order_by("-post_count", "-comment_count", "username")[:6]
    )
    for person in rows:
        profile = _get_or_create_profile(person)
        person.display_name = profile.full_name or person.username
        person.avatar = profile.avatar
        person.can_view_profile = _allows_profile_preview(viewer, person, profile)
        person.is_online = _is_user_online(person, profile)
    return rows


def _build_member_rows(viewer, *, limit=None, search=""):
    queryset = (
        CommunityMembership.objects.filter(is_active=True)
        .select_related("user__profile")
        .annotate(
            post_count=Count("user__community_posts", distinct=True),
            trip_count=Count("user__trips", distinct=True),
        )
        .order_by("-joined_at", "user__username")
    )
    if search:
        queryset = queryset.filter(
            Q(user__username__icontains=search)
            | Q(user__profile__full_name__icontains=search)
        )
    if limit:
        queryset = queryset[:limit]

    rows = list(queryset)
    for membership in rows:
        profile = membership.user.profile
        membership.display_name = profile.full_name or membership.user.username
        membership.avatar = profile.avatar
        membership.can_view_profile = _allows_profile_preview(viewer, membership.user, profile)
        membership.is_online = _is_user_online(membership.user, profile)
    return rows


def _build_community_sidebar_counts(user):
    return {
        "my_posts": CommunityPost.objects.filter(user=user).count(),
        "saved_posts": CommunityPostSave.objects.filter(user=user).count(),
        "media_posts": CommunityPost.objects.filter(_community_has_media_q()).distinct().count(),
    }


def _build_community_nav_items(active_section, sidebar_counts):
    badge_map = {
        "my_posts": sidebar_counts["my_posts"],
        "saved": sidebar_counts["saved_posts"],
        "media": sidebar_counts["media_posts"],
    }
    ordered_sections = [
        "home",
        "discussions",
        "help",
        "trip_planning",
        "budget",
        "hotels",
        "transport",
        "guides",
        "popular",
        "my_posts",
        "saved",
        "media",
        "members",
    ]
    items = []
    for section_key in ordered_sections:
        meta = COMMUNITY_SECTION_META[section_key]
        items.append(
            {
                "key": section_key,
                "label": meta["label"],
                "icon": meta["icon"],
                "url": reverse(meta["url_name"]),
                "is_active": active_section == section_key,
                "badge": badge_map.get(section_key),
            }
        )
    return items


def _build_community_shared_context(request, active_section):
    trip_aggregate = Trip.objects.aggregate(
        total_trips=Count("id"),
        total_spent=Sum("total_cost"),
        total_visitors=Count("user", distinct=True),
        total_spots=Count("spot", distinct=True),
    )
    membership_base_qs = CommunityMembership.objects.filter(is_active=True)
    recent_media_cards = _build_recent_media_cards()
    top_contributors = _build_top_contributors(request.user)
    community_members_preview = _build_member_rows(request.user, limit=8)
    notifications = list(
        CommunityNotification.objects.filter(user=request.user, is_read=False)
        .select_related("actor__profile", "post", "conversation")[:8]
    )
    for note in notifications:
        _decorate_notification(note)

    sidebar_counts = _build_community_sidebar_counts(request.user)
    community_nav_items = _build_community_nav_items(active_section, sidebar_counts)
    header_tab_keys = {
        "home",
        "discussions",
        "help",
        "trip_planning",
        "budget",
        "hotels",
        "transport",
        "guides",
        "popular",
    }
    shortcut_keys = {"my_posts", "saved", "media", "members"}
    community_header_tabs = [item for item in community_nav_items if item["key"] in header_tab_keys]
    community_shortcuts = [item for item in community_nav_items if item["key"] in shortcut_keys]
    community_cover_image = next(
        (card["preview_url"] for card in recent_media_cards if card["media_type"] == "image"),
        "",
    )
    header_people = []
    for membership in community_members_preview[:8]:
        header_people.append(
            {
                "user_id": membership.user_id,
                "avatar": membership.avatar,
                "display_name": membership.display_name,
                "can_view_profile": membership.can_view_profile,
                "profile_url": reverse("traveler_profile", args=[membership.user.id]) if membership.can_view_profile else "",
            }
        )
    existing_ids = {member["user_id"] for member in header_people}
    for person in top_contributors:
        if person.id in existing_ids:
            continue
        header_people.append(
            {
                "user_id": person.id,
                "avatar": person.avatar,
                "display_name": person.display_name,
                "can_view_profile": person.can_view_profile,
                "profile_url": reverse("traveler_profile", args=[person.id]) if person.can_view_profile else "",
            }
        )
        existing_ids.add(person.id)
        if len(header_people) >= 14:
            break
    return {
        "community_group_name": "Cholo Bd Community",
        "community_group_tagline": "Public group",
        "community_stats": {
            "members": membership_base_qs.count(),
            "online_members": membership_base_qs.filter(
                user__profile__last_active_at__gte=timezone.now() - timezone.timedelta(minutes=5)
            ).count(),
            "posts_today": CommunityPost.objects.filter(created_at__date=timezone.localdate()).count(),
            "trips_shared": trip_aggregate["total_trips"] or 0,
        },
        "top_contributors": top_contributors,
        "recent_media": recent_media_cards,
        "popular_spots": (
            CommunityPost.objects.exclude(spot__isnull=True)
            .values("spot__name")
            .annotate(total=Count("id"))
            .order_by("-total", "spot__name")[:6]
        ),
        "community_members_preview": community_members_preview,
        "community_header_people": header_people,
        "community_cover_image": community_cover_image,
        "notifications": notifications,
        "community_nav_items": community_nav_items,
        "community_header_tabs": community_header_tabs,
        "community_shortcuts": community_shortcuts,
        "community_reaction_choices": COMMUNITY_REACTION_CHOICES,
        "my_posts_count": sidebar_counts["my_posts"],
        "saved_posts_count": sidebar_counts["saved_posts"],
        "media_posts_count": sidebar_counts["media_posts"],
        "upcoming_events": [
            {"title": "Weekend Budget Planning", "date": "2026-03-14", "place": "Dhaka (Online)"},
            {"title": "Cox's Bazar Safety Meetup", "date": "2026-03-20", "place": "Cox's Bazar"},
            {"title": "Sajek Group Tour Prep", "date": "2026-03-27", "place": "Khagrachari"},
        ],
        "filter_post_types": CommunityPost.CANONICAL_POST_TYPE_CHOICES,
        "sort_options": COMMUNITY_SORT_OPTIONS,
        "resolved_options": COMMUNITY_RESOLVED_OPTIONS,
        "media_type_options": COMMUNITY_MEDIA_TYPE_OPTIONS,
        "districts": District.objects.order_by("name"),
        "spots": TourSpot.objects.order_by("name")[:500],
        "post_form": CommunityPostForm(),
        "comment_form": CommunityCommentForm(),
        "active_section": active_section,
        "section_meta": COMMUNITY_SECTION_META[active_section],
        "current_path_with_query": request.get_full_path(),
    }


def _render_community_post_section(request, active_section):
    _ensure_community_membership(request.user)
    posts_qs = _build_community_base_posts_queryset()
    posts_qs = _apply_community_section_scope(posts_qs, active_section, request.user)
    posts_qs, filters = _apply_community_post_filters(posts_qs, request, active_section)
    posts = list(posts_qs[:24])
    _record_community_post_views(request.user, posts)
    _decorate_community_posts(request, posts)

    context = _build_community_shared_context(request, active_section)
    context.update(
        {
            "page_mode": "posts",
            "posts": posts,
            "filters": filters,
            "members": [],
            "member_search": "",
            "show_post_grid": active_section == "media",
        }
    )
    return render(request, "trips/community.html", context)


def _render_community_members_section(request):
    _ensure_community_membership(request.user)
    member_search = (request.GET.get("member_q") or "").strip()
    members = _build_member_rows(request.user, search=member_search)

    context = _build_community_shared_context(request, "members")
    context.update(
        {
            "page_mode": "members",
            "posts": [],
            "filters": {
                "q": "",
                "location": "",
                "hashtag": "",
                "district": "",
                "spot": "",
                "post_type": "",
                "resolved": "",
                "media_type": "",
                "sort": "latest",
            },
            "members": members,
            "member_search": member_search,
            "show_post_grid": False,
        }
    )
    return render(request, "trips/community.html", context)


@login_required
def community(request):
    return _render_community_post_section(request, "home")


@login_required
def community_discussions(request):
    return _render_community_post_section(request, "discussions")


@login_required
def community_help(request):
    return _render_community_post_section(request, "help")


@login_required
def community_trip_planning(request):
    return _render_community_post_section(request, "trip_planning")


@login_required
def community_budget(request):
    return _render_community_post_section(request, "budget")


@login_required
def community_hotels(request):
    return _render_community_post_section(request, "hotels")


@login_required
def community_transport(request):
    return _render_community_post_section(request, "transport")


@login_required
def community_guides(request):
    return _render_community_post_section(request, "guides")


@login_required
def community_popular(request):
    return _render_community_post_section(request, "popular")


@login_required
def community_my_posts(request):
    return _render_community_post_section(request, "my_posts")


@login_required
def community_saved_posts(request):
    return _render_community_post_section(request, "saved")


@login_required
def community_media_gallery(request):
    return _render_community_post_section(request, "media")


@login_required
def community_members(request):
    return _render_community_members_section(request)

@login_required
def community_join(request):
    membership, created = _ensure_community_membership(request.user)
    if created:
        messages.success(request, "Welcome! You have joined the travel community.")
    return redirect("community")


@login_required
@require_POST
def community_create_post(request):
    form = CommunityPostForm(request.POST, request.FILES)
    if form.is_valid():
        post = form.save(commit=False)
        post.user = request.user
        post.save()
        _notify_mentions(
            actor=request.user,
            post=post,
            text=f"{post.title} {post.content}",
        )
        messages.success(request, "Community post published.")
    else:
        messages.error(request, "Could not publish post. Please check required fields.")
    return redirect(_safe_redirect_url(request, "community"))


@login_required
@require_POST
def community_add_comment(request, post_id):
    post = get_object_or_404(CommunityPost, id=post_id)
    form = CommunityCommentForm(request.POST, request.FILES)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.user = request.user
        comment.post = post
        comment.save()
        if post.user_id != request.user.id and _should_create_notification(post.user, "comment_alerts"):
            CommunityNotification.objects.create(
                user=post.user,
                actor=request.user,
                post=post,
                kind="answer" if post.post_type in {"help", "travel_question"} else "comment",
                message=f"{request.user.username} commented on your post.",
            )
        _notify_mentions(
            actor=request.user,
            post=post,
            text=comment.content,
        )
        messages.success(request, "Comment added.")
    else:
        messages.error(request, "Comment could not be added. Add text or media.")
    next_url = _safe_redirect_url(request, "community")
    return redirect(f"{next_url}#comments-{post.id}")


@login_required
@require_POST
def community_edit_comment(request, comment_id):
    comment = get_object_or_404(
        CommunityComment.objects.select_related("post", "user"),
        id=comment_id,
    )
    if comment.user_id != request.user.id:
        messages.error(request, "You can edit only your own comment.")
        return redirect(f"{_safe_redirect_url(request, 'community')}#comments-{comment.post_id}")

    original_state = _capture_comment_state(comment)
    form = CommunityCommentForm(
        request.POST,
        request.FILES,
        instance=comment,
        prefix=f"comment-{comment.id}",
    )
    if not form.is_valid():
        messages.error(request, "Comment edit failed. Check the text or media fields.")
        return redirect(f"{_safe_redirect_url(request, 'community')}#comments-{comment.post_id}")

    if not _comment_has_changes(original_state, form.cleaned_data):
        messages.info(request, "No comment changes detected.")
        return redirect(f"{_safe_redirect_url(request, 'community')}#comments-{comment.post_id}")

    _create_comment_history_snapshot(comment, request.user, original_state)
    edited_comment = form.save(commit=False)
    edited_comment.edited_at = timezone.now()
    edited_comment.save()
    messages.success(request, "Comment updated.")
    return redirect(f"{_safe_redirect_url(request, 'community')}#comments-{comment.post_id}")


@login_required
@require_POST
def community_toggle_like(request, post_id):
    post = get_object_or_404(CommunityPost, id=post_id)
    reaction_key = (request.POST.get("reaction") or "like").strip().lower()
    if reaction_key not in COMMUNITY_REACTION_META:
        reaction_key = "like"

    reaction = CommunityPostReaction.objects.filter(
        post=post,
        user=request.user,
    ).first()

    liked = True
    selected_reaction = reaction_key
    if reaction and reaction.reaction == reaction_key:
        reaction.delete()
        liked = False
        selected_reaction = ""
        CommunityNotification.objects.filter(
            user=post.user,
            actor=request.user,
            post=post,
            kind="like",
            is_read=False,
        ).delete()
    elif reaction:
        reaction.reaction = reaction_key
        reaction.save(update_fields=["reaction"])
    else:
        CommunityPostReaction.objects.create(
            post=post,
            user=request.user,
            reaction=reaction_key,
        )

    if liked and post.user_id != request.user.id and _should_create_notification(post.user, "like_alerts"):
        reaction_meta = _get_community_reaction_meta(selected_reaction)
        CommunityNotification.objects.update_or_create(
            user=post.user,
            actor=request.user,
            post=post,
            kind="like",
            defaults={
                "message": f"{request.user.username} reacted with {reaction_meta['label']} to your post: {post.title}",
                "is_read": False,
            },
        )

    reaction_counter = Counter(post.reactions.values_list("reaction", flat=True))
    reaction_summary = _serialize_community_reaction_counts(reaction_counter)
    selected_reaction_meta = _get_community_reaction_meta(selected_reaction)

    return JsonResponse(
        {
            "liked": liked,
            "like_count": post.reactions.count(),
            "selected_reaction": selected_reaction,
            "reaction_label": selected_reaction_meta["label"] if liked else "Like",
            "reaction_emoji": selected_reaction_meta["emoji"] if liked else "👍",
            "top_reactions": reaction_summary[:2],
        }
    )


@login_required
@require_POST
def community_toggle_save(request, post_id):
    post = get_object_or_404(CommunityPost, id=post_id)
    saved_row, created = CommunityPostSave.objects.get_or_create(
        post=post,
        user=request.user,
    )
    saved = True
    if not created:
        saved_row.delete()
        saved = False

    return JsonResponse(
        {
            "saved": saved,
            "save_count": post.saves.count(),
        }
    )


@login_required
@require_POST
def community_mark_notifications_read(request):
    CommunityNotification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return JsonResponse({"ok": True})


@login_required
def notifications_view(request):
    notifications_qs = CommunityNotification.objects.filter(user=request.user)
    notifications = list(
        notifications_qs
        .select_related("actor__profile", "post", "conversation")
        .order_by("-created_at")[:60]
    )
    for note in notifications:
        _decorate_notification(note)

    context = {
        "notifications": notifications,
        "unread_count": notifications_qs.filter(is_read=False).count(),
        "follow_count": notifications_qs.filter(kind="follow").count(),
        "engagement_count": notifications_qs.filter(
            kind__in=["like", "comment", "answer", "post_reply", "mention"]
        ).count(),
        "message_count": notifications_qs.filter(kind__in=["direct_message", "call"]).count(),
    }
    return render(request, "trips/notifications.html", context)


@login_required
def notification_open(request, notification_id):
    notification = get_object_or_404(
        CommunityNotification.objects.select_related("actor", "post", "conversation"),
        id=notification_id,
        user=request.user,
    )
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])
    return redirect(_notification_target_url(notification))


@login_required
@require_POST
def notifications_mark_all_read(request):
    CommunityNotification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect("notifications")


@login_required
def community_user_profile_api(request, user_id):
    User = get_user_model()
    target = get_object_or_404(User, id=user_id)
    profile = _get_or_create_profile(target)
    community_settings = UserCommunitySettings.objects.get_or_create(user=target)[0]
    if not _allows_profile_preview(request.user, target, profile):
        return JsonResponse({"detail": "This profile is private."}, status=403)
    trip_summary = Trip.objects.filter(user=target).aggregate(
        trips_completed=Count("id"),
        visited_districts=Count("district", distinct=True),
    )
    contribution_summary = {
        "posts": CommunityPost.objects.filter(user=target).count(),
        "comments": CommunityComment.objects.filter(user=target).count(),
    }
    reputation = (
        (trip_summary["trips_completed"] or 0) * 2
        + contribution_summary["posts"] * 4
        + contribution_summary["comments"] * 2
    )

    avatar = ""
    if profile.avatar:
        avatar = profile.avatar

    relationship = _build_relationship_context(
        request.user,
        target,
        profile=profile,
        community_settings=community_settings,
    )

    return JsonResponse(
        {
            "id": target.id,
            "name": profile.full_name if profile and profile.full_name else target.username,
            "username": target.username,
            "avatar": avatar,
            "trips_completed": trip_summary["trips_completed"] or 0,
            "visited_districts": trip_summary["visited_districts"] or 0,
            "reputation": reputation,
            "bio": profile.bio or "",
            "location": profile.location or "",
            "is_online": _is_user_online(target, profile),
            "follower_count": relationship["follower_count"],
            "following_count": relationship["following_count"],
            "can_follow": relationship["can_follow"],
            "is_following": relationship["is_following"],
            "can_message": relationship["can_message"],
            "is_self": relationship["is_self"],
            "profile_url": relationship["profile_url"],
            "message_url": relationship["message_url"],
        }
    )


@login_required
@require_POST
def community_toggle_follow(request, user_id):
    User = get_user_model()
    target = get_object_or_404(User, id=user_id)

    if target.id == request.user.id:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"detail": "You cannot follow yourself."}, status=400)
        messages.error(request, "You cannot follow your own profile.")
        return redirect("profile")

    follow_link, created = UserFollow.objects.get_or_create(
        follower=request.user,
        following=target,
    )
    is_following = True
    if not created:
        follow_link.delete()
        is_following = False
    elif _should_create_notification(target, "follower_alerts"):
        CommunityNotification.objects.create(
            user=target,
            actor=request.user,
            kind="follow",
            message=f"{request.user.username} started following you.",
        )

    payload = {
        "following": is_following,
        "follower_count": UserFollow.objects.filter(following=target).count(),
    }

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse(payload)

    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect("traveler_profile", user_id=target.id)


@login_required
def traveler_profile(request, user_id):
    User = get_user_model()
    target = get_object_or_404(User.objects.select_related("profile"), id=user_id)
    if target.id == request.user.id:
        return redirect("profile")

    profile = _get_or_create_profile(target)
    community_settings = UserCommunitySettings.objects.get_or_create(user=target)[0]
    if not _allows_profile_preview(request.user, target, profile):
        messages.error(request, "This profile is private.")
        return redirect("community")

    trip_summary = Trip.objects.filter(user=target).aggregate(
        total_trips=Count("id"),
        visited_districts=Count("district", distinct=True),
        visited_spots=Count("spot", distinct=True),
    )
    relationship = _build_relationship_context(
        request.user,
        target,
        profile=profile,
        community_settings=community_settings,
    )
    recent_posts = list(
        CommunityPost.objects.filter(user=target)
        .select_related("district", "spot")
        .order_by("-created_at")[:4]
    )

    return render(
        request,
        "trips/public_profile.html",
        {
            "target_user": target,
            "profile": profile,
            "relationship": relationship,
            "total_trips": trip_summary["total_trips"] or 0,
            "visited_districts": trip_summary["visited_districts"] or 0,
            "visited_spots": trip_summary["visited_spots"] or 0,
            "post_count": CommunityPost.objects.filter(user=target).count(),
            "recent_posts": recent_posts,
        },
    )


@login_required
def direct_message_start(request, user_id):
    User = get_user_model()
    target = get_object_or_404(User, id=user_id)

    if target.id == request.user.id:
        messages.info(request, "Open your inbox to review existing conversations.")
        return redirect("direct_messages")

    if not _allows_direct_message(request.user, target):
        messages.error(request, "This traveler is not accepting messages from you right now.")
        return redirect("traveler_profile", user_id=target.id)

    conversation, _ = _get_or_create_direct_conversation(request.user, target)
    return redirect(f"{reverse('direct_messages')}?conversation={conversation.id}")


@login_required
def direct_messages(request):
    base_qs = (
        Conversation.objects.filter(participants=request.user)
        .prefetch_related(
            "participants__profile",
            "messages__sender__profile",
            "messages__attachments",
        )
        .order_by("-updated_at", "-created_at")
    )

    requested_conversation = request.GET.get("conversation")
    selected_conversation_id = None
    if requested_conversation and requested_conversation.isdigit():
        selected_conversation_id = int(requested_conversation)
    else:
        selected_conversation_id = base_qs.values_list("id", flat=True).first()

    if selected_conversation_id:
        selected_base = get_object_or_404(base_qs, id=selected_conversation_id)
        Message.objects.filter(
            conversation=selected_base,
            is_read=False,
        ).exclude(sender=request.user).update(is_read=True)

    conversations = list(base_qs)

    selected_conversation = None
    for conversation in conversations:
        conversation.partner = _get_conversation_partner(conversation, request.user)
        message_list = list(conversation.messages.all())
        conversation.last_message = message_list[-1] if message_list else None
        conversation.unread_count = sum(
            1
            for message in message_list
            if message.sender_id != request.user.id and not message.is_read
        )
        if conversation.id == selected_conversation_id:
            selected_conversation = conversation
            conversation.message_list = message_list

    if not selected_conversation and conversations:
        selected_conversation = conversations[0]
        selected_conversation.message_list = list(selected_conversation.messages.all())

    selected_partner = _get_conversation_partner(selected_conversation, request.user) if selected_conversation else None
    selected_call_session = _get_conversation_active_call(selected_conversation, request.user)
    incoming_call_session = (
        CallSession.objects.filter(
            recipient=request.user,
            status="pending",
        )
        .select_related("initiator__profile", "recipient__profile", "conversation")
        .order_by("-created_at")
        .first()
    )

    context = {
        "conversations": conversations,
        "selected_conversation": selected_conversation,
        "selected_partner": selected_partner,
        "selected_call_session": selected_call_session,
        "incoming_call_session": incoming_call_session,
        "message_form": MessageForm(),
    }
    return render(request, "trips/messages.html", context)


@login_required
@require_POST
def direct_message_send(request, conversation_id):
    conversation = get_object_or_404(
        Conversation.objects.prefetch_related("participants"),
        id=conversation_id,
    )
    if not _conversation_belongs_to_user(conversation, request.user):
        return redirect("direct_messages")

    recipient = _get_conversation_partner(conversation, request.user)
    if not _allows_direct_message(request.user, recipient):
        messages.error(request, "This traveler is not accepting messages from you right now.")
        return redirect(f"{reverse('direct_messages')}?conversation={conversation.id}")

    if _message_rate_limited(request.user):
        messages.error(request, "You are sending messages too quickly. Please wait a few seconds.")
        return redirect(f"{reverse('direct_messages')}?conversation={conversation.id}")

    form = MessageForm(request.POST, request.FILES)
    if form.is_valid():
        message = form.save(commit=False)
        message.conversation = conversation
        message.sender = request.user
        message.save()
        attachment = form.cleaned_data.get("attachment")
        if attachment:
            MessageAttachment.objects.create(message=message, file=attachment)
        Conversation.objects.filter(id=conversation.id).update(updated_at=timezone.now())
        if _should_create_notification(recipient, "message_alerts"):
            CommunityNotification.objects.create(
                user=recipient,
                actor=request.user,
                conversation=conversation,
                kind="direct_message",
                message=f"{request.user.username} sent you a direct message.",
            )
    else:
        messages.error(request, "Write a message or attach a file before sending.")

    return redirect(f"{reverse('direct_messages')}?conversation={conversation.id}")


@login_required
@require_POST
def direct_message_call_request(request, conversation_id):
    conversation = get_object_or_404(
        Conversation.objects.prefetch_related("participants"),
        id=conversation_id,
    )
    if not _conversation_belongs_to_user(conversation, request.user):
        return redirect("direct_messages")

    recipient = _get_conversation_partner(conversation, request.user)
    if not recipient or not _allows_direct_message(request.user, recipient):
        messages.error(request, "This traveler is not accepting call requests from you right now.")
        return redirect(f"{reverse('direct_messages')}?conversation={conversation.id}")

    mode = request.POST.get("mode") or "audio"
    mode_label = "video call" if mode == "video" else "audio call"
    existing_call = (
        CallSession.objects.filter(
            conversation=conversation,
            status__in=["pending", "accepted"],
            mode=mode,
        )
        .filter(
            Q(initiator=request.user, recipient=recipient)
            | Q(initiator=recipient, recipient=request.user)
        )
        .order_by("-created_at")
        .first()
    )
    if existing_call:
        messages.info(request, f"There is already an active {mode_label}.")
        if existing_call.status == "accepted":
            return redirect("direct_call_room", call_id=existing_call.id)
        return redirect(f"{reverse('direct_messages')}?conversation={conversation.id}")

    call_session = CallSession.objects.create(
        conversation=conversation,
        initiator=request.user,
        recipient=recipient,
        mode=mode,
        status="pending",
    )
    Conversation.objects.filter(id=conversation.id).update(updated_at=timezone.now())

    if _should_create_notification(recipient, "call_alerts"):
        CommunityNotification.objects.create(
            user=recipient,
            actor=request.user,
            conversation=conversation,
            kind="call",
            message=f"{request.user.username} started a {mode_label} request.",
        )

    messages.success(request, f"{mode_label.title()} request sent.")
    return redirect(f"{reverse('direct_messages')}?conversation={conversation.id}#call-{call_session.id}")


@login_required
@require_POST
def direct_call_update(request, call_id):
    call_session = get_object_or_404(
        CallSession.objects.select_related("conversation", "initiator__profile", "recipient__profile"),
        id=call_id,
    )
    if not _call_session_belongs_to_user(call_session, request.user):
        return redirect("direct_messages")

    action = (request.POST.get("action") or "").strip().lower()
    conversation_url = f"{reverse('direct_messages')}?conversation={call_session.conversation_id}#call-{call_session.id}"
    mode_label = "video call" if call_session.mode == "video" else "audio call"

    if action == "accept" and call_session.recipient_id == request.user.id and call_session.status == "pending":
        call_session.status = "accepted"
        call_session.responded_at = timezone.now()
        call_session.save(update_fields=["status", "responded_at", "updated_at"])
        if _should_create_notification(call_session.initiator, "call_alerts"):
            CommunityNotification.objects.create(
                user=call_session.initiator,
                actor=request.user,
                conversation=call_session.conversation,
                kind="call",
                message=f"{request.user.username} accepted your {mode_label}.",
            )
        messages.success(request, f"{mode_label.title()} accepted.")
        return redirect("direct_call_room", call_id=call_session.id)

    if action == "decline" and call_session.recipient_id == request.user.id and call_session.status == "pending":
        call_session.status = "declined"
        call_session.responded_at = timezone.now()
        call_session.save(update_fields=["status", "responded_at", "updated_at"])
        if _should_create_notification(call_session.initiator, "call_alerts"):
            CommunityNotification.objects.create(
                user=call_session.initiator,
                actor=request.user,
                conversation=call_session.conversation,
                kind="call",
                message=f"{request.user.username} declined your {mode_label}.",
            )
        messages.info(request, f"{mode_label.title()} declined.")
        return redirect(conversation_url)

    if action == "end" and call_session.status in {"pending", "accepted"}:
        call_session.status = "ended"
        call_session.ended_at = timezone.now()
        call_session.save(update_fields=["status", "ended_at", "updated_at"])
        messages.info(request, f"{mode_label.title()} ended.")
        return redirect(conversation_url)

    messages.info(request, "This call session is no longer available.")
    return redirect(conversation_url)


@login_required
def direct_call_room(request, call_id):
    call_session = get_object_or_404(
        CallSession.objects.select_related("conversation", "initiator__profile", "recipient__profile"),
        id=call_id,
    )
    if not _call_session_belongs_to_user(call_session, request.user):
        return redirect("direct_messages")

    if call_session.status == "ended":
        messages.info(request, "This call has already ended.")
        return redirect(f"{reverse('direct_messages')}?conversation={call_session.conversation_id}")

    if call_session.status == "declined":
        messages.info(request, "This call request was declined.")
        return redirect(f"{reverse('direct_messages')}?conversation={call_session.conversation_id}")

    if call_session.status == "pending" and call_session.recipient_id == request.user.id:
        call_session.status = "accepted"
        call_session.responded_at = timezone.now()
        call_session.save(update_fields=["status", "responded_at", "updated_at"])
        if _should_create_notification(call_session.initiator, "call_alerts"):
            CommunityNotification.objects.create(
                user=call_session.initiator,
                actor=request.user,
                conversation=call_session.conversation,
                kind="call",
                message=f"{request.user.username} joined your {'video call' if call_session.mode == 'video' else 'audio call'}.",
            )

    context = {
        "call_session": call_session,
        "call_partner": call_session.other_participant(request.user),
        "call_room_url": _build_call_room_url(call_session),
        "is_initiator": call_session.initiator_id == request.user.id,
    }
    return render(request, "trips/call_room.html", context)


@login_required
@require_POST
def direct_message_delete(request, message_id):
    message = get_object_or_404(
        Message.objects.select_related("conversation", "sender"),
        id=message_id,
    )
    if message.sender_id != request.user.id or not _conversation_belongs_to_user(message.conversation, request.user):
        return redirect("direct_messages")

    for attachment in message.attachments.all():
        attachment.file.delete(save=False)
        attachment.delete()
    message.content = ""
    message.is_deleted = True
    message.save(update_fields=["content", "is_deleted"])
    return redirect(f"{reverse('direct_messages')}?conversation={message.conversation_id}")


@login_required
def api_conversations(request):
    conversations = (
        Conversation.objects.filter(participants=request.user)
        .prefetch_related("participants__profile", "messages__sender__profile", "messages__attachments")
        .order_by("-updated_at", "-created_at")
    )
    payload = []
    for conversation in conversations:
        partner = _get_conversation_partner(conversation, request.user)
        last_message = conversation.messages.order_by("created_at").last()
        payload.append(
            {
                "id": conversation.id,
                "partner": {
                    "id": partner.id,
                    "username": partner.username,
                    "name": partner.profile.full_name or partner.username,
                    "avatar": partner.profile.avatar or "",
                }
                if partner
                else None,
                "updated_at": conversation.updated_at.isoformat(),
                "last_message": _serialize_message(last_message, request.user) if last_message else None,
                "unread_count": conversation.messages.filter(is_read=False).exclude(sender=request.user).count(),
            }
        )
    return JsonResponse({"results": payload})


@login_required
def api_messages(request):
    conversation_id = request.GET.get("conversation_id")
    if not conversation_id or not conversation_id.isdigit():
        return JsonResponse({"detail": "conversation_id is required."}, status=400)

    conversation = get_object_or_404(
        Conversation.objects.prefetch_related("participants", "messages__sender__profile", "messages__attachments"),
        id=int(conversation_id),
    )
    if not _conversation_belongs_to_user(conversation, request.user):
        return JsonResponse({"detail": "Access denied."}, status=403)

    return JsonResponse(
        {
            "conversation_id": conversation.id,
            "results": [_serialize_message(message, request.user) for message in conversation.messages.all()],
        }
    )


@login_required
@require_POST
def api_send_message(request):
    receiver_id = request.POST.get("receiver_id")
    conversation_id = request.POST.get("conversation_id")

    if _message_rate_limited(request.user):
        return JsonResponse({"detail": "Message rate limit reached. Try again shortly."}, status=429)

    conversation = None
    recipient = None
    if conversation_id and conversation_id.isdigit():
        conversation = get_object_or_404(
            Conversation.objects.prefetch_related("participants"),
            id=int(conversation_id),
        )
        if not _conversation_belongs_to_user(conversation, request.user):
            return JsonResponse({"detail": "Access denied."}, status=403)
        recipient = _get_conversation_partner(conversation, request.user)
    elif receiver_id and receiver_id.isdigit():
        User = get_user_model()
        recipient = get_object_or_404(User, id=int(receiver_id))
        if not _allows_direct_message(request.user, recipient):
            return JsonResponse({"detail": "This traveler is not accepting messages from you."}, status=403)
        conversation, _ = _get_or_create_direct_conversation(request.user, recipient)
    else:
        return JsonResponse({"detail": "receiver_id or conversation_id is required."}, status=400)

    form = MessageForm(request.POST, request.FILES)
    if not form.is_valid():
        return JsonResponse(
            {
                "errors": form.errors.get_json_data(),
                "non_field_errors": list(form.non_field_errors()),
            },
            status=400,
        )

    message = form.save(commit=False)
    message.conversation = conversation
    message.sender = request.user
    message.save()
    attachment = form.cleaned_data.get("attachment")
    if attachment:
        MessageAttachment.objects.create(message=message, file=attachment)
    Conversation.objects.filter(id=conversation.id).update(updated_at=timezone.now())

    if recipient and _should_create_notification(recipient, "message_alerts"):
        CommunityNotification.objects.create(
            user=recipient,
            actor=request.user,
            conversation=conversation,
            kind="direct_message",
            message=f"{request.user.username} sent you a direct message.",
        )

    message.refresh_from_db()
    return JsonResponse(
        {
            "conversation_id": conversation.id,
            "message": _serialize_message(message, request.user),
        }
    )


@login_required
@require_POST
def api_mark_read(request):
    conversation_id = request.POST.get("conversation_id")
    if not conversation_id or not conversation_id.isdigit():
        return JsonResponse({"detail": "conversation_id is required."}, status=400)

    conversation = get_object_or_404(
        Conversation.objects.prefetch_related("participants"),
        id=int(conversation_id),
    )
    if not _conversation_belongs_to_user(conversation, request.user):
        return JsonResponse({"detail": "Access denied."}, status=403)

    updated = Message.objects.filter(
        conversation=conversation,
        is_read=False,
    ).exclude(sender=request.user).update(is_read=True)
    return JsonResponse({"ok": True, "updated": updated})


@login_required
def dashboard(request):
    return redirect("my_trips")


@login_required
def my_trips(request):
    reminder_form = TripReminderForm()

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "set_next_trip":
            reminder_form = TripReminderForm(request.POST)
            if reminder_form.is_valid():
                reminder = reminder_form.save(commit=False)
                reminder.user = request.user
                reminder.is_active = True
                reminder.save()
                messages.success(request, "Next trip reminder saved.")
                return redirect("my_trips")
        elif action == "clear_next_trip":
            reminder_id = request.POST.get("reminder_id")
            if reminder_id and str(reminder_id).isdigit():
                TripReminder.objects.filter(
                    id=reminder_id,
                    user=request.user,
                    is_active=True,
                ).update(is_active=False)
                messages.info(request, "Reminder cleared.")
            return redirect("my_trips")

    trips = (
        Trip.objects.filter(user=request.user)
        .select_related("division", "district", "upazila", "spot")
        .order_by("-from_date", "-created_at")
    )
    overview = _build_trip_overview_context(trips)

    now = timezone.localtime()
    upcoming_reminder = (
        TripReminder.objects.filter(user=request.user, is_active=True)
        .select_related("spot__upazila__district__division")
        .filter(
            Q(reminder_date__gt=now.date())
            | Q(reminder_date=now.date(), reminder_time__gte=now.time())
        )
        .order_by("reminder_date", "reminder_time", "created_at")
        .first()
    )

    upcoming_reminder_iso = ""
    if upcoming_reminder:
        reminder_dt = timezone.make_aware(
            datetime.combine(upcoming_reminder.reminder_date, upcoming_reminder.reminder_time),
            timezone.get_current_timezone(),
        )
        upcoming_reminder_iso = reminder_dt.isoformat()
    upcoming_route_data = _build_next_trip_route_context(upcoming_reminder)

    context = {
        "trips": trips,
        "reminder_form": reminder_form,
        "upcoming_reminder": upcoming_reminder,
        "upcoming_reminder_iso": upcoming_reminder_iso,
        "upcoming_route_data": upcoming_route_data,
        "google_maps_embed_api_key": settings.GOOGLE_MAPS_EMBED_API_KEY,
        "route_districts_json": list(
            District.objects.values("id", "name", "division_id").order_by("name")
        ),
        "route_upazilas_json": list(
            Upazila.objects.values("id", "name", "district_id").order_by("name")
        ),
        "route_spots_json": list(
            TourSpot.objects.values(
                "id",
                "name",
                "upazila_id",
                "latitude",
                "longitude",
                "upazila__name",
                "upazila__district__name",
            ).order_by("name")
        ),
    }
    context.update(overview)
    return render(request, "trips/my_trips.html", context)


@login_required
def trip_create(request):
    if request.method == "POST":
        form = TripForm(request.POST)
        if form.is_valid():
            trip = form.save(commit=False)
            trip.user = request.user
            trip.save()
            return redirect("trip_detail", trip_id=trip.id)
    else:
        initial = {}
        for field_name in ("division", "district", "upazila", "spot"):
            value = request.GET.get(field_name, "").strip()
            if value.isdigit():
                initial[field_name] = int(value)
        form = TripForm(initial=initial)

    return render(
        request,
        "trips/trip_form.html",
        {
            "form": form,
            "is_edit": False,
            "trip": None,
        },
    )


@login_required
def trip_edit(request, trip_id):
    trip = get_object_or_404(Trip, id=trip_id, user=request.user)

    if request.method == "POST":
        form = TripForm(request.POST, instance=trip)
        if form.is_valid():
            updated_trip = form.save(commit=False)
            updated_trip.user = request.user
            updated_trip.save()
            return redirect("trip_detail", trip_id=updated_trip.id)
    else:
        form = TripForm(instance=trip)

    return render(
        request,
        "trips/trip_form.html",
        {
            "form": form,
            "is_edit": True,
            "trip": trip,
        },
    )


@login_required
def trip_detail(request, trip_id):
    trip = get_object_or_404(
        Trip.objects.select_related("division", "district", "upazila", "spot"),
        id=trip_id,
        user=request.user,
    )
    return render(request, "trips/trip_detail.html", {"trip": trip})


@login_required
def profile_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    was_complete = profile.is_profile_complete
    form = UserProfileForm(
        instance=profile,
        user=request.user,
        enforce_required=not was_complete,
    )
    avatar_upload_form = ProfileAvatarUploadForm(instance=profile, prefix="avatar_upload")
    cover_upload_form = ProfileCoverUploadForm(instance=profile, prefix="cover_upload")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "update_cover":
            cover_upload_form = ProfileCoverUploadForm(
                request.POST,
                request.FILES,
                instance=profile,
                prefix="cover_upload",
            )
            if cover_upload_form.is_valid():
                cover_upload_form.save()
                messages.success(request, "Cover photo updated.")
                return redirect("profile")
            messages.error(request, "Could not update cover photo. Check the selected file type or size.")
        elif action == "update_avatar":
            avatar_upload_form = ProfileAvatarUploadForm(
                request.POST,
                request.FILES,
                instance=profile,
                prefix="avatar_upload",
            )
            if avatar_upload_form.is_valid():
                avatar_upload_form.save()
                messages.success(request, "Profile photo updated.")
                return redirect("profile")
            messages.error(request, "Could not update profile photo. Check the selected file type or size.")
        else:
            form = UserProfileForm(
                request.POST,
                request.FILES,
                instance=profile,
                user=request.user,
                enforce_required=not was_complete,
            )
            if form.is_valid():
                form.save()
                profile.refresh_from_db()
                if not was_complete and profile.is_profile_complete:
                    messages.success(request, "Profile completed. You can now explore the full website.")
                    return redirect("home")
                messages.success(request, "Profile updated successfully.")
                return redirect("profile")

    trips_qs = (
        Trip.objects.filter(user=request.user)
        .select_related("division", "district", "upazila", "spot")
        .order_by("-from_date", "-created_at")
    )
    trip_summary = trips_qs.aggregate(
        total_trips=Count("id"),
        total_spent=Sum("total_cost"),
        visited_districts=Count("district", distinct=True),
        visited_spots=Count("spot", distinct=True),
    )

    recent_posts = list(
        CommunityPost.objects.filter(user=request.user)
        .select_related("district", "spot")
        .annotate(
            comment_count=Count("comments", distinct=True),
            like_count=Count("reactions", distinct=True),
        )
        .order_by("-created_at")[:4]
    )
    recent_albums = list(
        Album.objects.filter(user=request.user)
        .select_related("spot")
        .prefetch_related("items")
        .annotate(item_count=Count("items"))
        .order_by("-trip_date", "-created_at")[:4]
    )
    for album in recent_albums:
        album.preview_item = next(
            (
                item
                for item in album.items.all()
                if item.file or item.external_url
            ),
            None,
        )

    recent_stories = list(
        Story.objects.filter(user=request.user)
        .select_related("spot")
        .order_by("-trip_date", "-created_at")[:4]
    )
    recent_history_entries = list(
        TravelHistory.objects.filter(user=request.user)
        .order_by("-visit_date", "-created_at")[:4]
    )
    recent_saved_spots = list(
        SavedSpot.objects.filter(user=request.user)
        .select_related("spot__upazila__district__division")
        .order_by("-created_at")[:4]
    )

    total_trips = trip_summary["total_trips"] or 0
    visited_districts = trip_summary["visited_districts"] or 0
    visited_spots = trip_summary["visited_spots"] or 0
    total_spent = trip_summary["total_spent"] or 0

    completion_fields = [
        profile.full_name,
        request.user.email,
        profile.phone,
        profile.avatar,
        profile.bio,
        profile.location,
        profile.website,
        profile.gender,
        profile.date_of_birth,
    ]
    profile_completion = round(
        (sum(1 for value in completion_fields if value) / len(completion_fields)) * 100
    )

    profile_badges = []
    if total_trips:
        profile_badges.append("Explorer")
    if visited_districts >= 5:
        profile_badges.append("District Hunter")
    if recent_stories:
        profile_badges.append("Story Teller")
    if recent_posts:
        profile_badges.append("Community Voice")
    if total_spent >= 50000:
        profile_badges.append("Road Warrior")

    follower_count = UserFollow.objects.filter(following=request.user).count()
    following_count = UserFollow.objects.filter(follower=request.user).count()

    return render(
        request,
        "trips/profile.html",
        {
            "form": form,
            "avatar_upload_form": avatar_upload_form,
            "cover_upload_form": cover_upload_form,
            "profile": profile,
            "onboarding_required": not profile.is_profile_complete,
            "profile_completion": profile_completion,
            "profile_badges": profile_badges,
            "total_trips": total_trips,
            "visited_districts": visited_districts,
            "visited_spots": visited_spots,
            "total_spent": total_spent,
            "recent_trips": list(trips_qs[:4]),
            "recent_posts": recent_posts,
            "recent_albums": recent_albums,
            "recent_stories": recent_stories,
            "recent_history_entries": recent_history_entries,
            "recent_saved_spots": recent_saved_spots,
            "album_count": Album.objects.filter(user=request.user).count(),
            "story_count": Story.objects.filter(user=request.user).count(),
            "history_count": TravelHistory.objects.filter(user=request.user).count(),
            "saved_spot_count": SavedSpot.objects.filter(user=request.user).count(),
            "post_count": CommunityPost.objects.filter(user=request.user).count(),
            "follower_count": follower_count,
            "following_count": following_count,
        },
    )


@login_required
def settings_view(request, section="account"):
    active_section = normalize_settings_section(section)
    if section != active_section:
        return redirect("settings_section", section=active_section)
    bundle = get_or_create_settings_bundle(request.user)
    form_map = {
        "account": AccountSettingsForm,
        "profile": ProfileSettingsSectionForm,
        "privacy": PrivacySettingsForm,
        "security": SecuritySettingsForm,
        "appearance": AppearanceSettingsForm,
        "notifications": NotificationSettingsForm,
    }
    form_class = form_map.get(active_section)
    form = form_class(user=request.user, bundle=bundle) if form_class else None
    deactivate_form = DangerZoneDeactivateForm(user=request.user)
    delete_form = DangerZoneDeleteForm(user=request.user)

    if request.method == "POST":
        action = request.POST.get("action") or "save_section"

        if action == "save_section" and form_class is not None:
            form = form_class(request.POST, request.FILES, user=request.user, bundle=bundle)
            if form.is_valid():
                old_password_hash = request.user.password
                changed_fields = list(form.changed_data)
                form.save()
                if active_section == "security" and request.user.password != old_password_hash:
                    update_session_auth_hash(request, request.user)
                log_settings_change(request.user, active_section, "save", request, changed_fields)
                messages.success(request, f"{get_settings_section_meta(active_section)['label']} settings updated.")
                return redirect("settings_section", section=active_section)
        elif active_section == "account" and action == "resend_verification":
            log_settings_change(request.user, active_section, "resend_verification", request, ["email"])
            messages.info(
                request,
                "Email verification delivery is not configured yet. Your account email is saved and ready for verification flow.",
            )
            return redirect("settings_section", section=active_section)
        elif active_section == "account" and action == "request_export":
            log_settings_change(request.user, active_section, "request_export", request, [])
            messages.success(
                request,
                "Export request recorded. Async export packaging can be connected next without changing this settings screen.",
            )
            return redirect("settings_section", section=active_section)
        elif active_section == "danger_zone" and action == "deactivate_account":
            deactivate_form = DangerZoneDeactivateForm(request.POST, user=request.user)
            if deactivate_form.is_valid():
                request.user.is_active = False
                request.user.save(update_fields=["is_active"])
                logout(request)
                messages.warning(request, "Your account has been deactivated.")
                return redirect("home")
        elif active_section == "danger_zone" and action == "delete_account":
            delete_form = DangerZoneDeleteForm(request.POST, user=request.user)
            if delete_form.is_valid():
                user = request.user
                logout(request)
                user.delete()
                return redirect("home")

    meta = get_settings_section_meta(active_section)
    return render(
        request,
        "trips/settings/base.html",
        {
            "settings_sidebar": build_settings_sidebar(active_section),
            "active_section": active_section,
            "active_section_meta": meta,
            "section_template": meta["template"],
            "form": form,
            "settings_bundle": bundle,
            "deactivate_form": deactivate_form,
            "delete_form": delete_form,
        },
    )


@login_required
def albums(request):
    albums_base_qs = (
        Album.objects.filter(user=request.user)
        .select_related("spot")
        .annotate(item_count=Count("items"))
        .order_by("-trip_date", "-created_at")
    )
    albums_qs = albums_base_qs

    q = request.GET.get("q", "").strip()
    date_from = request.GET.get("from_date", "").strip()
    date_to = request.GET.get("to_date", "").strip()

    if q:
        albums_qs = albums_qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
    if date_from:
        albums_qs = albums_qs.filter(trip_date__gte=date_from)
    if date_to:
        albums_qs = albums_qs.filter(trip_date__lte=date_to)

    album_form = AlbumForm(prefix="album")
    quick_item_form = AlbumItemForm(prefix="item")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create_album":
            album_form = AlbumForm(request.POST, prefix="album")
            if album_form.is_valid():
                album = album_form.save(commit=False)
                album.user = request.user
                album.save()
                messages.success(request, "Album created.")
                return redirect("albums")
        elif action == "quick_upload":
            quick_item_form = AlbumItemForm(request.POST, request.FILES, prefix="item")
            target_album_id = request.POST.get("target_album_id")
            target_album = Album.objects.filter(user=request.user, id=target_album_id).first()

            if not target_album:
                messages.error(request, "Select a valid album before uploading media.")
            elif quick_item_form.is_valid():
                media_item = quick_item_form.save(commit=False)
                media_item.album = target_album
                media_item.save()
                messages.success(request, "Media uploaded to album.")
                return redirect("albums")

    context = {
        "album_form": album_form,
        "quick_item_form": quick_item_form,
        "albums_for_upload": albums_base_qs,
        "albums": albums_qs,
        "q": q,
        "from_date": date_from,
        "to_date": date_to,
    }
    return render(request, "trips/albums.html", context)


@login_required
def album_detail(request, album_id):
    album = get_object_or_404(
        Album.objects.select_related("spot"),
        id=album_id,
        user=request.user,
    )
    items = album.items.all().order_by("-taken_at", "-created_at")

    item_date = request.GET.get("item_date", "").strip()
    if item_date:
        items = items.filter(taken_at=item_date)

    if request.method == "POST":
        item_form = AlbumItemForm(request.POST, request.FILES)
        if item_form.is_valid():
            item = item_form.save(commit=False)
            item.album = album
            item.save()
            messages.success(request, "Album photo/media added.")
            return redirect("album_detail", album_id=album.id)
    else:
        item_form = AlbumItemForm()

    return render(
        request,
        "trips/album_detail.html",
        {
            "album": album,
            "items": items,
            "item_form": item_form,
            "item_date": item_date,
        },
    )


@login_required
def stories(request):
    stories_qs = (
        Story.objects.filter(user=request.user)
        .select_related("spot")
        .order_by("-trip_date", "-created_at")
    )

    q = request.GET.get("q", "").strip()
    if q:
        stories_qs = stories_qs.filter(Q(title__icontains=q) | Q(content__icontains=q))

    if request.method == "POST":
        story_form = StoryForm(request.POST, request.FILES)
        if story_form.is_valid():
            story = story_form.save(commit=False)
            story.user = request.user
            story.save()
            messages.success(request, "Story published.")
            return redirect("stories")
    else:
        story_form = StoryForm()

    return render(
        request,
        "trips/stories.html",
        {
            "story_form": story_form,
            "stories": stories_qs,
            "q": q,
        },
    )


@login_required
def travel_history(request):
    history_qs = TravelHistory.objects.filter(user=request.user).order_by("-visit_date", "-created_at")

    place_filter = request.GET.get("place", "").strip()
    date_filter = request.GET.get("date", "").strip()
    if place_filter:
        history_qs = history_qs.filter(place_name__icontains=place_filter)
    if date_filter:
        history_qs = history_qs.filter(visit_date=date_filter)

    if request.method == "POST":
        history_form = TravelHistoryForm(request.POST, request.FILES)
        if history_form.is_valid():
            entry = history_form.save(commit=False)
            entry.user = request.user
            entry.save()
            messages.success(request, "History note saved.")
            return redirect("travel_history")
    else:
        history_form = TravelHistoryForm()

    context = {
        "history_form": history_form,
        "history_entries": history_qs,
        "place_filter": place_filter,
        "date_filter": date_filter,
    }
    return render(request, "trips/travel_history.html", context)


@login_required
def saved_spots(request):
    saved_qs = (
        SavedSpot.objects.filter(user=request.user)
        .select_related("spot__upazila__district__division")
        .order_by("-created_at")
    )

    if request.method == "POST":
        form = SavedSpotForm(request.POST)
        if form.is_valid():
            saved = form.save(commit=False)
            saved.user = request.user
            try:
                saved.save()
                messages.success(request, "Spot saved.")
                return redirect(_safe_redirect_url(request, "saved_spots"))
            except IntegrityError:
                messages.info(request, "This spot is already in your saved list.")
                return redirect(_safe_redirect_url(request, "saved_spots"))
    else:
        form = SavedSpotForm()

    return render(request, "trips/saved_spots.html", {"form": form, "saved_spots": saved_qs})


@login_required
@require_POST
def saved_spot_delete(request, saved_id):
    saved = get_object_or_404(SavedSpot, id=saved_id, user=request.user)
    saved.delete()
    messages.success(request, "Saved spot removed.")
    return redirect("saved_spots")


def travel_map(request):
    spots_qs = TourSpot.objects.select_related("upazila__district__division").annotate(
        total_visits=Count("trips"),
    )
    if request.user.is_authenticated:
        spots_qs = spots_qs.annotate(my_visits=Count("trips", filter=Q(trips__user=request.user)))
    else:
        spots_qs = spots_qs.annotate(my_visits=Value(0, output_field=IntegerField()))

    spots = spots_qs.order_by("name")

    map_spots = []
    for spot in spots:
        map_spots.append(
            {
                "id": spot.id,
                "name": spot.name,
                "category": spot.category,
                "division": spot.division.name,
                "district": spot.district.name,
                "upazila": spot.upazila.name,
                "latitude": float(spot.latitude) if spot.latitude is not None else None,
                "longitude": float(spot.longitude) if spot.longitude is not None else None,
                "total_visits": spot.total_visits,
                "my_visits": spot.my_visits,
            }
        )

    context = {
        "divisions_json": list(Division.objects.values("id", "name").order_by("name")),
        "map_spots_json": map_spots,
        "trip_count": Trip.objects.filter(user=request.user).count() if request.user.is_authenticated else 0,
    }
    return render(request, "trips/map.html", context)


def api_districts(request):
    division_id = request.GET.get("division_id")
    districts = District.objects.none()

    if division_id and division_id.isdigit():
        districts = District.objects.filter(division_id=division_id).order_by("name")

    return JsonResponse(
        {
            "results": [
                {"id": district.id, "name": district.name}
                for district in districts
            ]
        }
    )


def api_upazilas(request):
    district_id = request.GET.get("district_id")
    upazilas = Upazila.objects.none()

    if district_id and district_id.isdigit():
        upazilas = Upazila.objects.filter(district_id=district_id).order_by("name")

    return JsonResponse(
        {
            "results": [
                {"id": upazila.id, "name": upazila.name}
                for upazila in upazilas
            ]
        }
    )


def api_spots(request):
    upazila_id = request.GET.get("upazila_id")
    spots = TourSpot.objects.none()

    if upazila_id and upazila_id.isdigit():
        spots = TourSpot.objects.filter(upazila_id=upazila_id).order_by("name")

    return JsonResponse(
        {
            "results": [
                {
                    "id": spot.id,
                    "name": spot.name,
                    "has_coordinates": bool(spot.latitude and spot.longitude),
                }
                for spot in spots
            ]
        }
    )


def api_spot_insight(request):
    spot_id = request.GET.get("spot_id")

    if not spot_id or not spot_id.isdigit():
        return JsonResponse({"detail": "Valid spot_id is required."}, status=400)

    spot = get_object_or_404(
        TourSpot.objects.select_related("upazila__district__division"),
        id=spot_id,
    )

    spot_trips = (
        Trip.objects.filter(spot=spot)
        .select_related("user")
        .order_by("-from_date", "-created_at")
    )

    aggregates = spot_trips.aggregate(
        total_visits=Count("id"),
        unique_visitors=Count("user", distinct=True),
        average_cost=Avg("total_cost"),
    )

    last_visit = spot_trips.values_list("from_date", flat=True).first()

    recent_rows = []
    for trip in spot_trips[:5]:
        if trip.to_date:
            travel_date = f"{date_format(trip.from_date, 'Y-m-d')} to {date_format(trip.to_date, 'Y-m-d')}"
        else:
            travel_date = date_format(trip.from_date, "Y-m-d")

        recent_rows.append(
            {
                "visitor": trip.user.username,
                "travel_date": travel_date,
                "hotel": trip.hotel_name or "-",
                "total_cost": float(trip.total_cost),
            }
        )

    payload = {
        "spot": {
            "id": spot.id,
            "name": spot.name,
            "division": spot.division.name,
            "district": spot.district.name,
            "upazila": spot.upazila.name,
            "description": spot.description,
            "category": spot.category,
        },
        "stats": {
            "total_visits": aggregates["total_visits"] or 0,
            "unique_visitors": aggregates["unique_visitors"] or 0,
            "average_cost": float(aggregates["average_cost"] or 0),
            "last_visit_date": date_format(last_visit, "Y-m-d") if last_visit else None,
        },
        "recent_history": recent_rows,
    }

    return JsonResponse(payload)
