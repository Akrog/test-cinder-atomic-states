import db
import functools
import time
from sqlalchemy.exc import OperationalError

session_cfg = {'autocommit': True, 'expire_on_commit': True}


def _retry_on_operationalerror(f):
    """Decorator to retry a DB API call if Deadlock was received."""
    @functools.wraps(f)
    def wrapped(session, *args, **kwargs):
        deadlocks = 0
        while True:
            try:
                f(session, *args, **kwargs)
                return deadlocks
            except OperationalError as e:
                if e.args[0].startswith("(OperationalError) (1213, 'Deadlock found"):
                    deadlocks += 1
                else:
                    print 'Operational exception', session, e
                # this includes Lost connection to MySQL server and  Lock wait timeout
                # Retry!
                time.sleep(0.01)
                continue
    functools.update_wrapper(wrapped, f)
    return wrapped

@_retry_on_operationalerror
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
