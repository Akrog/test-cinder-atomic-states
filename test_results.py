from collections import defaultdict
import math
import operator as op


class ResultDataPoint(object):
    """Object to store results for 1 row change."""
    def __init__(self, worker=0, num_test=0, status='OK', acquire=0.0,
                 release=0.0, profile=None, deadlocks=0, timeouts=0,
                 disconnect=0):
        self.worker = worker
        self.num_test = num_test
        self.acquire = acquire
        self.release = release
        self.status = status
        self.profile = profile
        self.deadlocks = deadlocks
        self.timeouts = timeouts
        self.disconnect = disconnect


def _calculate_stats(values, factor=1):
    """Calculate min, max, mean and stddev for values applying a factor."""
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


def _prepare_profile(data):
    """Filter, group and prepare profiling data for printing."""
    PATTERN = "<method '"

    def _rename_call(name):
        i = len(PATTERN)
        return name[i:name.index("'", i)]

    result = defaultdict(lambda: {'callcount': 0, 'time': 0.0})
    for profile in data:
        for call in profile:
            if ('sql' in call['name']
                    and call['name'].startswith(PATTERN)):
                name = _rename_call(call['name'])
                result[name]['callcount'] += call['callcount']
                result[name]['time'] += call['time']
    return result


def display_results(total_time, results):
    """Display results for given a worker test results."""
    STATS = (('acquire', 1000), ('release', 1000), ('deadlocks', 1),
             ('timeouts', 1), ('disconnect', 1))

    print 'Total running time %.2f secs (includes DB checks)' % total_time

    # We'll only display stats on successful results
    results_ok = tuple(r for r in results if r.status == 'OK')
    errors = len(results) - len(results_ok)

    # Calculate stats for all relevant fields of results
    stats = {}
    for var, factor in STATS:
        stats[var] = _calculate_stats(map(op.attrgetter(var), results_ok),
                                      factor)

    profile = _prepare_profile(map(op.attrgetter('profile'), results_ok))

    print 'OK:', len(results_ok)
    print 'Errors:', errors

    # Display stats
    print 'Changes stats:'
    for var, s in stats.iteritems():
        print '\t%s:' % var,
        for x in s.iteritems():
            print '%s=%.2f' % x,
        print

    # Display profiling data
    print 'Profiling data:'
    for name, data in profile.iteritems():
        print '\t%s: %d calls, %.2fms' % (name, data['callcount'],
                                          data['time'] * 1000)


def map_profile_info(profile):
    """Map profiling information to that we consider relevant."""
    result = map(
        lambda p: {
            'callcount': p.callcount,
            'time': p.totaltime,
            'name': p.code if isinstance(p.code, str) else p.code.co_name,
            'file': None if isinstance(p.code, str) else p.code.co_filename},
        profile.getstats())
    return result
