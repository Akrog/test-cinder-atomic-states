# What's this?
[Openstack]'s Block Storage project [Cinder] intends to allow High Availability active-active configurations in the next Liberty Cycle, and for that there are a number of changes that need to happen.

One of those changes is making state changes (changes in status field) atomic inside Cinder, and for that there are different solutions, this code tries to provide some insight into these solutions in an empirical way.

# What's the problem?
Right now Cinder has sections where status is checked for a valid state ([1a],[2a],[3a],[4a]) and later on some change is made to the resource ([1b],[2b],[3b],[4b]) and some action taken ([1c],[2c],[3c],[4c]) under the assumption that the resource has not changed and is not being accessed by anybody else, which in a multi-hosted active-active deployment is not appropriate.

Related to that matter is the issue of atomic state changes, ensuring that no other operation can be performed on the resource while we are making a state change ([1b],[2b],[3b],[4b]). There's an interesting [spec] on the subject.

This issue, as well as a consistent read, is usually trivial when you are working with only 1 DB server, but when you are working with a multi-master DB cluster things get a little bit tricky.

For example, you could read a value stating that the device is available but it's not, you just happen to read from a node that is about to get the latest replication update, or you may be changing a resource that is also being changed at the same time on another node.

On a multi-master DB clusters row locking doesn't work across nodes, so a SELECT ... FOR UPDATE will only lock the row in 1 of the nodes, not the others.

Of course Cinder is not the first project to face this problem, and there is a good blog post on [locking in Nova] where the issue is explained in detail.

# Solutions
- SELECT .. FOR UPDATE with retries on Deadlocks
- Compare and Swap with retries on Deadlocks
- DLM for the changes
- DLM for the whole operation

## SELECT .. FOR UPDATE with retries on Deadlocks
Some people say that select for update cannot be part of the solution because it doesn't work with Galera clusters.

Like I mentioned before it's true that the lock provided by select for update will only lock the row in the current node, but it's not a problem if we know a Deadlock can happen and we are ready for it.

Deadlocks will happen when there is a cross-node locking conflict. Fortunately it is guaranteed that only 1 or 0 requests will succeed in a conflict, which means that we can retry on such conflicts.

This solution is located at solutions/forupdate.py

## Compare and Swap with retries on Deadlocks

Compare an Swap is the technique explained in above mentioned blog post [locking in Nova] which basically means that you have to set a condition for your update and then check if the update was successful.

It is important to remember that we will still need retries on Deadlocks, as they could still happen when updates happen in different nodes at the same time or when an update is requested in a node where replication hasn't updated the data yet.

This solution is located at solutions/update_with_where.py

## DLM for the changes

Another solution is using a Distributed Lock Manager to lock access to the row in all nodes when we want to make a change.

In these tests I have used [Tooz] because it provides a convenient solution that can easily change drivers (Redis, file, Zookeper) and also has a timeout to release locks in case the owner dies or stops responding.

Here we have 2 solutions with [Tooz]:
- Using files in an NFS share: solutions/tooz_file.py
- Using Redis: solutions/tooz_redis.py

## DLM for the whole operation

Instead of just locking the state change in the DB you could lock the whole operation (creation, deletion, etc.) which makes sense since you don't want anybody else changing the volume while you are making changes to it.

This option is probably the most difficult to implement in Cinder given its component structure (API, Scheduler, Manager...) 

We have 2 solutions with [Tooz]:
- Using files in an NFS share: solutions/tooz_gl_file.py 
- Using Redis: solutions/tooz_gl_redis.py

# The tests

The tests are performed outside of Cinder, as independent pieces of code, facilitating the creation of new solutions to test.

For each of the solutions tests will be run against a DB where we will create NUM_ROWS fake volumes and against each of these volumes there will be a number of workers (WORKERS_PER_ROW) competing to make NUM_TESTS_PER_WORKER changes to the states, from available to deleting and back to available.

