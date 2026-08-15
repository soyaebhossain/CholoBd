from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from trips.health import healthz, readyz
from trips import public_views
from trips.sitemaps import DestinationSitemap, StaticViewSitemap
from trips.views import TravelLoginView


sitemaps = {
    "destinations": DestinationSitemap,
    "static": StaticViewSitemap,
}

urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("readyz/", readyz, name="readyz"),
    path("manifest.webmanifest", public_views.web_manifest, name="web_manifest"),
    path("service-worker.js", public_views.service_worker, name="service_worker"),
    path("robots.txt", public_views.robots_txt, name="robots_txt"),
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="django.contrib.sitemaps.views.sitemap"),
    path("admin/", admin.site.urls),
    path("accounts/login/", TravelLoginView.as_view(), name="login"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", include("trips.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


handler400 = "trips.public_views.error_400"
handler403 = "trips.public_views.error_403"
handler404 = "trips.public_views.error_404"
handler500 = "trips.public_views.error_500"
