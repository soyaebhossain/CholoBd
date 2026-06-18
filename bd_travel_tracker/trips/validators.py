import os
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db.models.fields.files import FieldFile
from django.utils.text import get_valid_filename

ONE_MB = 1024 * 1024

IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}
VIDEO_EXTENSIONS = {"mp4", "webm", "mov"}
AUDIO_EXTENSIONS = {"mp3", "wav", "ogg", "m4a"}
MEDIA_LIBRARY_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | AUDIO_EXTENSIONS

AVATAR_MAX_BYTES = 2 * ONE_MB
IMAGE_MAX_BYTES = 5 * ONE_MB
AUDIO_MAX_BYTES = 10 * ONE_MB
VIDEO_MAX_BYTES = 50 * ONE_MB


def _format_max_size(max_size_bytes):
    if max_size_bytes % ONE_MB == 0:
        return f"{max_size_bytes // ONE_MB} MB"
    return f"{max_size_bytes} bytes"


def sanitize_uploaded_name(upload):
    if not upload or not getattr(upload, "name", ""):
        return upload

    original_name = os.path.basename(upload.name)
    safe_name = get_valid_filename(original_name) or "upload"
    suffix = Path(safe_name).suffix.lower()
    stem = Path(safe_name).stem[:80] or "upload"
    upload.name = f"{stem}{suffix}"
    return upload


def validate_upload(upload, *, allowed_extensions, max_size_bytes, label):
    if not upload:
        return

    # Bound forms may hand back an already-saved FieldFile when no new upload was chosen.
    # Re-validating its size can explode if the underlying file has been removed on disk.
    if isinstance(upload, FieldFile):
        return

    sanitize_uploaded_name(upload)
    suffix = Path(upload.name).suffix.lower().lstrip(".")

    if not suffix or suffix not in allowed_extensions:
        allowed = ", ".join(sorted(allowed_extensions))
        raise ValidationError(f"{label} must use one of these file types: {allowed}.")

    if upload.size > max_size_bytes:
        readable_limit = _format_max_size(max_size_bytes)
        raise ValidationError(f"{label} must be {readable_limit} or smaller.")


def validate_album_media_upload(upload, label="Media file"):
    if not upload:
        return

    if isinstance(upload, FieldFile):
        return

    sanitize_uploaded_name(upload)
    suffix = Path(upload.name).suffix.lower().lstrip(".")

    if suffix in IMAGE_EXTENSIONS:
        max_size = IMAGE_MAX_BYTES
    elif suffix in AUDIO_EXTENSIONS:
        max_size = AUDIO_MAX_BYTES
    elif suffix in VIDEO_EXTENSIONS:
        max_size = VIDEO_MAX_BYTES
    else:
        allowed = ", ".join(sorted(MEDIA_LIBRARY_EXTENSIONS))
        raise ValidationError(f"{label} must use one of these file types: {allowed}.")

    validate_upload(
        upload,
        allowed_extensions=MEDIA_LIBRARY_EXTENSIONS,
        max_size_bytes=max_size,
        label=label,
    )
