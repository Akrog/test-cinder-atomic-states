import db
import functools
import time
from sqlalchemy.exc import OperationalError

session_cfg = {'autocommit': False, 'expire_on_commit': True}


def _retry_on_deadlock(f):
    """Decorator to retry a DB API call if Deadlock was received."""
    @functools.wraps(f)
    def wrapped(session, *args, **kwargs):
        while True:
            try:
                return f(session, *args, **kwargs)
            except OperationalError as e:
                if not e.args[0].startswith("(OperationalError) (1213, 'Deadlock found"):
                    raise
                session.rollback()
                # Retry!
                #time.sleep(0.1)
                continue
    functools.update_wrapper(wrapped, f)
    return wrapped

@_retry_on_deadlock
def make_change(session, vol_id, initial, destination, attach_status):
    i = 0
    while True:
        vol = session.query(db.Volume).with_for_update().get(vol_id)
        if vol.status == initial:
            break
        session.rollback()
        #time.sleep(0.1)
        #i += 1
        #if i == 100:
        #    print 'Fuck'
        #    raise Exception ('Fuck')

        del vol
    vol.status = destination
    vol.attach_status = attach_status
    session.commit()
