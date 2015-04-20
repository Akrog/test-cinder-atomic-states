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

    if not isinstance(coordinator, driver):
        if coordinator:
            coordinator.stop()
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
