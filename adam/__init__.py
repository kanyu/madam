from .core import read
from .core import read_method_by_mime_type
from .audio import read_mp3, read_wav

supported_mime_types = read_method_by_mime_type.keys()
