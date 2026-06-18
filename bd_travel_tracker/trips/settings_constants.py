SETTINGS_SECTIONS = [
    "account",
    "profile",
    "privacy",
    "security",
    "appearance",
    "notifications",
    "danger_zone",
]

SETTINGS_META = {
    "account": {
        "label": "Account",
        "icon": "bi-person-gear",
        "description": "Private account details, verification, recovery, and data access.",
        "template": "trips/settings/section_account.html",
    },
    "profile": {
        "label": "Profile Settings",
        "icon": "bi-person-badge",
        "description": "Edit the public identity shown on your profile page.",
        "template": "trips/settings/section_profile.html",
    },
    "privacy": {
        "label": "Privacy",
        "icon": "bi-shield-lock",
        "description": "Control profile visibility and who can message or comment.",
        "template": "trips/settings/section_privacy.html",
    },
    "security": {
        "label": "Security",
        "icon": "bi-lock",
        "description": "Password, alerts, recovery, and account protection.",
        "template": "trips/settings/section_security.html",
    },
    "appearance": {
        "label": "Appearance",
        "icon": "bi-circle-half",
        "description": "Theme, language, density, font size, and map style preferences.",
        "template": "trips/settings/section_appearance.html",
    },
    "notifications": {
        "label": "Notifications",
        "icon": "bi-bell",
        "description": "Tune in-app, email, push, and reminder alerts.",
        "template": "trips/settings/section_notifications.html",
    },
    "danger_zone": {
        "label": "Danger Zone",
        "icon": "bi-exclamation-triangle",
        "description": "Deactivate or remove your account with strict confirmation steps.",
        "template": "trips/settings/section_danger_zone.html",
    },
}

VISIBILITY_CHOICES = [
    ("private", "Private"),
    ("followers", "Followers Only"),
    ("public", "Public"),
]

INTERACTION_CHOICES = [
    ("no_one", "No one"),
    ("followers", "Followers Only"),
    ("community", "Community Members"),
    ("everyone", "Everyone"),
]

FONT_SIZE_CHOICES = [
    ("sm", "Small"),
    ("md", "Medium"),
    ("lg", "Large"),
]

LAYOUT_DENSITY_CHOICES = [
    ("compact", "Compact"),
    ("comfortable", "Comfortable"),
]

MAP_STYLE_CHOICES = [
    ("roadmap", "Roadmap"),
    ("terrain", "Terrain"),
    ("satellite", "Satellite"),
]

DATE_FORMAT_CHOICES = [
    ("DD/MM/YYYY", "DD/MM/YYYY"),
    ("MM/DD/YYYY", "MM/DD/YYYY"),
    ("YYYY-MM-DD", "YYYY-MM-DD"),
]

CURRENCY_CHOICES = [
    ("BDT", "Bangladeshi Taka (BDT)"),
    ("USD", "US Dollar (USD)"),
    ("EUR", "Euro (EUR)"),
    ("INR", "Indian Rupee (INR)"),
]

TIMEZONE_CHOICES = [
    ("Asia/Dhaka", "Asia/Dhaka"),
    ("UTC", "UTC"),
    ("Asia/Kolkata", "Asia/Kolkata"),
    ("Asia/Singapore", "Asia/Singapore"),
]

IMAGE_QUALITY_CHOICES = [
    ("optimized", "Optimized"),
    ("high", "High"),
    ("original", "Original"),
]

VIDEO_UPLOAD_LIMIT_CHOICES = [
    ("100", "100 MB"),
    ("250", "250 MB"),
    ("500", "500 MB"),
]

STORAGE_PROVIDER_CHOICES = [
    ("none", "Keep uploads in app storage"),
    ("google_photos", "Google Photos"),
    ("google_drive", "Google Drive"),
]

MAP_VIEW_CHOICES = [
    ("division", "Division View"),
    ("district", "District View"),
    ("spot", "Spot View"),
]

DISTANCE_UNIT_CHOICES = [
    ("km", "Kilometers"),
    ("mi", "Miles"),
]

EXPORT_FORMAT_CHOICES = [
    ("zip", "ZIP Archive"),
    ("json", "JSON"),
    ("csv", "CSV"),
]