After acquiring the volume and changing it to deleting they will confirm that this is replicated in all nodes and that it is not changed by any other worker. Then they will proceed to change the state to available again.

[DuncanT] suggested that there should be a Synthetic Workload, so by default there will be 50 additional workers making 5 updates and 10 selects per second to their individual rows in the database while the tests are running.

Architecture:
- 1 HAProxy configured to send each request to a new server (roundrobin) with a Redis server and an NFS share (sync).
- 3 Galera-MariaDB server with rsync replication.
- PC to run tests

# The code

We all know that results depend not only on the HW used and the solution, but also on the implementation, so I made the code available in case some results didn't make sense.

Code is written in Python and uses processes to create the different workers.

Basic structure is:
- ha_test.py: The main program that runs the tests
- solutions: The different solutions that are tested on each execution
- workloaders: Synthetic workload generators

Configuration is mostly in ha_test.py (NUM_ROWS, WORKERS_PER_ROW, SYN_DB_GENERATORS, HAPROXY_IP, DB_NODES, DB_USER, DB_PASS...) but also in each of the specific solutions.

# The results

Program outputs data to stdout and then creates a CSV file with a summary of the results.

DB max_connections needs to be increased in DB nodes for these tests to run smoothly.

Total time is in seconds, all other timings are in ms.

Remember that while these test were run there were another 50 workers generating request to the DB.

Also consider that the more rows there are the more connections to the DBs are, because after changing to deleting the process will make 1 connection to each DB to check for the results. Therefore if you have 100 rows, you may have at one point 300 additional DB connections (100 to each node).

