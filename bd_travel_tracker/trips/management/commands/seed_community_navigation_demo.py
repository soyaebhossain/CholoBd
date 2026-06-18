import base64
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone

from trips.models import (
    CommunityComment,
    CommunityMembership,
    CommunityPost,
    CommunityPostMedia,
    CommunityPostReaction,
    CommunityPostSave,
    CommunityPostView,
    District,
    Division,
    TourSpot,
    Upazila,
)


TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlAbN8AAAAASUVORK5CYII="
)


class Command(BaseCommand):
    help = "Seed community navigation demo data for Cholo Bd."

    def handle(self, *args, **options):
        users = self._seed_users()
        spots = self._seed_locations()
        posts = self._seed_posts(users, spots)
        self._seed_engagement(users, posts)
        self.stdout.write(self.style.SUCCESS("Community navigation demo data seeded."))

    def _seed_users(self):
        user_model = get_user_model()
        user_specs = [
            ("traveler", "Traveler User", "01700000000"),
            ("ayesha", "Ayesha Rahman", "01711000001"),
            ("tanvir", "Tanvir Hasan", "01711000002"),
            ("maria", "Maria Akter", "01711000003"),
            ("farhan", "Farhan Islam", "01711000004"),
            ("nusrat", "Nusrat Jahan", "01711000005"),
        ]
        users = {}
        for username, full_name, phone in user_specs:
            user, created = user_model.objects.get_or_create(
                username=username,
                defaults={"email": f"{username}@example.com"},
            )
            if created:
                user.set_password("demo12345")
                user.save(update_fields=["password"])
            user.email = f"{username}@example.com"
            user.save(update_fields=["email"])
            user.profile.full_name = full_name
            user.profile.phone = phone
            user.profile.bio = f"{full_name} shares Bangladesh travel updates."
            user.profile.last_active_at = timezone.now()
            user.profile.save(update_fields=["full_name", "phone", "bio", "last_active_at"])
            CommunityMembership.objects.get_or_create(user=user, defaults={"is_active": True})
            users[username] = user
        return users

    def _seed_locations(self):
        locations = {}
        specs = [
            ("Dhaka", "Dhaka", "Dhanmondi", "Ahsan Manzil"),
            ("Chattogram", "Rangamati", "Baghaichhari", "Sajek Valley"),
            ("Chattogram", "Cox's Bazar", "Teknaf", "Saint Martin"),
            ("Sylhet", "Moulvibazar", "Sreemangal", "Lawachara National Park"),
            ("Khulna", "Bagerhat", "Mongla", "Sundarbans"),
        ]
        for division_name, district_name, upazila_name, spot_name in specs:
            division, _ = Division.objects.get_or_create(name=division_name)
            district, _ = District.objects.get_or_create(name=district_name, division=division)
            upazila, _ = Upazila.objects.get_or_create(name=upazila_name, district=district)
            spot, _ = TourSpot.objects.get_or_create(
                name=spot_name,
                upazila=upazila,
                defaults={"category": "Travel"},
            )
            locations[spot_name] = spot
        return locations

    def _seed_posts(self, users, spots):
        now = timezone.now()
        post_specs = [
            {
                "user": users["ayesha"],
                "post_type": "discussion",
                "title": "Best sunrise viewpoint in Sajek right now?",
                "content": "I want a quiet sunrise point with fewer crowds. Which trail is worth it this season?",
                "spot": spots["Sajek Valley"],
                "hashtags": "#sajek, #discussion, #sunrise",
                "days_ago": 0,
                "media": True,
            },
            {
                "user": users["tanvir"],
                "post_type": "help",
                "title": "Need help with Teknaf to Saint Martin launch timing",
                "content": "I am hearing mixed launch timings. Does anyone know the safest morning option?",
                "spot": spots["Saint Martin"],
                "hashtags": "#help, #launch, #saintmartin",
                "days_ago": 1,
            },
            {
                "user": users["maria"],
                "post_type": "trip_planning",
                "title": "3-day Sreemangal itinerary check",
                "content": "Planning tea garden visits, Lawachara, and local food. Please review this route order.",
                "spot": spots["Lawachara National Park"],
                "hashtags": "#tripplan, #sreemangal, #itinerary",
                "days_ago": 2,
            },
            {
                "user": users["farhan"],
                "post_type": "budget_travel",
                "title": "Low-cost Cox's Bazar weekend under 7000 BDT",
                "content": "Sharing bus, dorm stay, food cost, and beach transport breakdown for a tight budget.",
                "spot": spots["Saint Martin"],
                "hashtags": "#budget, #cheaptrip, #fare",
                "days_ago": 3,
            },
            {
                "user": users["nusrat"],
                "post_type": "hotels_stay",
                "title": "Family-friendly hotel near Dhanmondi heritage spots",
                "content": "Looking for safe stay options with parking and clean rooms for parents.",
                "spot": spots["Ahsan Manzil"],
                "hashtags": "#hotel, #stay, #familytrip",
                "days_ago": 4,
            },
            {
                "user": users["traveler"],
                "post_type": "transport_advice",
                "title": "Night bus safety tips for Khulna route",
                "content": "Which operator is safest and what fare range should I expect this week?",
                "spot": spots["Sundarbans"],
                "hashtags": "#transport, #bus, #safety, #fare",
                "days_ago": 5,
            },
            {
                "user": users["ayesha"],
                "post_type": "travel_guide",
                "title": "Beginner guide to visiting Sundarbans responsibly",
                "content": "Packing list, permit prep, guide booking, and wildlife safety basics for first-timers.",
                "spot": spots["Sundarbans"],
                "hashtags": "#guide, #sundarbans, #tips",
                "days_ago": 6,
                "media": True,
            },
            {
                "user": users["tanvir"],
                "post_type": "help",
                "title": "Resolved: local guide number for Lawachara trail",
                "content": "Found a verified local guide after checking forest gate contacts.",
                "spot": spots["Lawachara National Park"],
                "hashtags": "#help, #resolved, #guide",
                "days_ago": 7,
                "resolved": True,
            },
            {
                "user": users["maria"],
                "post_type": "discussion",
                "title": "Is Sajek better in monsoon or winter for photographers?",
                "content": "Trying to choose between cloud layers in monsoon and cleaner skies in winter.",
                "spot": spots["Sajek Valley"],
                "hashtags": "#discussion, #photography, #sajek",
                "days_ago": 8,
            },
            {
                "user": users["farhan"],
                "post_type": "budget_travel",
                "title": "Backpacker launch and hostel combo for Saint Martin",
                "content": "Here is a low-cost combo that saved me money without sacrificing safety.",
                "spot": spots["Saint Martin"],
                "hashtags": "#budget, #hostel, #launch",
                "days_ago": 9,
                "media": True,
            },
        ]

        posts = []
        for spec in post_specs:
            spot = spec["spot"]
            post, _ = CommunityPost.objects.update_or_create(
                user=spec["user"],
                title=spec["title"],
                defaults={
                    "post_type": spec["post_type"],
                    "content": spec["content"],
                    "district": spot.district,
                    "spot": spot,
                    "location_name": spot.name,
                    "hashtags": spec["hashtags"],
                    "is_resolved": spec.get("resolved", False),
                },
            )
            CommunityPost.objects.filter(id=post.id).update(created_at=now - timedelta(days=spec["days_ago"]))
            post.refresh_from_db()
            if spec.get("media"):
                self._attach_demo_image(post)
            posts.append(post)
        return posts

    def _attach_demo_image(self, post):
        if post.media_items.filter(media_type="image").exists():
            return
        media = CommunityPostMedia(post=post, media_type="image", caption=post.title, sort_order=1)
        media.file.save(f"seed-post-{post.id}.png", ContentFile(TINY_PNG), save=False)
        media.save()

    def _seed_engagement(self, users, posts):
        if not posts:
            return

        rotation = list(users.values())
        for index, post in enumerate(posts):
            commenter = rotation[(index + 1) % len(rotation)]
            CommunityComment.objects.get_or_create(
                post=post,
                user=commenter,
                defaults={"content": f"Useful thread on {post.spot.name if post.spot else 'this route'}."},
            )

            for offset in range(2):
                reacting_user = rotation[(index + offset + 2) % len(rotation)]
                CommunityPostReaction.objects.get_or_create(post=post, user=reacting_user, defaults={"reaction": "like"})

            saver = rotation[(index + 3) % len(rotation)]
            CommunityPostSave.objects.get_or_create(post=post, user=saver)

            for viewer in rotation[:4]:
                CommunityPostView.objects.get_or_create(post=post, user=viewer)
