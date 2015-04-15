import db
import functools
import time
from sqlalchemy.exc import OperationalError
from tooz import coordination
import os


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

coordinator = None
lock = None

@_retry_on_deadlock
def make_change(session, vol_id, initial, destination, attach_status):
    global coordinator
    global lock
    if coordinator is None:
        coordinator = coordination.get_coordinator('file://' + os.getcwd(), str(session))
        #coordinator = coordination.get_coordinator('redis://192.168.1.14', str(session))
        #coordinator = coordination.get_coordinator('ipc://' + os.getcwd(), str(session))
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
