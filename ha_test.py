#!/bin/env python
import pdb


import itertools as it
from pprint import pprint
from collections import defaultdict
import db
from tester import Tester
import time
from sqlalchemy.exc import OperationalError
import logging

NUM_ROWS = 5
WORKERS_PER_ROW = 2
NUM_TESTS_PER_WORKER = 10

NUM_WORKERS = NUM_ROWS*WORKERS_PER_ROW

HAPROXY_IP = '192.168.1.14'
DB_NODES = ('192.168.1.15', '192.168.1.16', '192.168.1.17')
DB_USER = 'wsrep_sst'
DB_PASS = 'wspass'

LOG = logging
LOG.basicConfig(level=logging.WARNING, format='%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S')

class WrongDataException(Exception):
    pass

#def create_node_connections():
        
def check_volume(db_cfg, vol_id, data):
    def _check_volume(nodes):
        for node in nodes:
            LOG.debug('Checking node %s for %s', node, data)
            with node[1].begin():
                LOG.debug('getting data from %s', node[0])
                vol = node[1].query(db.Volume).get(vol_id)
                LOG.debug('received data from %s', node[0])
                for k, v in data.iteritems():
                    d = getattr(vol, k)
                    if d != v:
                        LOG.debug('Error on key %s: %s != %s', k, v, d)
                        raise WrongDataException('Wrong data in server %s in %s, key %s %s != %s' % (node[2], vol_id, k, v, d))

    def _close_dbs(nodes):
        for node in nodes:
            node[0].close()

    def _create_dbs(db_cfg):
        nodes = []
        db_cfg = db_cfg.copy()
        for node_ip in db_cfg.get('nodes_ips', []):
            db_cfg['ip'] = node_ip
            database = db.Db(session_cfg={'autocommit': True, 'expire_on_commit': True}, **db_cfg)
            session = database.session
            nodes.append((database, session, node_ip))
        return nodes

    nodes = _create_dbs(db_cfg)

    num_tries = 6
    i = 0
    while True:
        try:
            _check_volume(nodes)
            _close_dbs(nodes)
            return
        except Exception as e:
            if i < num_tries - 1:
                if isinstance(e, WrongDataException):
                    LOG.debug('Check retry, possible propagation delay with changes %s', data)
                    i += 1
                else:
                    LOG.debug('Exception on check, this retry doesn\'t count: %s', e)
                time.sleep(0.25 * (i+1))
            else:
                LOG.error('Checking %s', data)
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


def do_test(worker_id, db_data, changer, session_cfg={}, vol_id=None, *args, **kwargs):
    db_cfg = db_data.copy()
    database = db.Db(session_cfg=session_cfg, **db_cfg)
    
    session = database.session
       
    results = []
    vol_id = vol_id or database.current_uuids[0]
    with db.profiled() as profile:
        for i in xrange(NUM_TESTS_PER_WORKER):
            try:
                marker = '%s_%s' % (worker_id, i)
                LOG.info('Start %s', marker)
                time.sleep(0.005)
                time_start = time.time()
                deadlocks = changer(session, vol_id, 'available', 'deleting', marker)
                time_end = time.time()
                change_1_time = time_end - time_start
                LOG.info('Checking deleting %s', marker)
                t = time.time()
                profile.disable()
                try:
                    ex = None
                    check_volume(db_cfg, vol_id, {'status': 'deleting', 'attach_status': marker})
                except WrongDataException:
                    raise
                except Exception as e:
                    ex = e
                    LOG.error('On check volume %s: %s', marker, e)
                profile.enable()
                s = time.time()
                LOG.info('Check OK for %s', marker)

                time_start = time.time()
                while True:
                    try:
                        LOG.info('Changing %s to available', marker)
                        deadlocks += changer(session, vol_id, 'deleting', 'available', marker)
                        LOG.info('Changed %s to available', marker)
                    except OperationalError as e:
                        LOG.warning('ERROR changing to available %s: %s', marker, e)
                        session.rollback()
                    except:
                        LOG.warning('Unexpected changing %s: %s', marker, e)
                        session.rollback()
                    else:
                        break
                    # We cannot let it on deleting or it will prevent other workers from doing anything
                time_end = time.time()
                change_2_time = time_end - time_start
                results.append(('OK %s' % i, change_1_time, change_2_time, deadlocks))
            except Exception as e:
                LOG.error('On %s: %s', marker, e)
                #session.rollback()
                results.append(("Exception on %s: %s" % (i, e), None, None, 0))
    LOG.info('Worker %s has finished', worker_id)
    return {'id': worker_id, 'result': results, 'profile': prepare_profile_info(profile)}


def populate_database(db_data, num_rows):
    database = db.Db(**db_data)
    database.create_table()
    database.populate(num_rows)
    uuids = database.current_uuids
    database.close()
    return (uuids)

def display_results(results):
    pattern = "<method '"
    i = 0
    errors = 0
    deadlocks = 0
    total_time = 0.0
    total_delete_time = 0.0
    for x in results:
        for d in x['result']:
            if d[0].startswith('OK'):
                i += 1 
                total_time += d[1]
                total_delete_time += d[2]
                deadlocks += d[3] 
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
        print 'Deadlocks:', deadlocks
        print 'Average time for each change is %.2fms and deletion is %.2fms' % ((total_time / i) * 1000, (total_delete_time / i) * 1000)
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
    db_data = {
        'user': DB_USER,
        'pwd': DB_PASS,
        'ip': HAPROXY_IP,
        'nodes_ips': DB_NODES}
    uuids = populate_database(db_data, NUM_ROWS)

    for solution in solutions:
        print '\nRunning', solution.__name__
        tester = Tester(do_test, it.cycle(tuple({'args': (uuids[i],)} for i in xrange(NUM_ROWS))), db_data, solution.make_change, solution.session_cfg)
        start = time.time()
        result = list(tester.run(NUM_WORKERS))
        end = time.time()
        print 'Time %.2f secs' % (end - start)
        display_results(result)
        time.sleep(1)

