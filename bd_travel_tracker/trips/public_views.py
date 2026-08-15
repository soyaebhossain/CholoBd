from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.template import loader
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.cache import cache_control, never_cache
from django.views.decorators.http import require_GET


PUBLIC_PAGES = {
    "about": {
        "eyebrow": "About Cholo Bd",
        "title": "Travel planning built around real journeys",
        "description": "Cholo Bd brings trip planning, destination discovery, expense tracking, and traveler connections into one dependable platform.",
        "sections": (
            ("Our mission", "Make travel across Bangladesh easier to plan, safer to share, and simpler to remember."),
            ("What the platform does", "Travelers can discover destinations, build trips, track costs, save memories, and connect with the community."),
            ("How we build trust", "We use privacy controls, account security, operational monitoring, and transparent platform policies as core product features."),
        ),
    },
    "help": {
        "eyebrow": "Help Center",
        "title": "Get the most from every journey",
        "description": "Quick guidance for planning trips, managing your account, and using community features responsibly.",
        "sections": (
            ("Plan a trip", "Choose a destination, add travel dates and costs, then manage the journey from My Trips."),
            ("Manage your privacy", "Use Settings to control profile visibility, messages, notifications, albums, and stories."),
            ("Account access", "Keep your password private, sign out on shared devices, and review account security settings after any suspicious activity."),
            ("Community support", "Use the Safety Center guidance whenever content or an interaction makes you uncomfortable."),
        ),
    },
    "privacy": {
        "eyebrow": "Privacy Notice",
        "title": "Your travel data stays under your control",
        "description": "This notice explains what Cholo Bd stores, why it is needed, and the controls available to you.",
        "sections": (
            ("Information we use", "Account details, profile preferences, trips, expenses, saved destinations, messages, and media you choose to provide."),
            ("Why we use it", "To operate your account, provide travel features, protect the service, and improve reliability."),
            ("Visibility and sharing", "Your privacy settings determine how profile and community information is shown. Private trips are not published as community content."),
            ("Retention and deletion", "Account settings include data and danger-zone controls. A deletion request removes the account according to applicable retention obligations."),
            ("Security", "Connections use HTTPS, sensitive credentials are not logged, and access controls are monitored for abuse."),
        ),
    },
    "safety": {
        "eyebrow": "Safety Center",
        "title": "Plan confidently and share responsibly",
        "description": "Practical rules for safer travel planning and respectful community participation.",
        "sections": (
            ("Verify before travelling", "Confirm transport, accommodation, opening hours, weather, and local guidance with authoritative sources."),
            ("Protect personal information", "Do not publish passwords, financial details, identity documents, or precise live location in public posts."),
            ("Meet safely", "Meet new contacts in public places, tell someone you trust, and arrange your own transport."),
            ("Emergency situations", "Contact local emergency services first. Cholo Bd is a planning platform and not an emergency-response service."),
            ("Respect the community", "Avoid harassment, impersonation, scams, dangerous advice, and content that violates another person's privacy."),
        ),
    },
    "terms": {
        "eyebrow": "Terms of Use",
        "title": "Clear rules for using Cholo Bd",
        "description": "By using the platform, you agree to use travel and community features lawfully and responsibly.",
        "sections": (
            ("Your account", "Keep your credentials secure and provide accurate information. You are responsible for activity performed through your account."),
            ("Your content", "You retain ownership of content you submit and grant the platform permission to display it according to your selected visibility."),
            ("Acceptable use", "Do not misuse the service, attempt unauthorized access, distribute malware, spam users, or publish unlawful or deceptive content."),
            ("Travel information", "Destination and community information may change. Verify safety, pricing, schedules, and entry requirements before acting."),
            ("Service availability", "Features may be improved, limited, or temporarily unavailable for maintenance, security, or operational reasons."),
        ),
    },
}


def _public_page(request, page_key):
    return render(request, "platform/information_page.html", PUBLIC_PAGES[page_key])


@require_GET
def about(request):
    return _public_page(request, "about")


@require_GET
def help_center(request):
    return _public_page(request, "help")


@require_GET
def privacy(request):
    return _public_page(request, "privacy")


@require_GET
def safety(request):
    return _public_page(request, "safety")


@require_GET
def terms(request):
    return _public_page(request, "terms")


@require_GET
def offline(request):
    return render(request, "platform/offline.html")


@require_GET
@cache_control(public=True, max_age=86400)
def web_manifest(request):
    return JsonResponse(
        {
            "id": "/",
            "name": "Cholo Bd — Travel Bangladesh",
            "short_name": "Cholo Bd",
            "description": "Discover destinations, plan trips, track costs, and connect with travelers.",
            "lang": "en",
            "start_url": "/",
            "scope": "/",
            "display": "standalone",
            "background_color": "#f6f8f3",
            "theme_color": "#255f3d",
            "icons": [
                {
                    "src": static("images/app-icon.svg"),
                    "sizes": "any",
                    "type": "image/svg+xml",
                    "purpose": "any",
                },
                {
                    "src": static("images/app-icon-maskable.svg"),
                    "sizes": "any",
                    "type": "image/svg+xml",
                    "purpose": "maskable",
                },
            ],
            "shortcuts": [
                {"name": "Explore destinations", "url": reverse("destinations")},
                {"name": "Open travel map", "url": reverse("travel_map")},
            ],
        },
        content_type="application/manifest+json",
    )


@require_GET
@never_cache
def service_worker(request):
    source = loader.get_template("platform/service-worker.js").render()
    response = HttpResponse(source, content_type="text/javascript; charset=utf-8")
    response.headers["Service-Worker-Allowed"] = "/"
    return response


@require_GET
@cache_control(public=True, max_age=3600)
def robots_txt(request):
    sitemap_url = request.build_absolute_uri(reverse("django.contrib.sitemaps.views.sitemap"))
    content = "\n".join(
        (
            "User-agent: *",
            "Allow: /",
            "Disallow: /admin/",
            "Disallow: /accounts/",
            "Disallow: /api/",
            "Disallow: /messages/",
            "Disallow: /settings/",
            f"Sitemap: {sitemap_url}",
            "",
        )
    )
    return HttpResponse(content, content_type="text/plain; charset=utf-8")


def _error_response(template_name, status, title, message):
    html = loader.get_template(template_name).render({"title": title, "message": message})
    return HttpResponse(html, status=status)


def error_400(request, exception):
    return _error_response("errors/error.html", 400, "We could not process that request", "Check the submitted information and try again.")


def error_403(request, exception):
    return _error_response("errors/error.html", 403, "Access is not available", "Sign in with the right account or return to a page you can access.")


def error_404(request, exception):
    return _error_response("errors/error.html", 404, "That page could not be found", "The link may be outdated, or the page may have moved.")


def error_500(request):
    return _error_response("errors/error.html", 500, "Something went wrong", "The service encountered an unexpected problem. Please try again shortly.")
