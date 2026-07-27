from __future__ import annotations

import base64
import binascii
from collections.abc import Sequence
from typing import Any

MAX_AGENT_IMAGES = 4
MAX_AGENT_IMAGE_BYTES = 8 * 1024 * 1024
MAX_AGENT_IMAGE_TOTAL_BYTES = 16 * 1024 * 1024
SUPPORTED_AGENT_IMAGE_MEDIA_TYPES = ("image/png", "image/jpeg", "image/webp")


def _matches_media_type(media_type: str, payload: bytes) -> bool:
    if media_type == "image/png":
        return payload.startswith(b"\x89PNG\r\n\x1a\n")
    if media_type == "image/jpeg":
        return payload.startswith(b"\xff\xd8\xff")
    if media_type == "image/webp":
        return len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WEBP"
    return False


def decoded_agent_image_size(media_type: str, data_url: str) -> int:
    if media_type not in SUPPORTED_AGENT_IMAGE_MEDIA_TYPES:
        raise ValueError(f"unsupported image media type: {media_type}")
    prefix = f"data:{media_type};base64,"
    if not data_url.startswith(prefix):
        raise ValueError("image data_url must be a matching base64 data URL")
    encoded = data_url[len(prefix) :]
    if not encoded:
        raise ValueError("image payload cannot be empty")
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("image payload is not valid base64") from exc
    if not payload:
        raise ValueError("image payload cannot be empty")
    if len(payload) > MAX_AGENT_IMAGE_BYTES:
        raise ValueError(
            f"each image must be at most {MAX_AGENT_IMAGE_BYTES // (1024 * 1024)} MiB"
        )
    if not _matches_media_type(media_type, payload):
        raise ValueError("image bytes do not match the declared media type")
    return len(payload)


def validate_agent_image_collection(images: Sequence[Any]) -> None:
    if len(images) > MAX_AGENT_IMAGES:
        raise ValueError(f"at most {MAX_AGENT_IMAGES} reference images are allowed")
    total = 0
    for image in images:
        data_url = image.data_url.get_secret_value()
        total += decoded_agent_image_size(image.media_type, data_url)
    if total > MAX_AGENT_IMAGE_TOTAL_BYTES:
        raise ValueError(
            "combined reference images must be at most "
            f"{MAX_AGENT_IMAGE_TOTAL_BYTES // (1024 * 1024)} MiB"
        )


def multimodal_user_content(text: str, images: Sequence[Any]) -> str | list[dict[str, Any]]:
    if not images:
        return text
    content: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for image in images:
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": image.data_url.get_secret_value(),
                    "detail": image.detail,
                },
            }
        )
    return content


def reference_image_prompt(images: Sequence[Any]) -> str:
    if not images:
        return ""
    names = ", ".join(image.name for image in images)
    return (
        "Reference image input:\n"
        f"{len(images)} image(s) are attached: {names}. Inspect the images directly. "
        "Treat visible equipment, instruments, labels, line routes, connection points, "
        "flow direction and relative layout as design evidence. Reconstruct them with real "
        "catalog symbols, semantic ports and connectors rather than tracing pixels or adding "
        "decorative shapes. Resolve ambiguity using the user's natural-language instruction.\n\n"
    )
