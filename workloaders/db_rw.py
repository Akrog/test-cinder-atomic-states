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

# Synthetic workload generator for DB selects and updates

import time
import uuid

from sqlalchemy.exc import IntegrityError

import db


@db.retry_on_operational_error
def do_workload(worker_id, stop, db_data, num_selects=10, num_updates=5,
                *args, **kwargs):
    total_operations = num_selects + num_updates
    wait_time = 1.0 / total_operations
    operations = tuple(range(total_operations))

    database = db.Db(session_cfg={'autocommit': True,
                                  'expire_on_commit': True},
                     **db_data)

    # Add a specific volume for our workload
    while True:
        my_uuid = uuid.uuid1()
        try:
            with database.session.begin():
                database.session.add(db.Volume(id=my_uuid,
                                               status='available'))
                break
        except IntegrityError:
            pass

    # While shared stop value doesn't change
    while not stop.value:
        for i in operations:
            with database.session.begin():
                if i < num_selects:
                    v = database.session.query(db.Volume).get(my_uuid)
                else:
                    v.attach_status = '%s-%s' % (worker_id, i)
            time.sleep(wait_time)

    # We remove our volume after we have finished the tests
    with database.session.begin():
        database.session.delete(v)

    database.close()
    return True
