#!/bin/env python

import cProfile
import itertools as it
import logging
import time

from sqlalchemy.exc import OperationalError

import db
import test_results
from tester import Tester

NUM_ROWS = 2  # How many different rows are available
WORKERS_PER_ROW = 3  # How many workes will be fighting for each row
NUM_TESTS_PER_WORKER = 10  # How many deleting-available changes to make
DELETE_TIME = 0.01  # Simulated delete time

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


def do_test(worker_id, num_tests, db_data, changer, session_cfg={},
            vol_id=None, delete_time=0.01, *args, **kwargs):
    """Perform tests for atomic changes of rows in the database.

    Will perform num_tests changes from available to deleting and back to
    available, always checking that changes are consistent across all nodes of
    the database.
    """
    db_cfg = db_data.copy()
    database = db.Db(session_cfg=session_cfg, **db_cfg)

    session = database.session

    results = []
    vol_id = vol_id or database.current_uuids[0]

    profile = cProfile.Profile()
    for i in xrange(num_tests):
        result = test_results.ResultDataPoint(worker=worker_id, num_test=i)
        try:
            marker = '%s_%s' % (worker_id, i)
            LOG.info('Start %s', marker)
            time.sleep(0.005)
            profile.enable()
            time_start = time.time()
            r = changer(session, vol_id, 'available', 'deleting', marker)
            # Update result values for deadlocks, timeouts, etc.
            for k, v in r.iteritems():
                setattr(result, k, v)
            time_end = time.time()
            profile.disable()
            result.acquire = time_end - time_start
            LOG.info('Checking deleting %s', marker)
            try:
                ex = None
                check_volume(db_cfg, vol_id,
                             {'status': 'deleting', 'attach_status': marker})
            except db.WrongDataException:
                raise
            except Exception as e:
                ex = e
                LOG.error('On check volume %s: %s', marker, ex)
            LOG.info('Check OK for %s', marker)

            time.sleep(delete_time)

            # We cannot let it on deleting or it will prevent other workers
            # from doing anything
            result.release = 0.0
            while True:
                try:
                    LOG.info('Changing %s to available', marker)
                    profile.enable()
                    time_start = time.time()
                    r = changer(session, vol_id, 'deleting', 'available',
                                marker)
                    time_end = time.time()
                    profile.disable()
                    result.release += time_end - time_start

                    # Update result values for deadlocks, timeouts, etc.
                    for k, v in r.iteritems():
                        setattr(result, k, getattr(result, k) + v)
                    LOG.info('Changed %s to available', marker)
                except OperationalError as e:
                    LOG.warning('ERROR changing %s to available: %s',
                                marker, e)
                    session.rollback()
                except Exception as e:
                    LOG.warning('Unexpected changing %s: %s', marker, e)
                    session.rollback()
                else:
                    break
        except Exception as e:
            LOG.error('On %s: %s', marker, e)
            # session.rollback()
            result.status = 'Exception %s' % e
        finally:
            result.profile = test_results.map_profile_info(profile)
            results.append(result)
    LOG.info('Worker %s has finished', worker_id)
    return results


def get_solutions():
    """Return loaded solution libraries existing in solutions directory."""
    from importlib import import_module
    import pkgutil

    package = 'solutions'
    solution_names = ['.' + name
                      for _, name, _ in pkgutil.iter_modules([package])
                      if not name.startswith('_')]
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
        print '\t%d workers' % NUM_WORKERS
        print '\t%d rows' % NUM_ROWS
        print '\t%d changes per worker' % NUM_TESTS_PER_WORKER

        tester = Tester(
            do_test,
            it.cycle({'args': (uuid,)} for uuid in uuids),
            NUM_TESTS_PER_WORKER,
            db_data,
            solution.make_change,
            solution.session_cfg,
            delete_time=DELETE_TIME)
        start = time.time()
        result = list(it.chain(*tester.run(NUM_WORKERS)))
        end = time.time()
        test_results.display_results(end - start, result)
        time.sleep(1)
