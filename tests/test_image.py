import pytest

import adam.image
import io
import PIL.Image
import piexif


def test_supports_jfif():
    assert 'image/jpeg' in adam.supported_mime_types


@pytest.fixture
def jpeg_rgb_image():
    empty_image = PIL.Image.new('RGB', (1, 1))
    image_data = io.BytesIO()
    empty_image.save(image_data, 'JPEG')
    image_data.seek(0)

    exif_dict = {'0th': {piexif.ImageIFD.Artist: 'Test artist'}}
    exif_bytes = piexif.dump(exif_dict)
    image_with_exif_metadata = io.BytesIO()
    piexif.insert(exif_bytes, image_data.read(), image_with_exif_metadata)

    return image_with_exif_metadata


def test_read_jpeg_returns_asset_with_jpeg_mime_type(jpeg_rgb_image):
    jpeg_asset = adam.image.read_jpeg(jpeg_rgb_image)

    assert jpeg_asset.mime_type == 'image/jpeg'


def test_jpeg_asset_essence_is_filled(jpeg_rgb_image):
    jpeg_asset = adam.image.read_jpeg(jpeg_rgb_image)

    assert jpeg_asset.essence is not None


def test_jpeg_asset_contains_size_information(jpeg_rgb_image):
    jpeg_asset = adam.image.read_jpeg(jpeg_rgb_image)

    assert jpeg_asset.width == 1
    assert jpeg_asset.height == 1


def test_jpeg_asset_essence_is_a_jpeg(jpeg_rgb_image):
    jpeg_asset = adam.image.read_jpeg(jpeg_rgb_image)

    jpeg_image = PIL.Image.open(jpeg_asset.essence)

    assert jpeg_image.format == 'JPEG'


def test_jpeg_asset_essence_can_be_read_multiple_times(jpeg_rgb_image):
    jpeg_asset = adam.image.read_jpeg(jpeg_rgb_image)

    essence_contents = jpeg_asset.essence.read()
    same_essence_contents = jpeg_asset.essence.read()

    assert essence_contents == same_essence_contents


def test_jpeg_asset_essence_does_not_contain_exif_metadata(jpeg_rgb_image):
    jpeg_asset = adam.image.read_jpeg(jpeg_rgb_image)
    jpeg_asset.essence.seek(0)
    essence_bytes = jpeg_asset.essence.read()

    essence_exif = piexif.load(essence_bytes)

    for ifd, ifd_data in essence_exif.items():
        assert not ifd_data
