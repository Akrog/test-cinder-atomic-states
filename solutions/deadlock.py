import db
import time

session_cfg = {'autocommit': False, 'expire_on_commit': True}

def make_change(session, vol_id, initial, destination, attach_status):
    i = 0
    while True:
        vol = session.query(db.Volume).with_for_update().get(vol_id)
        if vol.status == initial:
            break
        #session.commit()
        session.rollback()
        time.sleep(0.1)
        i += 1
        if i == 10:
            raise Exception ('Fuck')

        del vol
    vol.status = destination
    vol.attach_status = attach_status
    session.commit()
    
    # return "I'm session %s id %s status from %s to %s attach_status %s" % (session, id, initial, destination, attach_status)
