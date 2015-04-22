from collections import defaultdict
import csv
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


class Summary(object):
    def __init__(self, total_time=0, solution=None, ok=0, errors=0, stats={},
                 profile=[]):
        self.total_time = total_time
        self.solution = solution
        self.ok = ok
        self.errors = errors
        self.stats = stats
        self.profile = profile


def _calculate_stats(values, factor=1):
    """Calculate min, max, mean and stddev for values applying a factor."""
    result = {'min': min(values) * factor,
              'max': max(values) * factor,
              'sum': sum(values) * factor,
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


def summarize(solution, total_time, results):
    STATS = (('acquire', 1000), ('release', 1000), ('deadlocks', 1),
             ('timeouts', 1), ('disconnect', 1))

    # We'll only display stats on successful results
    results_ok = tuple(r for r in results if r.status == 'OK')
    errors = len(results) - len(results_ok)

    # Calculate stats for all relevant fields of results
    stats = {}
    for var, factor in STATS:
        stats[var] = _calculate_stats(map(op.attrgetter(var), results_ok),
                                      factor)

    profile = _prepare_profile(map(op.attrgetter('profile'), results_ok))

    return Summary(total_time, solution.__name__, len(results_ok), errors,
                   stats, profile)


def display_results(summary):
    """Display results for given a worker test results."""
    print ('Total running time %.2f secs (includes DB checks)'
           % summary.total_time)

    print 'OK:', summary.ok
    print 'Errors:', summary.errors

    # Display stats
    print 'Changes stats:'
    for var, s in summary.stats.iteritems():
        print '\t%s:' % var,
        for x in s.iteritems():
            print '%s=%.2f' % x,
        print

    # Display profiling data
    print 'Profiling data:'
    for name, data in summary.profile.iteritems():
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


def write_csv(filename, summaries, float_format='%.02f'):
    """Write all results to CSV a file."""
    data = [['solution', 'total time', 'ok', 'errors']]

    for var, s in summaries[0].stats.iteritems():
        for stat in s:
            data[0].append('%s %s' % (var, stat))

    for summary in summaries:
        row = [summary.solution, float_format % summary.total_time, summary.ok,
               summary.errors]
        for s in summary.stats.itervalues():
            for stat in s.itervalues():
                row.append(float_format % stat)
        data.append(row)

    with open(filename, 'wb') as csv_file:
        writer = csv.writer(csv_file)
        for row in data:
            writer.writerow(row)
