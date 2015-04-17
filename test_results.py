from collections import defaultdict
import itertools as it
import operator as op
from pprint import pprint


class ResultDataPoint(object):
    def __init__(self, worker=0, num_test=0, status='OK', acquire=0.0, release=0.0,
                 profile=None, deadlocks=0, timeouts=0, lost_conn=0):
        self.worker = worker
        self.num_test = num_test
        self.acquire = acquire
        self.release = release
        self.status = status
        self.profile = profile
        self.deadlocks = deadlocks
        self.timeouts = timeouts
        self.lost_conn = lost_conn


def display_results(total_time, results):
    print 'Total running time %.2f secs (includes DB checks)' % total_time
    pattern = "<method '"
    i = 0
    errors = 0
    deadlocks = 0
    total_time = 0.0
    total_delete_time = 0.0

    for r in results:
        if r.status == 'OK':
            i += 1 
            total_time += r.acquire
            total_delete_time += r.release
            deadlocks += r.deadlocks
        else:
            errors += 1

    acc = defaultdict(lambda: {'callcount': 0, 'time': 0.0})    
    for result in results:
        for call in result.profile:
            if ('sql' in call['name']
                    and call['name'].startswith(pattern)):
                acc[call['name']]['callcount'] += call['callcount']
                acc[call['name']]['time'] += call['time']

    if i:
        print 'Errors:', errors
        print 'Deadlocks:', deadlocks
        print('Average time for each change is %.2fms and deletion is %.2fms' %
              ((total_time / i) * 1000, (total_delete_time / i) * 1000))
        for name, data in acc.iteritems():
            i = len(pattern)
            n = name[i:name.index("'", i)]
            print '\t%s: %d calls, %.2fms' % (n, data['callcount'],
                                              data['time'] * 1000) 

    #pprint(dict(acc))


def prepare_profile_info(profile):
    result = map(
        lambda p: {
            'callcount': p.callcount, 
            'time': p.totaltime, 
            'name': p.code if isinstance(p.code, str) else p.code.co_name, 
            'file': None if isinstance(p.code, str) else p.code.co_filename},
        profile.getstats())
    return result
