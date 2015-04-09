#!/bin/env python


from pprint import pprint

import db
from tester import Tester
from solutions import deadlock

def my_func():
    
    return {'args': args, 'kwargs': kwargs}

def check_volume(session, vol_id, data):
    vol = session.query(db.Volume).get(vol_id)
    for k, v in data.iteritems():
        d = getattr(vol, k)
        if d != v:
            raise Exception('Wrong data in %s, key %s %s != %s' % (vol_id, k, v, d))

def do_test(worker_id, db_data, changer, session_cfg={}, *args, **kwargs):
    db_data['session_cfg'] = session_cfg
    database = db.Db(**db_data)
    session = database.session
    results = []
    vol_id = database.current_uuids[0]
    #return vol_id
    for i in xrange(10):
        try:
            marker = '%s_%s' % (worker_id, i) 
            changer(session, vol_id, 'available', 'deleting', marker)
            check_volume(session, vol_id, {'status': 'deleting', 'attach_status': marker})
            changer(session, vol_id, 'deleting', 'available', marker)
            results.append('Ok %s' % i)
        except Exception as e:
            results.append("Exception on %s: %s" % (i, e))
    return {'id': worker_id, 'result': results}

if __name__ == '__main__':
    db_data = {'user': 'wsrep_sst', 'pwd': 'wspass', 'ip': '192.168.1.14'}
    database = db.Db(**db_data)
    database.create_table()
    database.populate()
    database.close()

    t = Tester(do_test, None, db_data, deadlock.make_change, deadlock.session_cfg, database.current_uuids[0])
    #t = Tester(do_test, None, database.get_engine(), deadlock.make_change, database.current_uuids[0])
    r = t.run(5)
    pprint(list(r))
