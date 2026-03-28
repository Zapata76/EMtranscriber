from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageOps


ICON_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare EMtranscriber branding assets.")
    parser.add_argument("--icon-source", type=Path, help="Path to source image used to generate emtranscriber.ico")
    parser.add_argument("--sidebar-source", type=Path, help="Path to source image used for left sidebar image")
    parser.add_argument(
        "--assets-dir",
        type=Path,
        default=Path("packaging") / "assets",
        help="Output assets directory (default: packaging/assets)",
    )
    return parser


def load_image(path: Path) -> Image.Image:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Source image not found: {path}")
    image = Image.open(path)
    return ImageOps.exif_transpose(image).convert("RGB")


def save_icon(source_path: Path, assets_dir: Path) -> Path:
    icon_source = load_image(source_path)
    square = ImageOps.fit(icon_source, (1024, 1024), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))

    icon_path = assets_dir / "emtranscriber.ico"
    square.save(icon_path, format="ICO", sizes=ICON_SIZES)

    # Keep an editable square PNG source alongside the generated ICO.
    square_png_path = assets_dir / "emtranscriber_icon_source.png"
    square.save(square_png_path, format="PNG")

    return icon_path


def save_sidebar_image(source_path: Path, assets_dir: Path) -> Path:
    sidebar_source = load_image(source_path)
    sidebar_path = assets_dir / "main_sidebar_image.jpg"
    sidebar_source.save(sidebar_path, format="JPEG", quality=95)
    return sidebar_path


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.icon_source is None and args.sidebar_source is None:
        parser.error("Provide at least one source: --icon-source and/or --sidebar-source")

    assets_dir: Path = args.assets_dir
    assets_dir.mkdir(parents=True, exist_ok=True)

    if args.icon_source is not None:
        icon_path = save_icon(args.icon_source, assets_dir)
        print(f"Generated icon: {icon_path}")

    if args.sidebar_source is not None:
        sidebar_path = save_sidebar_image(args.sidebar_source, assets_dir)
        print(f"Generated sidebar image: {sidebar_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