It is my belief that it is a more likely scenario that you have many resources (row) and few workers wanting to change the same one concurrently. After all, how many operations are we expecting to happen on the same volume at the same time? (I'm talking about update operations, not select).

Performed tests, are:
- Basic "baseline": 100 rows, 1 worker per row 
- Realistic "baseline": 400 rows, 1 worker per row 
- Realistic case: 100 rows, 3 workers per row 
- Stress case: 100 rows, 5 workers per row 
- Hell case requested by [DuncanT]: 5 rows, 100 workers per row 

Each worker will perform 10 changes in its row, so if we have 100 rows and 5 workers we'll have 5 x 100 x 10 available-deleting-available state changes.

## 100 rows, 1 worker per row

| solution | total time | release max | release mean | release stddev | release min | acquire max | acquire mean | acquire stddev | acquire min | deadlocks max | deadlocks sum | deadlocks mean | deadlocks stddev | deadlocks min | disconnect sum |
| :------- | ---: | -----: | ----: | ----: | ---: | -----: | ----: | ----: | ---: | --: | --: | --: | --: | --: | --: |
| forupdate | 4.40 | 218.48 | 26.68 | 25.88 | 2.81 | 381.54 | 31.79 | 47.43 | 2.97 | 0 | 0 | 0 | 0 | 0 | 0 |
| tooz_file | 4.50 | 228.29 | 87.10 | 41.05 | 3.99 | 780.60 | 107.56 | 79.52 | 4.40 | 0 | 0 | 0 | 0 | 0 | 0 |
| tooz_gl_file | 4.22 | 126.01 | 18.75 | 16.52 | 2.37 | 460.79 | 28.97 | 53.91 | 2.62 | 0 | 0 | 0 | 0 | 0 | 0 |
| tooz_gl_redis | 5.61 | 198.49 | 42.38 | 28.62 | 4.64 | 1200.63 | 127.49 | 254.20 | 5.65 | 0 | 0 | 0 | 0 | 0 | 0 |
| tooz_redis | 6.06 | 507.84 | 58.10 | 54.13 | 5.88 | 3771.47 | 154.26 | 374.98 | 6.15 | 0 | 0 | 0 | 0 | 0 | 0 |
| update_with_where | 3.94 | 115.51 | 14.13 | 13.18 | 1.74 | 240.55 | 18.73 | 34.33 | 1.87 | 0 | 0 | 0 | 0 | 0 | 0 |

## 400 rows, 1 worker per row

| solution | total time | release max | release mean | release stddev | release min | acquire max | acquire mean | acquire stddev | acquire min | deadlocks max | deadlocks sum | deadlocks mean | deadlocks stddev | deadlocks min | disconnect sum |
| :------- | ---: | -----: | ----: | ----: | ---: | -----: | ----: | ----: | ---: | --: | --: | --: | --: | --: | --: |
| forupdate | 17.39 | 404.27 | 127.54 | 50.47 | 2.66 | 1317.20 | 160.64 | 136.42 | 2.75 | 0 | 0 | 0 | 0 | 0 | 0 |
| tooz_file | 18.19 | 1164.34 | 466.64 | 145.95 | 3.88 | 1770.11 | 575.03 | 228.65 | 4.30 | 0 | 0 | 0 | 0 | 0 | 0 |
| tooz_gl_file | 17.05 | 833.11 | 80.82 | 45.86 | 2.42 | 1353.52 | 145.29 | 222.32 | 3.14 | 0 | 0 | 0 | 0 | 0 | 0 |
| tooz_gl_redis | 23.02 | 531.23 | 195.57 | 73.52 | 4.79 | 6572.62 | 564.95 | 1021.04 | 5.97 | 0 | 0 | 0 | 0 | 0 | 0 |
| tooz_redis | 54.02 | 30226.79 | 1423.02 | 5730.37 | 6.64 | 30180.03 | 1148.36 | 4031.52 | 6.45 | 0 | 0 | 0 | 0 | 0 | 0 |
| update_with_where | 15.94 | 761.38 | 65.66 | 48.20 | 1.70 | 999.90 | 81.98 | 103.42 | 1.65 | 0 | 0 | 0 | 0 | 0 | 0 |

## 100 rows, 3 workers per row

| solution | total time | release max | release mean | release stddev | release min | acquire max | acquire mean | acquire stddev | acquire min | deadlocks max | deadlocks sum | deadlocks mean | deadlocks stddev | deadlocks min | disconnect sum |
| :------- | ---: | -----: | ----: | ----: | ---: | -----: | ----: | ----: | ---: | --: | --: | --: | --: | --: | --: |
| forupdate | 29.74 | 458.64 | 87.75 | 46.30 | 2.61 | 21576.99 | 1666.43 | 2411.90 | 2.67 | 20 | 3097 | 1.03 | 2.39 | 0 | 0 |
| tooz_file | 16.40 | 896.80 | 217.52 | 70.93 | 4.22 | 5999.49 | 1002.62 | 748.24 | 4.39 | 1 | 1 | 0 | 0.02 | 0 | 0 |
| tooz_gl_file | 35.46 | 589.38 | 62.40 | 28.08 | 2.32 | 15801.65 | 2133.70 | 1748.04 | 3.06 | 1 | 3 | 0 | 0.03 | 0 | 0 |
| tooz_gl_redis | 27.16 | 497.82 | 104.87 | 61.36 | 4.67 | 19077.05 | 1529.61 | 2221.91 | 5.71 | 21 | 2179 | 0.73 | 2.17 | 0 | 0 |
| tooz_redis | 37.74 | 2374.17 | 341.09 | 315.21 | 5.93 | 22035.10 | 2186.44 | 2958.66 | 6.24 | 1 | 3 | 0 | 0.03 | 0 | 0 |
| update_with_where | 28.56 | 410.01 | 42.98 | 23.81 | 1.73 | 21912.22 | 1534.25 | 2201.45 | 1.75 | 19 | 2529 | 0.84 | 2.09 | 0 | 0 |

## 100 rows, 5 workers per row

| solution | total time | release max | release mean | release stddev | release min | acquire max | acquire mean | acquire stddev | acquire min | deadlocks max | deadlocks sum | deadlocks mean | deadlocks stddev | deadlocks min | disconnect sum |
| :------- | ---: | -----: | ----: | ----: | ---: | -----: | ----: | ----: | ---: | --: | --: | --: | --: | --: | --: |
| forupdate | 74.06 | 938.41 | 133.95 | 65.49 | 2.79 | 66457.25 | 4964.80 | 7712.70 | 2.89 | 40 | 7605 | 1.52 | 3.87 | 0 | 0 |
| tooz_file | 32.99 | 1969.80 | 319.56 | 110.44 | 4.34 | 14136.37 | 2237.51 | 1781.38 | 4.77 | 1 | 2 | 0 | 0.02 | 0 | 0 |
| tooz_gl_file | 95.10 | 530.60 | 101.45 | 37.88 | 2.32 | 69048.12 | 6915.23 | 6599.07 | 2.66 | 1 | 1 | 0 | 0.01 | 0 | 1 |
| tooz_gl_redis | 62.80 | 898.38 | 145.43 | 95.76 | 4.79 | 38103.20 | 4257.74 | 4490.45 | 5.50 | 26 | 5004 | 1 | 2.48 | 0 | 0 |
| tooz_redis | 82.45 | 3999.49 | 483.03 | 456.58 | 6.03 | 62078.86 | 5707.50 | 6965.76 | 6.14 | 1 | 3 | 0 | 0.02 | 0 | 0 |
| update_with_where | 71.49 | 362.69 | 69.96 | 38.14 | 1.70 | 63202.31 | 4717.18 | 6915.30 | 1.73 | 35 | 7272 | 1.45 | 3.57 | 0 | 0 |

## 5 rows, 100 workers per row

| solution | total time | release max | release mean | release stddev | release min | acquire max | acquire mean | acquire stddev | acquire min | deadlocks max | deadlocks sum | deadlocks mean | deadlocks stddev | deadlocks min | disconnect sum |
| :------- | ---: | -----: | ----: | ----: | ---: | -----: | ----: | ----: | ---: | --: | --: | --: | --: | --: | --: |
| forupdate | 669.92 | 1728.29 | 140.20 | 98.94 | 2.47 | 519704.30 | 57939.42 | 64540.98 | 2.92 | 47 | 18779 | 3.76 | 4.48 | 0 | 0 | 0 |
| tooz_file | 406.14 | 3490.77 | 356.61 | 318.81 | 3.40 | 343353.97 | 35441.05 | 39050.68 | 4.33 | 2 | 10 | 0 | 0.05 | 0 | 0 | 0 |
| tooz_gl_file | 1798.83 | 282.82 | 93.45 | 40.75 | 1.91 | 1795731.55 | 155522.78 | 242287.31 | 2.54 | 1 | 1 | 0 | 0.01 | 0 | 1 | 2137 |
| tooz_gl_redis | 57.19 | 339.17 | 5.61 | 7.41 | 3.24 | 45434.50 | 4349.53 | 4660.23 | 5.06 | 7 | 710 | 0.14 | 0.54 | 0 | 0 | 0 |
| tooz_redis | 608.34 | 8653.99 | 490.99 | 805.15 | 5.25 | 465611.49 | 46242.89 | 50004.22 | 5.62 | 1 | 8 | 0 | 0.04 | 0 | 0 | 0 |
| update_with_where | 413.52 | 548.61 | 81.84 | 56.70 | 1.59 | 372124.50 | 34867.09 | 46082.66 | 1.83 | 46 | 15188 | 3.04 | 4.65 | 0 | 0 | 0 |

# Conclusions

Total time is irrelevant, because it includes the time to confirm that all nodes have the right data and that no other worker has changed this data. So we have to look at acquire and release times.

For me the most realistic case is where there are only a few "fights" for the volume, so that would be the test with 100 rows and 3 workers fighting for each row.
In that test we can see that the best solution is locking with files, and the second best is the compare and swap solution, which is better on changing to available.
Even facing these results I would still go with a compare and swap with retries on Deadlocks as the chosen solution, because it doesn't require anything extra, you can achive atomic state changes with the DB alone, which in my opinion is a great plus, and also in the 400 rows and 1 worker per row, which would be the ideal world, outperforms any other solution.

# Disclaimer

The code is buggy as hell, as it was only meant as a way to create the data.

Basically expects everything to work fine on the tests and if it doesn't it'll probably just hang, so I'm not responsible for anything that happens if you run this tests.

**BEWARE:** By default the tests uses cinder DB and a table called volumes, so please don't have any relevant data there.

# Links

Since repositories are constantly changing links will point to the wrong place pretty quickly, so here are the methods they were meant to point to and the code it contained.

####1 - def extend(self, context, volume, new_size):
**[1a]:**
```python
if volume['status'] != 'available':
```
**[1b]:**
```python
self.update(context, volume, {'status': 'extending'})
```
**[1c]:**
```python
self.volume_rpcapi.extend_volume(context, volume, new_size,
                                 reservations)
```
####2 - def copy_volume_to_image(self, context, volume, metadata, force):
**[2a]:**
```python
self._check_volume_availability(volume, force)
```
**[2b]:**
```python
self.update(context, volume, {'status': 'uploading'})
```
**[2c]:**
```python
self.volume_rpcapi.copy_volume_to_image(context,
                                        volume,
                                        recv_metadata)
```
####3 - def delete_snapshot(self, context, snapshot, force=False):
**[3a]:**
```python
if not force and snapshot['status'] not in ["available", "error"]:
```
**[3b]:**
```python
snapshot_obj.status = 'deleting'
snapshot_obj.save(context)
```
**[3c]:**
```python
self.volume_rpcapi.delete_snapshot(context, snapshot_obj,
                                   volume['host'])
```

####4 - def create(self, context, name, description, volume_id, container, incremental=False, availability_zone=None):
**[4a]:**
```python
if volume['status'] != "available":
```
**[4b]:**
```python
self.db.volume_update(context, volume_id, {'status': 'backing-up'})
```
**[4c]:**
```python
self.backup_rpcapi.create_backup(context,
                                 backup['host'],
                                 backup['id'],
                                 volume_id)
```

[Cinder]: https://wiki.openstack.org/wiki/Cinder
[OpenStack]: https://www.openstack.org/
[1a]: https://github.com/openstack/cinder/blob/master/cinder/volume/api.py#L1149
[1b]: https://github.com/openstack/cinder/blob/master/cinder/volume/api.py#L1188
[1c]: https://github.com/openstack/cinder/blob/master/cinder/volume/api.py#L1189
[2a]: https://github.com/openstack/cinder/blob/master/cinder/volume/api.py#L1106
[2b]: https://github.com/openstack/cinder/blob/master/cinder/volume/api.py#L1128
[2c]: https://github.com/openstack/cinder/blob/master/cinder/volume/api.py#L1129
[3a]: https://github.com/openstack/cinder/blob/master/cinder/volume/api.py#L876
[3b]: https://github.com/openstack/cinder/blob/master/cinder/volume/api.py#L893
[3c]: https://github.com/openstack/cinder/blob/master/cinder/volume/api.py#L897
[4a]: https://github.com/openstack/cinder/blob/master/cinder/backup/api.py#L129
[4b]: https://github.com/openstack/cinder/blob/master/cinder/backup/api.py#L194
[4c]: https://github.com/openstack/cinder/blob/master/cinder/backup/api.py#L218
[spec]: https://review.openstack.org/#/c/95037/13/specs/juno/create-states.rst,unified
[locking in Nova]: http://www.joinfu.com/2015/01/understanding-reservations-concurrency-locking-in-nova/
[Tooz]: https://github.com/openstack/tooz
[DuncanT]: http://www.openstack.org/community/members/profile/5851
