import base64
import io
import struct
import zlib

import pytest
from PIL import Image

from shared_runtime.image_input import ImageInputError, normalize_images


def image_uri(fmt="PNG", size=(32, 24), **kwargs):
    output = io.BytesIO()
    Image.new("RGB", size, "red").save(output, format=fmt, **kwargs)
    mime = {"PNG": "png", "JPEG": "jpeg", "WEBP": "webp"}[fmt]
    return "data:image/" + mime + ";base64," + base64.b64encode(output.getvalue()).decode()


@pytest.mark.parametrize(
    "uri",
    [
        "https://127.0.0.1/private",
        "file:///private",
        "data:image/svg+xml;base64,PHN2Zz4=",
        "data:image/png;base64,!@#$",
        "data:image/png;base64,dGV4dA==",
    ],
)
def test_rejects_urls_unsupported_types_and_invalid_pixels(uri):
    with pytest.raises(ImageInputError):
        normalize_images([uri])


def test_count_mime_and_size_limits():
    with pytest.raises(ImageInputError, match="3"):
        normalize_images([image_uri()] * 4)
    with pytest.raises(ImageInputError, match="不符"):
        normalize_images([image_uri().replace("image/png", "image/jpeg")])
    with pytest.raises(ImageInputError, match="5 MiB"):
        normalize_images(["data:image/png;base64," + "A" * (7 * 1024 * 1024)])
    with pytest.raises(ImageInputError, match="10 MiB"):
        normalize_images(["data:image/png;base64," + "A" * (5 * 1024 * 1024)] * 3)


def test_checks_dimensions_before_decompressing_pixels():
    # Valid PNG header with an excessive area, no large allocation or pixel stream.
    ihdr = struct.pack(">IIBBBBB", 5000, 4000, 8, 2, 0, 0, 0)
    block = b"IHDR" + ihdr
    png = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", len(ihdr)) + block + struct.pack(">I", zlib.crc32(block))
    png += b"\x00\x00\x00\x00IDAT\x35\xaf\x06\x1e"
    uri = "data:image/png;base64," + base64.b64encode(png).decode()
    with pytest.raises(ImageInputError, match="分辨率"):
        normalize_images([uri])


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_normalizes_formats_and_bounds_dimensions(fmt):
    normalized = normalize_images([image_uri(fmt, (2000, 1000))])[0]
    with Image.open(io.BytesIO(base64.b64decode(normalized.split(",")[1]))) as image:
        assert image.format == "JPEG" and image.size == (1536, 768)
        assert not image.getexif()


def test_applies_orientation_and_strips_exif():
    exif = Image.Exif()
    exif[274], exif[270] = 6, "private metadata"
    normalized = normalize_images([image_uri("JPEG", (30, 20), exif=exif)])[0]
    with Image.open(io.BytesIO(base64.b64decode(normalized.split(",")[1]))) as image:
        assert image.size == (20, 30)
        assert not image.getexif()
