import db
import time

session_cfg = {'autocommit': True, 'expire_on_commit': True}


@db.retry_on_operational_error
def make_change(session, vol_id, initial, destination, attach_status):
    while True:
        with session.begin():
            vol = session.query(db.Volume).with_for_update().get(vol_id)
            if vol.status == initial:
                vol.status = destination
                vol.attach_status = attach_status
                return
        time.sleep(0.01)
