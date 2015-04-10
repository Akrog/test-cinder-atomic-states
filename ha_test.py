#!/bin/env python
import pdb


from pprint import pprint
from collections import defaultdict
import db
from tester import Tester
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
                    if DEBUG: print '-', d, '!=', v,
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

def prepare_profile_info(profile):
    result = map(
        lambda p: {
            'callcount': p.callcount, 
            'time': p.totaltime, 
            'name': p.code if isinstance(p.code, str) else p.code.co_name, 
            'file': None if isinstance(p.code, str) else p.code.co_filename},
        profile.getstats())
    return result

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
    with db.profiled() as profile:
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
                if DEBUG: print '... ERROR', str(e)
                session.rollback()
                results.append(("Exception on %s: %s" % (i, e), None, None))
    return {'id': worker_id, 'result': results, 'profile': prepare_profile_info(profile)}


def populate_database(user, passwd, ip):
    database = db.Db(user=user, pwd=passwd, ip=ip)
    database.create_table()
    database.populate()
    uuids = database.current_uuids[0]
    database.close()
    return (uuids)

def display_results(results):
    pattern = "<method '"
    i = 0
    errors = 0
    total_time = 0.0
    for x in results:
        for d in x['result']:
            if d[0].startswith('Ok'):
                i += 1 
                total_time += d[1]
            else:
                errors += 1
    sql = list(filter(lambda r: 'sql' in r['name'] and r['name'].startswith(pattern), result['profile']) for result in results)
    acc = defaultdict(lambda: {'callcount': 0, 'time': 0.0})    
    for result in sql:
        for call in result:
            acc[call['name']]['callcount'] += call['callcount']
            acc[call['name']]['time'] += call['time']

    if i:
        print 'Errors:', errors
        print 'Average time for each change is %.2fms' % ((total_time / i) * 1000)
        for name, data in acc.iteritems():
            i = len(pattern)
            n = name[i:name.index("'", i)]
            print '\t%s: %d calls, %.2fms' % (n, data['callcount'], data['time'] * 1000) 
        #pprint(dict(acc))

def get_solutions():
    from importlib import import_module
    import pkgutil

    package = 'solutions'
    solution_names = ['.' + name for _, name, _ in pkgutil.iter_modules([package])]
    return map(lambda name: import_module(name, package), solution_names)


if __name__ == '__main__':
    solutions = get_solutions()
    db_data = {'user': 'wsrep_sst', 'pwd': 'wspass', 'ip': '192.168.1.14'}
    uuids = populate_database(db_data['user'], db_data['pwd'], db_data['ip'])
    db_data['node_ips'] = ['192.168.1.15', '192.168.1.16', '192.168.1.17']

    for solution in solutions:
        print '\nRunning', solution.__name__
        #with db.profiled() as pr:
        tester = Tester(do_test, None, db_data, solution.make_change, solution.session_cfg, uuids[0])
        start = time.time()
        result = list(tester.run(NUM_WORKERS))
        end = time.time()
        #pdb.set_trace()
        if DEBUG: pprint(result)
        print 'Time %.2f secs' % (end - start)
        display_results(result)

