from datetime import datetime
import hashlib
import hmac
import logging
import math
import time
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.forms import AuthenticationForm
from django.db import transaction
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from .models import LoginThrottle, UserProfile


request_logger = logging.getLogger("trips.request")
security_logger = logging.getLogger("trips.security")


class OperationsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = self._request_id(request)
        request.request_id = request_id
        started_at = time.perf_counter()

        try:
            response = self.get_response(request)
        except Exception:
            request_logger.exception(
                "request_failed",
                extra=self._log_context(request, request_id, started_at, 500),
            )
            raise

        response.headers.setdefault("X-Request-ID", request_id)
        response.headers.setdefault("Permissions-Policy", settings.PERMISSIONS_POLICY)
        response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        request_logger.info(
            "request_completed",
            extra=self._log_context(request, request_id, started_at, response.status_code),
        )
        return response

    @staticmethod
    def _request_id(request):
        candidate = (request.headers.get("X-Request-ID") or "").strip()
        try:
            return str(uuid.UUID(candidate))
        except (ValueError, AttributeError):
            return str(uuid.uuid4())

    @staticmethod
    def _log_context(request, request_id, started_at, status_code):
        user = getattr(request, "user", None)
        return {
            "request_id": request_id,
            "method": request.method,
            "path": request.path,
            "status_code": status_code,
            "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
            "user_id": user.id if user and user.is_authenticated else None,
        }


class LoginThrottleMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method != "POST" or request.path != reverse("login"):
            return self.get_response(request)

        throttle_key = self._throttle_key(request)
        retry_after = self._retry_after(throttle_key)
        if retry_after:
            security_logger.warning(
                "login_throttled",
                extra={"request_id": getattr(request, "request_id", None), "path": request.path},
            )
            messages.error(request, "Too many login attempts. Please wait and try again.")
            response = render(
                request,
                "registration/login.html",
                {"form": AuthenticationForm(request=request)},
                status=429,
            )
            response.headers["Retry-After"] = str(retry_after)
            return response

        response = self.get_response(request)
        if request.user.is_authenticated:
            LoginThrottle.objects.filter(key=throttle_key).delete()
        else:
            self._record_failure(throttle_key)
        return response

    @staticmethod
    def _throttle_key(request):
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
        client_ip = forwarded_for.split(",", 1)[0].strip() or request.META.get("REMOTE_ADDR", "unknown")
        username = (request.POST.get("username") or "").strip().casefold()
        fingerprint = f"{client_ip}|{username}".encode("utf-8")
        return hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            fingerprint,
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _retry_after(throttle_key):
        attempt = LoginThrottle.objects.filter(key=throttle_key).first()
        if not attempt or not attempt.blocked_until:
            return 0
        remaining = (attempt.blocked_until - timezone.now()).total_seconds()
        return max(0, math.ceil(remaining))

    @staticmethod
    def _record_failure(throttle_key):
        now = timezone.now()
        window = timezone.timedelta(seconds=settings.LOGIN_THROTTLE_WINDOW_SECONDS)
        lock = timezone.timedelta(seconds=settings.LOGIN_THROTTLE_LOCK_SECONDS)

        with transaction.atomic():
            attempt, _ = LoginThrottle.objects.select_for_update().get_or_create(
                key=throttle_key,
                defaults={"window_started_at": now},
            )
            if attempt.window_started_at < now - window:
                attempt.failures = 0
                attempt.window_started_at = now
                attempt.blocked_until = None

            attempt.failures += 1
            if attempt.failures >= settings.LOGIN_THROTTLE_FAILURE_LIMIT:
                attempt.blocked_until = now + lock
            attempt.save()


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
