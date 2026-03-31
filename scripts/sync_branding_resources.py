from __future__ import annotations

import argparse
import os
import subprocess
from collections import deque
from pathlib import Path

from PIL import Image, ImageChops, ImageOps

ICON_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
RESOURCE_ALIASES: dict[str, tuple[str, ...]] = {
    "icon": ("icon_black", "icons", "icon"),
    "welcome": ("welcome",),
    "working1": ("working1",),
    "working2": ("working2",),
    "working3": ("working3",),
    "working4": ("working4",),
    "working5": ("working5",),
    "tired": ("tired",),
    "panic": ("panic",),
    "desperate": ("desperate",),
    "fail": ("fail",),
    "sad": ("sad",),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync branding assets into embedded Qt resources.")
    parser.add_argument("--images-dir", type=Path, default=Path("images"), help="Directory containing branding source images.")
    parser.add_argument(
        "--resources-dir",
        type=Path,
        default=Path("src") / "emtranscriber" / "ui" / "resources",
        help="Output resource directory.",
    )
    parser.add_argument(
        "--icon-output",
        type=Path,
        default=Path("packaging") / "assets" / "emtranscriber.ico",
        help="Generated icon output path for PyInstaller --icon.",
    )
    return parser


def find_image_by_stems(images_dir: Path, stems: tuple[str, ...]) -> Path:
    images = [path for path in images_dir.iterdir() if path.is_file()]
    for stem in stems:
        matches = [path for path in images if path.stem.lower() == stem.lower()]
        if matches:
            matches.sort(key=lambda path: path.name.lower())
            return matches[0]
    raise FileNotFoundError(f"Missing branding image for stems {stems} in {images_dir}")


def _crop_uniform_background(image: Image.Image, *, tolerance: int = 12, padding: int = 8) -> Image.Image:
    rgb = image.convert("RGB")
    bg_color = rgb.getpixel((0, 0))
    bg = Image.new("RGB", rgb.size, bg_color)
    diff = ImageChops.difference(rgb, bg)
    mask = diff.convert("L").point(lambda value: 255 if value > tolerance else 0)
    bbox = mask.getbbox()
    if bbox is None:
        return image

    left, top, right, bottom = bbox
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(image.width, right + padding)
    bottom = min(image.height, bottom + padding)
    return image.crop((left, top, right, bottom))


def _is_bg_pixel(rgb: tuple[int, int, int], bg: tuple[int, int, int], tolerance: int) -> bool:
    return (
        abs(rgb[0] - bg[0]) <= tolerance
        and abs(rgb[1] - bg[1]) <= tolerance
        and abs(rgb[2] - bg[2]) <= tolerance
    )


def _make_outer_background_transparent(image: Image.Image, *, tolerance: int = 12) -> Image.Image:
    rgba = image.convert("RGBA")
    rgb = rgba.convert("RGB")
    width, height = rgba.size
    bg = rgb.getpixel((0, 0))

    background_like = [False] * (width * height)
    rgb_pixels = rgb.load()
    for y in range(height):
        row_offset = y * width
        for x in range(width):
            background_like[row_offset + x] = _is_bg_pixel(rgb_pixels[x, y], bg, tolerance)

    visited = [False] * (width * height)
    queue: deque[tuple[int, int]] = deque()

    def enqueue_if_bg(x: int, y: int) -> None:
        index = y * width + x
        if not visited[index] and background_like[index]:
            visited[index] = True
            queue.append((x, y))

    for x in range(width):
        enqueue_if_bg(x, 0)
        enqueue_if_bg(x, height - 1)
    for y in range(height):
        enqueue_if_bg(0, y)
        enqueue_if_bg(width - 1, y)

    while queue:
        x, y = queue.popleft()
        if x > 0:
            enqueue_if_bg(x - 1, y)
        if x + 1 < width:
            enqueue_if_bg(x + 1, y)
        if y > 0:
            enqueue_if_bg(x, y - 1)
        if y + 1 < height:
            enqueue_if_bg(x, y + 1)

    alpha = rgba.getchannel("A")
    alpha_pixels = alpha.load()
    for y in range(height):
        row_offset = y * width
        for x in range(width):
            if visited[row_offset + x]:
                alpha_pixels[x, y] = 0

    rgba.putalpha(alpha)
    return rgba


def _prepare_square_icon_image(icon_source: Path) -> Image.Image:
    image = ImageOps.exif_transpose(Image.open(icon_source)).convert("RGBA")

    # icons.png may contain multiple variants side by side; keep the left one as fallback icon source.
    if icon_source.stem.lower() == "icons" and image.width > image.height:
        image = image.crop((0, 0, image.width // 2, image.height))

    image = _crop_uniform_background(image)
    image = _make_outer_background_transparent(image)
    return ImageOps.fit(image, (1024, 1024), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def generate_icon(square_image: Image.Image, icon_output: Path) -> None:
    icon_output.parent.mkdir(parents=True, exist_ok=True)
    square_image.save(icon_output, format="ICO", sizes=ICON_SIZES)


def save_icon_png(square_image: Image.Image, png_output: Path) -> None:
    png_output.parent.mkdir(parents=True, exist_ok=True)
    square_image.save(png_output, format="PNG")


def write_qrc(resources_dir: Path, files_by_alias: dict[str, Path]) -> Path:
    resources_dir.mkdir(parents=True, exist_ok=True)
    qrc_path = resources_dir / "branding.qrc"

    lines = ["<RCC>", '  <qresource prefix="/branding">']
    for alias in sorted(files_by_alias):
        rel_path = os.path.relpath(files_by_alias[alias], resources_dir).replace("\\", "/")
        lines.append(f'    <file alias="{alias}">{rel_path}</file>')
    lines.append("  </qresource>")
    lines.append("</RCC>")

    qrc_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return qrc_path


def compile_qrc_to_python(qrc_path: Path, output_py: Path) -> None:
    try:
        import PySide6
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("PySide6 is required to compile branding resources.") from exc

    pyside_root = Path(PySide6.__file__).resolve().parent
    rcc_exe = pyside_root / "rcc.exe"
    if not rcc_exe.exists():
        raise FileNotFoundError(f"Unable to locate rcc.exe at {rcc_exe}")

    output_py.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(rcc_exe), "-g", "python", str(qrc_path), "-o", str(output_py)]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(
            "Qt resource compilation failed:\n"
            f"Command: {' '.join(cmd)}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )


def main() -> int:
    args = build_parser().parse_args()

    images_dir = args.images_dir.resolve()
    
    # If images directory doesn't exist, skip branding resource generation
    # and use default/existing resources
    if not images_dir.exists() or not images_dir.is_dir():
        print(f"Warning: Images directory not found at {images_dir}")
        print("Skipping branding resource sync. Using existing resources if available.")
        return 0

    files_by_alias: dict[str, Path] = {}
    for alias, stems in RESOURCE_ALIASES.items():
        files_by_alias[alias] = find_image_by_stems(images_dir, stems).resolve()

    resources_dir = args.resources_dir.resolve()
    icon_square = _prepare_square_icon_image(files_by_alias["icon"])
    generated_icon_png = resources_dir / "_generated_icon.png"
    save_icon_png(icon_square, generated_icon_png)
    files_by_alias["icon"] = generated_icon_png.resolve()
    generate_icon(icon_square, args.icon_output.resolve())

    qrc_path = write_qrc(resources_dir, files_by_alias)
    output_py = resources_dir / "branding_rc.py"
    compile_qrc_to_python(qrc_path, output_py)

    print(f"Generated icon: {args.icon_output.resolve()}")
    print(f"Generated QRC:  {qrc_path}")
    print(f"Generated RCC:  {output_py}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
