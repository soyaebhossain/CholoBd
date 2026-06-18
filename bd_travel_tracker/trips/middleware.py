from datetime import datetime

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from .models import UserProfile


class ProfileCompletionRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            return self.get_response(request)

        path = request.path
        static_url = settings.STATIC_URL or "/static/"
        media_url = settings.MEDIA_URL or "/media/"

        if path.startswith(static_url) or path.startswith(media_url) or path.startswith("/admin/"):
            return self.get_response(request)

        allowed_paths = {
            reverse("profile"),
            reverse("logout"),
        }

        if path in allowed_paths:
            return self.get_response(request)

        try:
            profile = request.user.profile
        except UserProfile.DoesNotExist:
            profile = UserProfile.objects.create(user=request.user)

        self._touch_last_active(request, profile)

        if not profile.is_profile_complete:
            return redirect("profile")

        return self.get_response(request)

    def _touch_last_active(self, request, profile):
        now = timezone.now()
        session_key = "last_active_touch"
        last_touch_value = request.session.get(session_key)
        if last_touch_value:
            try:
                last_touch = datetime.fromisoformat(last_touch_value)
                if timezone.is_naive(last_touch):
                    last_touch = timezone.make_aware(last_touch, timezone.get_current_timezone())
                if now - last_touch < timezone.timedelta(seconds=60):
                    return
            except ValueError:
                pass

        profile.last_active_at = now
        profile.save(update_fields=["last_active_at", "updated_at"])
        request.session[session_key] = now.isoformat()
