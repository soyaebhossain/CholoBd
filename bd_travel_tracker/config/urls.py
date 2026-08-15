from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from trips.health import healthz, readyz
from trips.views import TravelLoginView

urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("readyz/", readyz, name="readyz"),
    path("admin/", admin.site.urls),
    path("accounts/login/", TravelLoginView.as_view(), name="login"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", include("trips.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
