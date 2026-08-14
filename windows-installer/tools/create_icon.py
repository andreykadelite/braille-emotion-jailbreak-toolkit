from pathlib import Path

from PIL import Image, ImageDraw


def create_icon(path: Path) -> None:
    size = 256
    image = Image.new("RGBA", (size, size), (15, 42, 71, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((10, 10, 246, 246), radius=38, outline=(255, 255, 255), width=10)

    dot_positions = (
        (74, 68),
        (74, 120),
        (74, 172),
        (126, 68),
        (126, 120),
        (126, 172),
    )
    for x, y in dot_positions:
        draw.ellipse((x - 16, y - 16, x + 16, y + 16), fill=(255, 255, 255))

    # A simple right-pointing installation arrow remains recognizable at 32 px.
    draw.rounded_rectangle((154, 105, 217, 139), radius=8, fill=(90, 214, 165))
    draw.polygon(((205, 79), (242, 122), (205, 165)), fill=(90, 214, 165))

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


if __name__ == "__main__":
    create_icon(Path(__file__).resolve().parent.parent / "installer.ico")
