from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("trips", "0005_communitymembership"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="contact_visibility",
            field=models.CharField(
                choices=[("private", "Private"), ("public", "Public")],
                default="private",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="cover_photo",
            field=models.FileField(blank=True, null=True, upload_to="covers/"),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="date_of_birth",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="default_album_visibility",
            field=models.CharField(
                choices=[("private", "Private"), ("public", "Public")],
                default="private",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="default_story_visibility",
            field=models.CharField(
                choices=[("private", "Private"), ("public", "Public")],
                default="public",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="gender",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "Prefer not to say"),
                    ("male", "Male"),
                    ("female", "Female"),
                    ("other", "Other"),
                ],
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="location",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="website",
            field=models.URLField(blank=True),
        ),
    ]
