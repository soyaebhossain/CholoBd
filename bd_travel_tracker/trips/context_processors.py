from .models import CommunityNotification, UserProfile


def user_preferences(request):
    theme = "light"
    language = "en"
    notification_unread_count = 0

    if request.user.is_authenticated:
        try:
            profile = request.user.profile
        except UserProfile.DoesNotExist:
            profile = UserProfile.objects.create(user=request.user)
        theme = profile.theme_mode or "light"
        language = profile.preferred_language or "en"
        notification_unread_count = CommunityNotification.objects.filter(
            user=request.user,
            is_read=False,
        ).count()

    return {
        "active_theme": theme,
        "active_language": language,
        "notification_unread_count": notification_unread_count,
    }
