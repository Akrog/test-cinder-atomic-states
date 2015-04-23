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

import db
import time
from tooz import coordination


session_cfg = {'autocommit': True, 'expire_on_commit': True}

coordinator = None
lock = None


@db.retry_on_operational_error
def tooz_make_change(driver, url, session, vol_id, initial, destination,
                     attach_status):
    global coordinator
    global lock

    # If coordinator is not the one we want we cannot reuse it
    if not isinstance(coordinator, driver):
        if coordinator:
            coordinator.stop()

        # Create new coordinator and lock
        coordinator = coordination.get_coordinator(url, str(session))
        coordinator.start()
        lock = coordinator.get_lock(vol_id)

    while True:
        with lock, session.begin():
            vol = session.query(db.Volume).with_for_update().get(vol_id)
            if vol.status == initial:
                vol.status = destination
                vol.attach_status = attach_status
                return
        coordinator.heartbeat()
        time.sleep(0.01)
