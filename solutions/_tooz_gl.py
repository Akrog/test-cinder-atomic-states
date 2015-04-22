import time

from sqlalchemy import and_
from tooz import coordination

import db


session_cfg = {'autocommit': True, 'expire_on_commit': True}

coordinator = None
lock = None
acquired = False


# Code extracted from https://review.openstack.org/#/c/109837/
def safe_update(session, instance_id, values, expected_values):
    conn = session.connection()
    inst_tab = db.Volume.__table__
    where_conds = [inst_tab.c.id == instance_id]
    for field, value in expected_values.items():
        where_conds.append(inst_tab.c[field] == value)
    upd_stmt = inst_tab.update().where(and_(*where_conds)).values(**values)
    try:
        res = conn.execute(upd_stmt)
    finally:
        conn.close()
    return res.rowcount


@db.retry_on_operational_error
def tooz_make_change(driver, url, session, vol_id, initial, destination,
                     attach_status):
    global coordinator
    global lock
    global acquired

    # If coordinator is not the one we want we cannot reuse it
    if not isinstance(coordinator, driver):
        if coordinator:
            coordinator.stop()

        # Create new coordinator and lock
        coordinator = coordination.get_coordinator(url, str(session))
        coordinator.start()
        lock = coordinator.get_lock(vol_id)

    # When going from available to any other state we acquire the lock
    if initial == 'available':
        # If this is a retry we've already acquired the lock
        if not acquired:
            while not lock.acquire():
                coordinator.heartbeat()
                time.sleep(0.01)
            acquired = True

    n = 0
    while n == 0:
        n = safe_update(session, vol_id,
                        {'status': destination,
                         'attach_status': attach_status},
                        {'status': initial})
    coordinator.heartbeat()
    if destination == 'available':
        lock.release()
        acquired = False
