import abc
import io
import itertools
import mimetypes
import os
import shelve
import shutil

from frozendict import frozendict


class AssetStorage(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def add(self, asset, tags=None):
        raise NotImplementedError()

    @abc.abstractmethod
    def remove(self, asset):
        raise NotImplementedError()

    @abc.abstractmethod
    def __contains__(self, asset_id):
        raise NotImplementedError()

    @abc.abstractmethod
    def __iter__(self):
        raise NotImplementedError()

    @abc.abstractmethod
    def filter_by_tags(self, *tags):
        """
        Returns all assets in this storage that have at least the specified tags.

        :param tags: Mandatory tags of an asset to be included in result
        :return: Assets whose tags are a superset of the specified tags
        """
        raise NotImplementedError()


class InMemoryStorage(AssetStorage):
    def __init__(self):
        self.tags_by_asset = {}

    def add(self, asset, tags=None):
        if not tags:
            tags = set()
        self.tags_by_asset[asset] = tags

    def remove(self, asset):
        if asset not in self.tags_by_asset:
            raise ValueError('Unable to delete asset that is not contained in storage.')
        del self.tags_by_asset[asset]


    def __contains__(self, asset):
        return asset in self.tags_by_asset

    def get(self, **kwargs):
        matches = []
        for asset in self.tags_by_asset.keys():
            for key, value in kwargs.items():
                if asset.metadata.get(key, None) == value:
                    matches.append(asset)
        return matches

    def __iter__(self):
        return iter(list(self.tags_by_asset.keys()))

    def filter_by_tags(self, *tags):
        search_tags = set(tags)
        assets_by_tags = [asset for asset, tags in self.tags_by_asset.items() if search_tags.issubset(tags)]
        return iter(assets_by_tags)


class FileStorage(AssetStorage):
    """
    Represents a persistent storage backend for assets.

    FileStorage uses a directory on the file system to serialize Assets.
    """
    def __init__(self, path):
        """
        Initializes a new FileStorage with the specified path.

        :param path: File system path where the data should go
        """
        if os.path.isfile(path):
            raise FileExistsError('The storage path "%s" is a file not a directory.' % path)
        if not os.path.isdir(path):
            os.mkdir(path)
        self.path = path

        self._shelf_path = os.path.join(self.path, 'shelf')
        with shelve.open(self._shelf_path) as assets:
            max_stored_asset_id = max(map(int, assets.keys())) if assets.keys() else 0
            self._asset_id_sequence = itertools.count(start=max_stored_asset_id + 1)

    def __contains__(self, asset):
        with shelve.open(self._shelf_path) as assets:
            return asset in (stored_asset for stored_asset, tags in assets.values())

    def add(self, asset, tags=None):
        if not tags:
            tags = set()
        with shelve.open(self._shelf_path) as assets:
            for asset_id, asset_with_tags in assets.items():
                if asset == asset_with_tags[0]:
                    assets[asset_id] = (asset, tags)
                    return
            asset_id = next(self._asset_id_sequence)
            assets[str(asset_id)] = (asset, tags)

    def remove(self, asset):
        with shelve.open(self._shelf_path) as assets:
            for asset_id, (stored_asset, _) in assets.items():
                if stored_asset == asset:
                    del assets[asset_id]
                    return
        raise ValueError('Unable to remove unknown asset %s', asset)

    def __iter__(self):
        with shelve.open(self._shelf_path) as assets:
            return iter([asset for asset, tags in assets.values()])

    def filter_by_tags(self, *search_tags):
        with shelve.open(self._shelf_path) as assets:
            return iter([asset for asset, tags in assets.values() if set(search_tags) <= tags])


def _freeze_dict(dictionary):
    """
    Creates a read-only dictionary from the specified dictionary.

    If the dictionary contains a value which is a dictionary, this dict
    is recursively transformed into a read-only dict.

    :param dictionary: Dict to be transformed into a read-only dict
    :return: Read-only dictionary
    """
    entries = {}
    for key, value in dictionary.items():
        if isinstance(value, dict):
            value = _freeze_dict(value)
        if isinstance(value, set):
            value = frozenset(value)
        entries[key] = value
    return frozendict(entries)


class Asset:
    """
    Represents a digital asset.

    Assets should not be instantiated directly. Instead, use :func:`~madam.core.read` to retrieve an Asset
    representing your content.

    :param essence: The essence of the asset as a file-like object
    :param metadata: The metadata describing the essence
    """
    def __init__(self, essence, **metadata):
        self.essence_data = essence.read()
        if 'mime_type' not in metadata:
            metadata['mime_type'] = None
        self.metadata = _freeze_dict(metadata)

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return other.__dict__ == self.__dict__
        return False

    def __getattr__(self, item):
        if item in self.metadata:
            return self.metadata[item]
        raise AttributeError('%r object has no attribute %r' % (self.__class__, item))

    def __setattr__(self, key, value):
        if 'metadata' in self.__dict__ and key in self.__dict__['metadata']:
            raise NotImplementedError('Unable to overwrite metadata attribute.')
        super().__setattr__(key, value)

    def __setstate__(self, state):
        """
        Sets this objects __dict__ to the specified state.

        Required for Asset to be unpicklable. If this is absent, pickle will not
        set the __dict__ correctly due to the presence of :func:`~madam.core.Asset.__getattr__`.
        :param state: The state passed by pickle
        """
        self.__dict__ = state

    @property
    def essence(self):
        """
        Represents the actual content of the asset.

        The essence of an MP3 file, for example, is only comprised of the actual audio data,
        whereas metadata such as ID3 tags are stored separately as metadata.
        """
        return io.BytesIO(self.essence_data)

    def __hash__(self):
        return hash(self.essence_data) ^ hash(self.metadata)


class UnsupportedFormatError(ValueError):
    """
    Represents an error that is raised whenever file content with unknown type is encountered.
    """
    pass

mimetypes.init()
processors = []
metadata_processors_by_format = {}


def read(file, mime_type=None):
    """
    Reads the specified file and returns its contents as an Asset object.

    :param file: file-like object to be parsed
    :param mime_type: MIME type of the specified file
    :type mime_type: str
    :returns: Asset representing the specified file
    :raises UnsupportedFormatError: if the file format cannot be recognized or is not supported

    :Example:

    >>> import madam
    >>> with open('path/to/file.jpg', 'rb') as file:
    ...     madam.read(file)
    """
    processors_supporting_type = (processor for processor in processors if processor.can_read(file))
    processor = next(processors_supporting_type, None)
    if not processor:
        raise UnsupportedFormatError()
    asset = processor.read(file)
    for metadata_format, metadata_processor in metadata_processors_by_format.items():
        file.seek(0)
        try:
            metadata = dict(asset.metadata)
            metadata[metadata_format] = metadata_processor.read(file)
            stripped_essence = metadata_processor.strip(asset.essence)
            clean_asset = Asset(stripped_essence, metadata=_freeze_dict(metadata))
            asset = clean_asset
        except UnsupportedFormatError:
            pass
    return asset


def write(asset, file):
    r"""
    Write the Asset object to the specified file.

    :param asset: Asset that contains the data to be written
    :param file: file-like object to be written

    :Example:

    >>> import io
    >>> import os
    >>> import madam
    >>> from madam.core import Asset
    >>> gif_asset = Asset(essence=io.BytesIO(b'GIF89a\x01\x00\x01\x00\x00\x00\x00;'), mime_type='image/gif')
    >>> with open(os.devnull, 'wb') as file:
    ...     madam.write(gif_asset, file)
    >>> wav_asset = Asset(
    ...     essence=io.BytesIO(b'RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac'
    ...             b'\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00'),
    ...     mime_type='video/mp4')
    >>> with open(os.devnull, 'wb') as file:
    ...     madam.write(wav_asset, file)
    """
    essence_with_metadata = asset.essence
    for metadata_format, processor in metadata_processors_by_format.items():
        metadata = getattr(asset, metadata_format, None)
        if metadata is not None:
            essence_with_metadata = processor.combine(essence_with_metadata, metadata)
    shutil.copyfileobj(essence_with_metadata, file)


class Pipeline:
    def __init__(self):
        self.operators = []

    def process(self, *assets):
        for asset in assets:
            processed_asset = asset
            for operator in self.operators:
                processed_asset = operator(processed_asset)
            yield processed_asset

    def add(self, operator):
        self.operators.append(operator)


class Processor(metaclass=abc.ABCMeta):
    def __init__(self):
        processors.append(self)

    @abc.abstractmethod
    def can_read(self, mime_type):
        raise NotImplementedError()

    @abc.abstractmethod
    def read(self, file):
        raise NotImplementedError()


class MetadataProcessor(metaclass=abc.ABCMeta):
    def __init__(self):
        metadata_processors_by_format[self.format] = self

    @property
    @abc.abstractmethod
    def format(self):
        raise NotImplementedError()

    @abc.abstractmethod
    def read(self, file):
        """
        Reads the file and returns the metadata.

        The type of metadata that is returned is specified by :attr:`~madam.core.MetadataProcessor.format`.

        :param file: File-like object to be read
        :return: Metadata contained in the file
        :raises UnsupportedFormatError: if the data is corrupt or its format is not supported
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def strip(self, file):
        raise NotImplementedError()

    @abc.abstractmethod
    def combine(self, file, metadata):
        """
        Returns a byte stream whose contents represent the specified file where the specified metadata was added.

        :param metadata: Metadata information to be added
        :param file: Container file
        :return: File-like object with combined content
        """
        raise NotImplementedError()
