from solutions import _tooz as tz
from tooz.drivers.file import FileDriver

session_cfg = tz.session_cfg


def make_change(session, *args, **kwargs):
    url = 'redis://192.168.1.14'
    return tz.tooz_make_change(FileDriver, url, session, *args, **kwargs)
