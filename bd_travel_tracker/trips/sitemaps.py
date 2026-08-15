from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from .models import TourSpot


class StaticViewSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return (
            "home",
            "destinations",
            "travel_map",
            "community",
            "about",
            "help_center",
            "privacy",
            "safety",
            "terms",
        )

    def location(self, item):
        return reverse(item)

    def priority(self, item):
        return 1.0 if item == "home" else 0.7


class DestinationSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.8

    def items(self):
        return TourSpot.objects.only("id").order_by("id")

    def location(self, item):
        return reverse("destination_detail", args=[item.id])
