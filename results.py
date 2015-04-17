
from collections import defaultdict
from pprint import pprint

def display_results(total_time, results):
    print 'Total running time %.2f secs (includes DB checks)' % total_time
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
    sql = list(
        filter(lambda r: 'sql' in r['name'] and r['name'].startswith(pattern),
               result['profile'])
        for result in results)
    acc = defaultdict(lambda: {'callcount': 0, 'time': 0.0})    
    for result in sql:
        for call in result:
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
