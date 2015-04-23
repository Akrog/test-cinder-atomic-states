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
