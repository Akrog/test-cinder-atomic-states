from collections import defaultdict
import itertools as it
import math
import operator as op
from pprint import pprint


class ResultDataPoint(object):
    def __init__(self, worker=0, num_test=0, status='OK', acquire=0.0, release=0.0,
                 profile=None, deadlocks=0, timeouts=0, disconnect=0):
        self.worker = worker
        self.num_test = num_test
        self.acquire = acquire
        self.release = release
        self.status = status
        self.profile = profile
        self.deadlocks = deadlocks
        self.timeouts = timeouts
        self.disconnect = disconnect


def calculate_stats(values, factor):
    result = {'min': min(values) * factor,
              'max': max(values) * factor,
              'mean': 0,
              'stddev': 0}

    if values:
        mean = sum(values) / float(len(values))
        result['mean'] = factor * mean
        result['stddev'] = (
            factor * math.sqrt((1.0 / (len(values) - 1))
                               * sum((x - mean) ** 2 for x in values)))

    return result


def display_results(total_time, results):
    STATS = (('acquire', 1000), ('release', 1000), ('deadlocks', 1),
             ('timeouts', 1), ('disconnect', 1))
    PATTERN = "<method '"

    print 'Total running time %.2f secs (includes DB checks)' % total_time

    results_ok = tuple(r for r in results if r.status == 'OK')
    stats = {}
    for var, factor in STATS:
        stats[var] = calculate_stats(map(op.attrgetter(var), results_ok),
                                     factor)
    errors = len(results) - len(results_ok)

    acc = defaultdict(lambda: {'callcount': 0, 'time': 0.0})    
    for result in results_ok:
        for call in result.profile:
            if ('sql' in call['name']
                    and call['name'].startswith(PATTERN)):
                acc[call['name']]['callcount'] += call['callcount']
                acc[call['name']]['time'] += call['time']

    print 'OK:', len(results_ok)
    print 'Errors:', errors
    print 'Changes stats:'
    for var, s in stats.iteritems():
        print '\t%s:' % var,
        for x in s.iteritems():
            print '%s=%.2f' % x,
        print

    print 'Profiling data:'
    for name, data in acc.iteritems():
        i = len(PATTERN)
        n = name[i:name.index("'", i)]
        print '\t%s: %d calls, %.2fms' % (n, data['callcount'],
                                              data['time'] * 1000) 


def prepare_profile_info(profile):
    result = map(
        lambda p: {
            'callcount': p.callcount, 
            'time': p.totaltime, 
            'name': p.code if isinstance(p.code, str) else p.code.co_name, 
            'file': None if isinstance(p.code, str) else p.code.co_filename},
        profile.getstats())
    return result
