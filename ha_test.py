#!/bin/env python

from pprint import pprint
import pdb

import itertools as it
import logging
import time

from sqlalchemy.exc import OperationalError

import db
import results
from tester import Tester

NUM_ROWS = 5
WORKERS_PER_ROW = 2
NUM_TESTS_PER_WORKER = 10

NUM_WORKERS = NUM_ROWS*WORKERS_PER_ROW

HAPROXY_IP = '192.168.1.14'
DB_NODES = ('192.168.1.15', '192.168.1.16', '192.168.1.17')
DB_USER = 'wsrep_sst'
DB_PASS = 'wspass'

LOG = logging
LOG.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S')

        
def check_volume(db_cfg, vol_id, data):
    """Check that a volumes has the same data in all cluster nodes."""
    def _check_volume(dbs):
        for node in dbs:
            LOG.debug('Checking node %s for %s', node, data)
            node.check_volume(vol_id, data)

    def _close_dbs(dbs):
        for node in dbs:
            node.close()

    def _create_dbs(db_cfg):
        db_cfg = db_cfg.copy()
        del db_cfg['ip']
        return (db.Db(ip=ip, **db_cfg) for ip in db_cfg.get('nodes_ips', []))

    dbs = _create_dbs(db_cfg)

    num_tries = 6
    i = 0
    while True:
        try:
            _check_volume(dbs)
            _close_dbs(dbs)
            return
        except Exception as e:
            if i < num_tries - 1:
                if isinstance(e, db.WrongDataException):
                    LOG.debug('Check retry, possible propagation delay with '
                              'changes %s', data)
                    i += 1
                else:
                    LOG.debug('Check exception, retry doesn\'t count: %s', e)
                time.sleep(0.25 * (i+1))
            else:
                LOG.error('Checking %s', data)
                _close_dbs(dbs)
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


def do_test(worker_id, db_data, changer, session_cfg={}, vol_id=None,
            *args, **kwargs):
    db_cfg = db_data.copy()
    database = db.Db(session_cfg=session_cfg, **db_cfg)
    
    session = database.session
       
    results = []
    vol_id = vol_id or database.current_uuids[0]
    with db.profiled(enabled=False) as profile:
        for i in xrange(NUM_TESTS_PER_WORKER):
            try:
                marker = '%s_%s' % (worker_id, i)
                LOG.info('Start %s', marker)
                time.sleep(0.005)
                profile.enable()
                time_start = time.time()
                deadlocks = changer(session, vol_id, 'available', 'deleting', marker)
                time_end = time.time()
                profile.disable()
                change_1_time = time_end - time_start
                LOG.info('Checking deleting %s', marker)
                t = time.time()
                try:
                    ex = None
                    check_volume(db_cfg, vol_id, {'status': 'deleting', 'attach_status': marker})
                except db.WrongDataException:
                    raise
                except Exception as e:
                    ex = e
                    LOG.error('On check volume %s: %s', marker, e)
                s = time.time()
                LOG.info('Check OK for %s', marker)

                change_2_time = 0.0
                while True:
                    try:
                        LOG.info('Changing %s to available', marker)
                        profile.enable()
                        time_start = time.time()
                        deadlocks += changer(session, vol_id, 'deleting', 'available', marker)
                        time_end = time.time()
                        profile.disable()
                        change_2_time += time_end - time_start
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
                results.append(('OK %s' % i, change_1_time, change_2_time, deadlocks))
            except Exception as e:
                LOG.error('On %s: %s', marker, e)
                #session.rollback()
                results.append(("Exception on %s: %s" % (i, e), None, None, 0))
    LOG.info('Worker %s has finished', worker_id)
    return {'id': worker_id, 'result': results, 'profile': prepare_profile_info(profile)}


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
    uuids = db.populate_database(db_data, NUM_ROWS)

    for solution in solutions:
        print '\nRunning', solution.__name__
        tester = Tester(do_test, it.cycle(tuple({'args': (uuids[i],)} for i in xrange(NUM_ROWS))), db_data, solution.make_change, solution.session_cfg)
        start = time.time()
        result = list(tester.run(NUM_WORKERS))
        end = time.time()
        results.display_results(end - start, result)
        time.sleep(1)

