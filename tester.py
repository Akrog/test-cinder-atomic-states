#!/bin/env python

from multiprocessing import Pool

class Tester(object):
    def __init__(self, worker, params=None, *args, **kwargs):
        self.worker = worker
        self.params = params if hasattr(params, 'next') else iter(params or tuple())
        self.args = args
        self.kwargs = kwargs

    def run(self, num_workers):
        pool = Pool(processes=num_workers)
        workers = []

        for i in xrange(num_workers):
            args = [i]
            args.extend(self.args)
            kwargs = self.kwargs.copy()
            try:
                params = self.params.next()
                args.extend(params.get('args', []))
                kwargs.update(params.get('kwargs', {}))
            except StopIteration:
                pass
            
            workers.append(pool.apply_async(self.worker, args, kwargs))

        pool.close()
        pool.join()
        results = (w.get() for w in workers)
        return results

