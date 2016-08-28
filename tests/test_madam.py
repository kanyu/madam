import io

import piexif
import pytest

from madam import Madam
from madam.core import Asset, UnsupportedFormatError
from assets import jpeg_asset, png_asset, image_asset, y4m_asset, asset


@pytest.fixture(name='madam')
def madam_instance():
    return Madam()


def test_jpeg_asset_essence_does_not_contain_exif_metadata(madam):
    exif = jpeg_asset().metadata['exif']
    data_with_exif = io.BytesIO()
    piexif.insert(piexif.dump(exif), jpeg_asset().essence.read(), new_file=data_with_exif)
    asset = madam.read(data_with_exif)
    essence_bytes = asset.essence.read()

    essence_exif = piexif.load(essence_bytes)

    for ifd, ifd_data in essence_exif.items():
        assert not ifd_data


def test_read_empty_file_raises_error(madam):
    file_data = io.BytesIO()

    with pytest.raises(UnsupportedFormatError):
        madam.read(file_data)


def test_read_raises_when_file_is_none(madam):
    invalid_file = None

    with pytest.raises(TypeError):
        madam.read(invalid_file)


def test_read_raises_error_when_format_is_unknown(madam):
    random_data = b'\x07]>e\x10\n+Y\x07\xd8\xf4\x90%\r\xbbK\xb8+\xf3v%\x0f\x11'
    unknown_file = io.BytesIO(random_data)

    with pytest.raises(UnsupportedFormatError):
        madam.read(unknown_file)


def test_read_returns_asset_when_reading_valid_data(madam, asset):
    valid_data = asset.essence

    asset = madam.read(valid_data)

    assert asset is not None


def test_writes_correct_essence_without_metadata(madam, image_asset):
    asset = Asset(essence=image_asset.essence)
    file = io.BytesIO()

    madam.write(asset, file)

    file.seek(0)
    assert file.read() == asset.essence.read()


def test_writes_correct_essence_with_metadata(madam, jpeg_asset):
    file = io.BytesIO()

    madam.write(jpeg_asset, file)

    file.seek(0)
    assert file.read() != jpeg_asset.essence.read()


def test_config_contains_list_of_all_processors_by_default(madam):
    assert madam.config['processors'] == [
        'madam.audio.MutagenProcessor', 'madam.audio.WaveProcessor',
        'madam.image.PillowProcessor',
        'madam.video.FFmpegProcessor']
