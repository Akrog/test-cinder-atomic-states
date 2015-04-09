#!/bin/env python

from multiprocessing import Pool

class Tester(object):
    def __init__(self, worker, params=None, *args, **kwargs):
        self.worker = worker
        self.params = params
        self.args = args
        self.kwargs = kwargs

    def run(self, num_workers):
        pool = Pool(processes=num_workers)
        workers = []

        for i in xrange(num_workers):
            args = [i]
            args.extend(self.args)
            kwargs = self.kwargs.copy()
            if self.params and len(self.params) > i:
                args.extend(self.params[i].get('args', []))
                kwargs.update(self.params[i].get('kwargs', {}))             
            
            workers.append(pool.apply_async(self.worker, args, kwargs))

        pool.close()
        pool.join()
        results = (w.get() for w in workers)
        return results

