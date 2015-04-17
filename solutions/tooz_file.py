import os

from tooz.drivers.file import FileDriver

from solutions import _tooz as tz


session_cfg = tz.session_cfg

def make_change(session, *args, **kwargs):
    url = 'file://' + os.getcwd()
    return tz.tooz_make_change(FileDriver, url, session, *args, **kwargs) 
