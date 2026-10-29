import base64
import hashlib
from collections.abc import Callable
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from typing import cast

from PIL import Image

from .models import Pose
from .scenarios import Obstacle, SceneDraft, VisualObject

PHOTO_STORE = Path(__file__).resolve().parents[2] / ".roveredge" / "photos"
MAX_PHOTO_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class PhotoDraftRequest:
    name: str
    data_url: str


def create_photo_draft(request: PhotoDraftRequest) -> dict[str, object]:
    if not request.name.strip():
        raise ValueError("photo draft name is required")
    media_type, photo_bytes = _decode_data_url(request.data_url)
    try:
        image = Image.open(BytesIO(photo_bytes)).convert("RGB")
        image.verify()
    except Exception as error:
        raise ValueError("uploaded reference must be a valid PNG or JPEG image") from error
    image = Image.open(BytesIO(photo_bytes)).convert("RGB")
    if image.width < 32 or image.height < 32:
        raise ValueError("uploaded reference must be at least 32 by 32 pixels")

    photo_sha256 = hashlib.sha256(photo_bytes).hexdigest()
    PHOTO_STORE.mkdir(parents=True, exist_ok=True)
    suffix = ".png" if media_type == "image/png" else ".jpg"
    destination = PHOTO_STORE / f"{photo_sha256}{suffix}"
    if not destination.exists():
        temporary = destination.with_suffix(".tmp")
        temporary.write_bytes(photo_bytes)
        temporary.replace(destination)

    targets: list[VisualObject] = []
    red_box = _color_bounds(
        image,
        lambda red, green, blue: red > 150 and red > green * 1.4 and red > blue * 1.4,
    )
    blue_box = _color_bounds(
        image,
        lambda red, green, blue: blue > 120 and blue > red * 1.25 and blue > green * 1.1,
    )
    if red_box is not None:
        targets.append(_target_from_pixels("photo-red-target", "Red toolbox", red_box, image.size))
    if blue_box is not None:
        targets.append(
            _target_from_pixels("photo-blue-target", "Blue barrel", blue_box, image.size)
        )

    dark_box = _color_bounds(image, lambda red, green, blue: max(red, green, blue) < 80)
    obstacles = (
        (_obstacle_from_pixels("photo-dark-region", dark_box, image.size),)
        if dark_box is not None
        else ()
    )
    draft = SceneDraft(
        name=request.name.strip(),
        width_m=8.0,
        height_m=6.0,
        pixels_per_meter=100.0,
        dock_pose=Pose(1.0, 3.0, 0.0),
        obstacles=obstacles,
        targets=tuple(targets),
        photo_reference_sha256=photo_sha256,
    )
    uncertainty = [
        "Scale defaults to 100 px/m and is not measured from the photograph.",
        "Dock pose is a default and must be placed by the user.",
        "Colored and dark regions are rough 2D proposals, not metric reconstruction.",
    ]
    if not targets:
        uncertainty.append(
            "No supported colored target was proposed; add a target before confirmation."
        )
    if not obstacles:
        uncertainty.append(
            "No dark obstacle region was proposed; add obstacle footprints as needed."
        )
    return {
        "method": "rough_color_region_proposals_v1",
        "claim": "heuristic draft only; no automatic metric or hidden-geometry reconstruction",
        "photo_reference": {
            "sha256": photo_sha256,
            "url": f"/api/photo-references/{photo_sha256}",
            "media_type": media_type,
        },
        "uncertainty": uncertainty,
        "draft": asdict(draft),
    }


def get_photo_reference(photo_sha256: str) -> tuple[bytes, str]:
    if len(photo_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in photo_sha256
    ):
        raise ValueError("unknown photo reference")
    for suffix, media_type in ((".png", "image/png"), (".jpg", "image/jpeg")):
        path = PHOTO_STORE / f"{photo_sha256}{suffix}"
        if path.is_file():
            return path.read_bytes(), media_type
    raise ValueError("unknown photo reference")


def _decode_data_url(data_url: str) -> tuple[str, bytes]:
    prefix, separator, encoded = data_url.partition(",")
    if not separator or prefix not in {"data:image/png;base64", "data:image/jpeg;base64"}:
        raise ValueError("photo must be a base64 PNG or JPEG data URL")
    try:
        photo_bytes = base64.b64decode(encoded, validate=True)
    except ValueError as error:
        raise ValueError("photo data URL contains invalid base64") from error
    if not photo_bytes or len(photo_bytes) > MAX_PHOTO_BYTES:
        raise ValueError("photo must contain 1 byte to 8 MiB")
    return prefix.removeprefix("data:").removesuffix(";base64"), photo_bytes


def _color_bounds(
    image: Image.Image, predicate: Callable[[int, int, int], bool]
) -> tuple[int, int, int, int] | None:
    points: list[tuple[int, int]] = []
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue = cast(tuple[int, int, int], image.getpixel((x, y)))
            if predicate(red, green, blue):
                points.append((x, y))
    if len(points) < max(16, image.width * image.height // 500):
        return None
    xs, ys = zip(*points, strict=True)
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def _floor_bounds(
    box: tuple[int, int, int, int], image_size: tuple[int, int]
) -> tuple[float, float, float, float]:
    left, top, right, bottom = box
    width, height = image_size
    return (
        round(left / width * 8.0, 3),
        round(top / height * 6.0, 3),
        round(right / width * 8.0, 3),
        round(bottom / height * 6.0, 3),
    )


def _target_from_pixels(
    identity: str,
    label: str,
    box: tuple[int, int, int, int],
    image_size: tuple[int, int],
) -> VisualObject:
    left, top, right, bottom = _floor_bounds(box, image_size)
    color = (196, 54, 45) if label == "Red toolbox" else (42, 92, 168)
    return VisualObject(identity, label, left, top, right, bottom, color)


def _obstacle_from_pixels(
    identity: str, box: tuple[int, int, int, int], image_size: tuple[int, int]
) -> Obstacle:
    return Obstacle(identity, *_floor_bounds(box, image_size))
