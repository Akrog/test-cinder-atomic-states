#!/bin/env python

import multiprocessing as mp


class Tester(object):
    def __init__(self, worker, params=None, *args, **kwargs):
        self.worker = worker

        # If has a next method use as it is, otherwise try to create iterable
        self.params = (params if hasattr(params, 'next')
                       else iter(params or tuple()))
        self.args = args
        self.kwargs = kwargs

    def run(self, num_workers):
        pool = mp.Pool(processes=num_workers)
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


class Workloader(object):
    def __init__(self, worker, params=None, *args, **kwargs):
        self.worker = worker

        # If has a next method use as it is, otherwise try to create iterable
        self.params = (params if hasattr(params, 'next')
                       else iter(params or tuple()))
        self.args = args
        self.kwargs = kwargs

        self.stop = mp.Value('b', False)

    def run(self, num_workers):
        self.workers = []

        for i in xrange(num_workers):
            args = [i, self.stop]
            args.extend(self.args)
            kwargs = self.kwargs.copy()
            try:
                params = self.params.next()
                args.extend(params.get('args', []))
                kwargs.update(params.get('kwargs', {}))
            except StopIteration:
                pass

            worker = mp.Process(target=self.worker, args=args, kwargs=kwargs)
            self.workers.append(worker)

        for w in self.workers:
            w.start()

        return self.stop

    def finish(self):
        self.stop.value = True

        for w in self.workers:
            w.join()
        return (w.exitcode() for w in self.workers)
