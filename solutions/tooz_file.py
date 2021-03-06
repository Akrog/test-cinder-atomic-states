# Copyright 2015 Red Hat, Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

import os

from solutions import _tooz as tz
from tooz.drivers.file import FileDriver

session_cfg = tz.session_cfg


def make_change(session, *args, **kwargs):
    url = 'file://' + os.getcwd() + '/shared'
    return tz.tooz_make_change(FileDriver, url, session, *args, **kwargs)
