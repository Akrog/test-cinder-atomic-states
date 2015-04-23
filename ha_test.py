#!/bin/env python

# Copyright 2015 Red Hat, Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

import cProfile
import gc
import itertools as it
import logging
import os
import time

import db
import test_results
import worker
from workloaders import db_rw as wl_generator

DB_NAME = 'cinder'

NUM_ROWS = 100  # How many different rows are available
WORKERS_PER_ROW = 3  # How many workes will be fighting for each row
NUM_TESTS_PER_WORKER = 10  # How many deleting-available changes to make
DELETE_TIME = 0.01  # Simulated delete time

SYN_DB_UPDATES_PER_GENERATOR = 5
SYN_DB_SELECTS_PER_GENERATOR = 10
SYN_DB_GENERATORS = 50

NUM_WORKERS = NUM_ROWS*WORKERS_PER_ROW

HAPROXY_IP = '192.168.1.14'
DB_NODES = ('192.168.1.15', '192.168.1.16', '192.168.1.17')
DB_USER = 'wsrep_sst'
DB_PASS = 'wspass'

OUTPUT_FILE = os.getcwd() + '/results.csv'

ENABLE_PROFILING = False

LOG = logging
LOG.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S')


def do_change(changer, profile, session, vol_id, initial, destination, marker,
              result):
    """Make a status change, time it, profile it and return time."""
    LOG.info('Changing %s to %s', marker, destination)
    time_start = time.time()
    r = changer(session, vol_id, initial, destination, marker)
    time_end = time.time()
    profile.disable()
    # Update result values for deadlocks, timeouts, etc.
    for k, v in r.iteritems():
        setattr(result, k, getattr(result, k) + v)
    LOG.info('Changed %s to %s', marker, destination)
    return time_end - time_start


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

    if not ENABLE_PROFILING:
        fake = lambda *args, **kwargs: tuple()
        profile = fake
        profile.__dict__ = {'enable': fake, 'disable': fake, 'getstats': fake}
    else:
        profile = cProfile.Profile()

    for i in xrange(num_tests):
        result = test_results.ResultDataPoint(worker=worker_id, num_test=i)
        try:
            marker = '%s_%s' % (worker_id, i)

            LOG.info('Start %s', marker)
            time.sleep(0.01)
            profile.enable()

            # make change to deleting, measure and profile it
            result.acquire = do_change(changer, profile, session, vol_id,
                                       'available', 'deleting', marker, result)

            # check that it's changed in all nodes
            LOG.info('Checking deleting %s', marker)
            try:
                ex = None
                db.check_volume(LOG, db_cfg, vol_id,
                                {'status': 'deleting',
                                 'attach_status': marker})
            except Exception as e:
                ex = e
                LOG.error('On check volume %s: %s', marker, ex)
            else:
                LOG.info('Check OK for %s', marker)
                time.sleep(delete_time)

            # make change to available, measure and profile it
            result.release = do_change(changer, profile, session, vol_id,
                                       'deleting', 'available', marker, result)

            if ex:
                raise ex

        except Exception as e:
            LOG.error('On %s: %s', marker, e)
            result.status = 'Exception %s' % e
        finally:
            result.profile = test_results.map_profile_info(profile)
            results.append(result)

    database.close()
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
    # get all solutions from solutions directory
    solutions = get_solutions()
    summaries = []

    # populate the database with enough different volumes
    db_data = {
        'user': DB_USER,
        'pwd': DB_PASS,
        'ip': HAPROXY_IP,
        'db_name': DB_NAME,
        'nodes_ips': DB_NODES}
    uuids = db.populate_database(db_data, NUM_ROWS)

    for solution in solutions:
        print '\nRunning', solution.__name__
        print '\t%d workers' % NUM_WORKERS
        print '\t%d rows' % NUM_ROWS
        print '\t%d changes per worker' % NUM_TESTS_PER_WORKER
        print ('\t%d synthetic workload generators with %d selects and '
               '%d updates per second' % (SYN_DB_GENERATORS,
                                          SYN_DB_SELECTS_PER_GENERATOR,
                                          SYN_DB_UPDATES_PER_GENERATOR))

        testers = worker.Tester(
            do_test,
            it.cycle({'args': (uuid,)} for uuid in uuids),
            NUM_TESTS_PER_WORKER,
            db_data,
            solution.make_change,
            solution.session_cfg,
            delete_time=DELETE_TIME)

        workloads = worker.Workloader(
            wl_generator.do_workload,
            None,
            db_data,
            num_selects=SYN_DB_SELECTS_PER_GENERATOR,
            num_updates=SYN_DB_UPDATES_PER_GENERATOR)

        # start workload generators
        workloads.run(SYN_DB_GENERATORS)

        # test solution
        start = time.time()
        result = tuple(it.chain(*testers.run(NUM_WORKERS)))
        end = time.time()

        # stop workload generators
        workloads.finish()

        summary = test_results.summarize(solution, end - start, result)
        summaries.append(summary)

        del workloads
        del testers
        del result
        gc.collect()

        test_results.display_results(summary)
        time.sleep(1)

    test_results.write_csv(OUTPUT_FILE, summaries)
