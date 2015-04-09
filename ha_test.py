#!/bin/env python


from pprint import pprint

import db
from tester import Tester
from solutions import deadlock
import time
from sqlalchemy.exc import OperationalError

DEBUG = False
NUM_WORKERS = 5 
NUM_TESTS_PER_WORKER = 100

def my_func():
    
    return {'args': args, 'kwargs': kwargs}

def check_volume(nodes, vol_id, data):
    def _check_volume():
        for node in nodes:
            if DEBUG: print '+',
            vol = node[1].query(db.Volume).get(vol_id)
            for k, v in data.iteritems():
                if DEBUG: print '.',
                d = getattr(vol, k)
                if d != v:
                    if DEBUG: print '-',
                    node[1].expire(vol)
                    raise Exception('Wrong data in server %s in %s, key %s %s != %s' % (node[2], vol_id, k, v, d))

    num_tries = 3
    for i in xrange(num_tries):
        try:
            _check_volume()
            return
        except:
            if i < num_tries:
                time.sleep(0.1)
            else:
                raise

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
    for i in xrange(NUM_TESTS_PER_WORKER):
        try:
            marker = '%s_%s' % (worker_id, i)
            time_start = time.time()
            changer(session, vol_id, 'available', 'deleting', marker)
            time_end = time.time()
            change_1_time = time_end - time_start
            #time.sleep(0.1)
            if DEBUG: print 'Checking deleting', marker,
            check_volume(nodes, vol_id, {'status': 'deleting', 'attach_status': marker})
            if DEBUG: print '... OK'

            time_start = time.time()
            while True:
                try:
                    changer(session, vol_id, 'deleting', 'available', marker)
                except OperationalError as e:
                    if DEBUG: print 'ERROR: ', e
                    session.rollback()
                else:
                    #time.sleep(0.05)
                    break
                # We cannot let it on deleting or it will prevent other workers from doing anything
            time_end = time.time()
            change_2_time = time_end - time_start
            results.append(('Ok %s' % i, change_1_time, change_2_time))
        except Exception as e:
            if DEBUG: print '... ERROR'
            session.rollback()
            results.append(("Exception on %s: %s" % (i, e), None, None))
    return {'id': worker_id, 'result': results}


def populate_database(user, passwd, ip):
    database = db.Db(user=user, pwd=passwd, ip=ip)
    database.create_table()
    database.populate()
    uuids = database.current_uuids[0]
    database.close()
    return (uuids)



if __name__ == '__main__':
    db_data = {'user': 'wsrep_sst', 'pwd': 'wspass', 'ip': '192.168.1.14'}
    uuids = populate_database(db_data['user'], db_data['pwd'], db_data['ip'])
    #database = db.Db(**db_data)
    #database.create_table()
    #database.populate()
    #database.close()

    db_data['node_ips'] = ['192.168.1.15', '192.168.1.16', '192.168.1.17']

    t = Tester(do_test, None, db_data, deadlock.make_change, deadlock.session_cfg, uuids[0])
    #t = Tester(do_test, None, database.get_engine(), deadlock.make_change, database.current_uuids[0])
    r = t.run(NUM_WORKERS)
    res = list(r)
    pprint(res)

    i = 0
    errors = 0
    result = 0.0
    for x in res:
        for d in x['result']:
            if d[0].startswith('Ok'):
                i += 1 
                result += d[1]
            else:
                errors += 1

    if i:
        print 'Average time for each change is', (result / i)
        print 'Errors:', errors
