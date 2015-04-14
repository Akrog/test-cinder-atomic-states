import db
import functools
import time
from sqlalchemy.exc import OperationalError

session_cfg = {'autocommit': True, 'expire_on_commit': True}


def _retry_on_deadlock(f):
    """Decorator to retry a DB API call if Deadlock was received."""
    @functools.wraps(f)
    def wrapped(session, *args, **kwargs):
        deadlocks = 0
        while True:
            try:
                f(session, *args, **kwargs)
                return deadlocks
            except OperationalError as e:
                if not e.args[0].startswith("(OperationalError) (1213, 'Deadlock found"):
                    raise
                deadlocks += 1
                # Retry!
                time.sleep(0.01)
                continue
    functools.update_wrapper(wrapped, f)
    return wrapped

@_retry_on_deadlock
def make_change(session, vol_id, initial, destination, attach_status):
    while True:
        with session.begin():
            vol = session.query(db.Volume).with_for_update().get(vol_id)
            if vol.status == initial:
                vol.status = destination
                vol.attach_status = attach_status
                #session.commit()
                return
            time.sleep(0.01)
