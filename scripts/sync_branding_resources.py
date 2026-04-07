from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
from collections import deque
from pathlib import Path

from PIL import Image, ImageChops, ImageOps

ICON_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
DEFAULT_OPTIMIZED_MAX_SIDE = 1280
DEFAULT_JPEG_QUALITY = 90
SYNC_SIGNATURE_VERSION = 1

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
    "destruction": ("destruction",),
    "sad": ("sad",),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync branding assets into Qt resources.")
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
    parser.add_argument(
        "--optimized-max-side",
        type=int,
        default=DEFAULT_OPTIMIZED_MAX_SIDE,
        help="Max long-edge (px) for sidebar images before packaging.",
    )
    parser.add_argument(
        "--jpeg-quality",
        type=int,
        default=DEFAULT_JPEG_QUALITY,
        help="JPEG quality for optimized sidebar images (1-100).",
    )
    parser.add_argument(
        "--rcc-output",
        type=Path,
        default=None,
        help="Optional output path for compiled branding.rcc (defaults to resources-dir/branding.rcc).",
    )
    parser.add_argument(
        "--emit-python",
        action="store_true",
        help="Also emit legacy branding_rc.py module.",
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


def _resize_if_needed(image: Image.Image, *, max_side: int) -> Image.Image:
    if max_side <= 0:
        return image

    width, height = image.size
    longest = max(width, height)
    if longest <= max_side:
        return image

    scale = float(max_side) / float(longest)
    new_size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    return image.resize(new_size, Image.Resampling.LANCZOS)


def _has_real_alpha(image: Image.Image) -> bool:
    if "A" not in image.getbands():
        return False
    alpha = image.getchannel("A")
    lo, _hi = alpha.getextrema()
    return lo < 255


def optimize_display_image(
    source_path: Path,
    optimized_dir: Path,
    alias: str,
    *,
    max_side: int,
    jpeg_quality: int,
) -> Path:
    optimized_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(source_path) as opened:
        image = ImageOps.exif_transpose(opened)
        image = _resize_if_needed(image, max_side=max_side)

        alpha_candidate = image.convert("RGBA")
        has_alpha = _has_real_alpha(alpha_candidate)

        if has_alpha:
            output_path = optimized_dir / f"{alias}.png"
            alpha_candidate.save(output_path, format="PNG", optimize=True, compress_level=9)
        else:
            output_path = optimized_dir / f"{alias}.jpg"
            rgb = image.convert("RGB")
            rgb.save(
                output_path,
                format="JPEG",
                quality=jpeg_quality,
                optimize=True,
                progressive=True,
                subsampling=0,
            )

    # Keep one deterministic file per alias and remove stale siblings.
    for stale in optimized_dir.glob(f"{alias}.*"):
        if stale.resolve() != output_path.resolve() and stale.is_file():
            stale.unlink(missing_ok=True)

    return output_path.resolve()


def build_resource_files(
    source_files_by_alias: dict[str, Path],
    resources_dir: Path,
    *,
    max_side: int,
    jpeg_quality: int,
) -> dict[str, Path]:
    optimized_dir = resources_dir / "_optimized_branding"

    files_by_alias: dict[str, Path] = {}
    for alias, source_path in source_files_by_alias.items():
        if alias == "icon":
            continue
        files_by_alias[alias] = optimize_display_image(
            source_path,
            optimized_dir,
            alias,
            max_side=max_side,
            jpeg_quality=jpeg_quality,
        )
    return files_by_alias


def write_qrc(resources_dir: Path, files_by_alias: dict[str, Path], *, sync_signature: str) -> Path:
    resources_dir.mkdir(parents=True, exist_ok=True)
    qrc_path = resources_dir / "branding.qrc"

    lines = [
        "<RCC>",
        f"  <!-- branding-sync-signature: {sync_signature} -->",
        '  <qresource prefix="/branding">',
    ]
    for alias in sorted(files_by_alias):
        rel_path = os.path.relpath(files_by_alias[alias], resources_dir).replace("\\", "/")
        lines.append(f'    <file alias="{alias}">{rel_path}</file>')
    lines.append("  </qresource>")
    lines.append("</RCC>")

    qrc_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return qrc_path


def _resolve_rcc_executable() -> Path:
    try:
        import PySide6
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("PySide6 is required to compile branding resources.") from exc

    pyside_root = Path(PySide6.__file__).resolve().parent
    rcc_exe = pyside_root / "rcc.exe"
    if not rcc_exe.exists():
        raise FileNotFoundError(f"Unable to locate rcc.exe at {rcc_exe}")
    return rcc_exe


def compile_qrc_to_binary(qrc_path: Path, output_rcc: Path) -> None:
    rcc_exe = _resolve_rcc_executable()
    output_rcc.parent.mkdir(parents=True, exist_ok=True)

    cmd = [str(rcc_exe), "-binary", str(qrc_path), "-o", str(output_rcc)]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(
            "Qt binary resource compilation failed:\n"
            f"Command: {' '.join(cmd)}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )


def compile_qrc_to_python(qrc_path: Path, output_py: Path) -> None:
    rcc_exe = _resolve_rcc_executable()
    output_py.parent.mkdir(parents=True, exist_ok=True)

    cmd = [str(rcc_exe), "-g", "python", str(qrc_path), "-o", str(output_py)]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(
            "Qt python resource compilation failed:\n"
            f"Command: {' '.join(cmd)}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )


def _clamp(value: int, *, low: int, high: int) -> int:
    return max(low, min(high, value))


def _sum_sizes(paths: list[Path]) -> int:
    return sum(path.stat().st_size for path in paths if path.exists() and path.is_file())


def _build_sync_signature(
    source_files_by_alias: dict[str, Path],
    *,
    max_side: int,
    jpeg_quality: int,
) -> str:
    hasher = hashlib.sha256()
    hasher.update(f"v={SYNC_SIGNATURE_VERSION}|max_side={max_side}|jpeg_quality={jpeg_quality}".encode("utf-8"))
    hasher.update(f"|icon_sizes={ICON_SIZES!r}".encode("utf-8"))

    for alias in sorted(source_files_by_alias):
        path = source_files_by_alias[alias]
        stat = path.stat()
        hasher.update(
            f"|{alias}|{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8")
        )
    return hasher.hexdigest()


def _read_qrc_signature(qrc_path: Path) -> str | None:
    if not qrc_path.exists():
        return None

    marker = "branding-sync-signature:"
    try:
        for line in qrc_path.read_text(encoding="utf-8").splitlines():
            if marker not in line:
                continue
            value = line.split(marker, 1)[1]
            value = value.split("-->", 1)[0]
            value = value.strip()
            if value:
                return value
    except Exception:  # noqa: BLE001
        return None

    return None


def _can_skip_regeneration(
    *,
    sync_signature: str,
    qrc_path: Path,
    rcc_output: Path,
    icon_output: Path,
    emit_python: bool,
    output_py: Path | None,
) -> bool:
    if _read_qrc_signature(qrc_path) != sync_signature:
        return False

    required_files = [qrc_path, rcc_output, icon_output]
    if emit_python and output_py is not None:
        required_files.append(output_py)

    for path in required_files:
        if not path.exists() or not path.is_file():
            return False

    qrc_mtime_ns = qrc_path.stat().st_mtime_ns
    if rcc_output.stat().st_mtime_ns < qrc_mtime_ns:
        return False
    if emit_python and output_py is not None and output_py.stat().st_mtime_ns < qrc_mtime_ns:
        return False

    return True


def main() -> int:
    args = build_parser().parse_args()

    images_dir = args.images_dir.resolve()

    # If images directory does not exist, skip branding resource generation
    # and use default/existing resources.
    if not images_dir.exists() or not images_dir.is_dir():
        print(f"Warning: Images directory not found at {images_dir}")
        print("Skipping branding resource sync. Using existing resources if available.")
        return 0

    max_side = max(640, int(args.optimized_max_side))
    jpeg_quality = _clamp(int(args.jpeg_quality), low=70, high=100)

    source_files_by_alias: dict[str, Path] = {}
    for alias, stems in RESOURCE_ALIASES.items():
        source_files_by_alias[alias] = find_image_by_stems(images_dir, stems).resolve()

    resources_dir = args.resources_dir.resolve()
    qrc_path = resources_dir / "branding.qrc"
    rcc_output = args.rcc_output.resolve() if args.rcc_output else (resources_dir / "branding.rcc")
    icon_output = args.icon_output.resolve()
    output_py = resources_dir / "branding_rc.py" if args.emit_python else None
    sync_signature = _build_sync_signature(
        source_files_by_alias,
        max_side=max_side,
        jpeg_quality=jpeg_quality,
    )

    if _can_skip_regeneration(
        sync_signature=sync_signature,
        qrc_path=qrc_path,
        rcc_output=rcc_output,
        icon_output=icon_output,
        emit_python=args.emit_python,
        output_py=output_py,
    ):
        print("Branding assets unchanged. Skipping regeneration.")
        print(f"Reusing icon: {icon_output}")
        print(f"Reusing QRC:  {qrc_path}")
        print(f"Reusing RCC:  {rcc_output}")
        if args.emit_python and output_py is not None:
            print(f"Reusing RCC Python module: {output_py}")
        return 0

    icon_square = _prepare_square_icon_image(source_files_by_alias["icon"])
    generated_icon_png = resources_dir / "_generated_icon.png"
    save_icon_png(icon_square, generated_icon_png)
    generate_icon(icon_square, icon_output)

    files_by_alias = build_resource_files(
        source_files_by_alias,
        resources_dir,
        max_side=max_side,
        jpeg_quality=jpeg_quality,
    )
    files_by_alias["icon"] = generated_icon_png.resolve()

    qrc_path = write_qrc(resources_dir, files_by_alias, sync_signature=sync_signature)
    compile_qrc_to_binary(qrc_path, rcc_output)

    if args.emit_python:
        output_py = resources_dir / "branding_rc.py"
        compile_qrc_to_python(qrc_path, output_py)
        print(f"Generated RCC Python module: {output_py}")

    source_total = _sum_sizes(list(source_files_by_alias.values()))
    packaged_total = _sum_sizes(list(files_by_alias.values()))

    print(f"Generated icon: {icon_output}")
    print(f"Generated QRC:  {qrc_path}")
    print(f"Generated RCC:  {rcc_output}")
    print(
        "Optimized branding payload: "
        f"{packaged_total / (1024 * 1024):.2f} MB "
        f"(source references {source_total / (1024 * 1024):.2f} MB)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
