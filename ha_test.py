#!/bin/env python


from pprint import pprint

import db
from tester import Tester
from solutions import deadlock

def my_func():
    
    return {'args': args, 'kwargs': kwargs}

def check_volume(nodes, vol_id, data):
    for node in nodes:
        vol = node[1].query(db.Volume).get(vol_id)
        for k, v in data.iteritems():
            d = getattr(vol, k)
            if d != v:
                raise Exception('Wrong data in server %s in %s, key %s %s != %s' % (node[2], vol_id, k, v, d))

def do_test(worker_id, db_data, changer, session_cfg={}, *args, **kwargs):
    node_ips = db_data.pop('node_ips', [])

    db_cfg = db_data.copy()
    nodes = []
    for node_ip in node_ips:
        db_cfg['ip'] = node_ip
        database = db.Db(**db_data)
        session = database.session
        nodes.append((database, session, node_ip))

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
            check_volume(nodes, vol_id, {'status': 'deleting', 'attach_status': marker})
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

    db_data['node_ips'] = ['192.168.1.15', '192.168.1.16', '192.168.1.17']

    t = Tester(do_test, None, db_data, deadlock.make_change, deadlock.session_cfg, database.current_uuids[0])
    #t = Tester(do_test, None, database.get_engine(), deadlock.make_change, database.current_uuids[0])
    r = t.run(5)
    pprint(list(r))
