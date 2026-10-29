import hashlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

from .scenarios import VisualObject, get_scenario


@dataclass(frozen=True)
class RenderedScene:
    scenario_version: str
    png_bytes: bytes
    sha256: str
    width_px: int
    height_px: int
    camera_transform: tuple[float, float, float, float, float, float]


def render_scene(scenario_version: str) -> RenderedScene:
    scenario = get_scenario(scenario_version)
    width = 800
    height = 600
    pixels_per_meter = 100.0
    image = Image.new("RGBA", (width, height), (238, 242, 239, 255))
    draw = ImageDraw.Draw(image)

    for obstacle in scenario.obstacles:
        draw.rectangle(
            (
                round(obstacle.x_min_m * pixels_per_meter),
                round(obstacle.y_min_m * pixels_per_meter),
                round(obstacle.x_max_m * pixels_per_meter),
                round(obstacle.y_max_m * pixels_per_meter),
            ),
            fill=(91, 101, 96, 255),
        )
    for item in scenario.visual_objects:
        _composite_visual_object(image, item, pixels_per_meter)

    draw.rectangle((85, 285, 115, 315), fill=(35, 58, 50, 255))
    draw.ellipse((91, 291, 109, 309), fill=(72, 104, 91, 255))
    output = BytesIO()
    image.convert("RGB").save(output, format="PNG", optimize=False, compress_level=9)
    png_bytes = output.getvalue()
    return RenderedScene(
        scenario_version=scenario_version,
        png_bytes=png_bytes,
        sha256=hashlib.sha256(png_bytes).hexdigest(),
        width_px=width,
        height_px=height,
        camera_transform=(0.01, 0.0, 0.0, 0.0, 0.01, 0.0),
    )


def _composite_visual_object(
    scene: Image.Image, item: VisualObject, pixels_per_meter: float
) -> None:
    asset_name = {
        "Red toolbox": "red-toolbox.png",
        "Blue barrel": "blue-barrel.png",
    }.get(item.label)
    if asset_name is None:
        raise ValueError(f"unsupported perception asset label: {item.label}")
    asset_path = (
        Path(__file__).resolve().parents[2]
        / "web"
        / "public"
        / "assets"
        / "perception"
        / asset_name
    )
    with Image.open(asset_path) as source:
        asset = source.convert("RGBA")
    target_width = round((item.x_max_m - item.x_min_m) * pixels_per_meter)
    target_height = round((item.y_max_m - item.y_min_m) * pixels_per_meter)
    asset.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
    left = round(item.x_min_m * pixels_per_meter + (target_width - asset.width) / 2)
    top = round(item.y_min_m * pixels_per_meter + (target_height - asset.height) / 2)
    scene.alpha_composite(asset, (left, top))
