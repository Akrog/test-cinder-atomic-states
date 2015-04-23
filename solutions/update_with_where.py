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

import db
import time
from sqlalchemy import and_

session_cfg = {'autocommit': True, 'expire_on_commit': True}


# Code extracted from https://review.openstack.org/#/c/109837/
def safe_update(session, instance_id, values, expected_values):
    """Attempts to update the instance record in the database.

    Constructs a raw UPDATE SQL statement, with a WHERE condition that
    contains not only the instance UUID, but also a collection of
    expected field/value combinations. The function returns the number
    of records that were affected by the UPDATE statement, so this can
    be used to implement a SQL-based compare-and-swap loop, where the
    caller attempts to update the database record for the instance, but
    only update the record if the existing record matches precisely what
    the caller expects. The alternative to this is to use the lock-heavy
    SELECT FOR UPDATE.

    :param session: DB session to grab a connection from.
    :param instance_uuid: UUID of the instance to attempt an update for.
    :param values: The new field values to set.
    :param expected_values: The old values for some fields that we expect
                            to be in the current record, otherwise we don't
                            do the update.
    :returns The number of records that were affected by the UPDATE statement
    """
    if not values:
        raise ValueError('Attempted to update an instance with no new values.')

    conn = session.connection()
    inst_tab = db.Volume.__table__
    where_conds = [inst_tab.c.id == instance_id]
    for field, value in expected_values.items():
        where_conds.append(inst_tab.c[field] == value)
    upd_stmt = inst_tab.update().where(and_(*where_conds)).values(**values)
    try:
        res = conn.execute(upd_stmt)
    finally:
        conn.close()
    return res.rowcount


@db.retry_on_operational_error
def make_change(session, vol_id, initial, destination, attach_status):
    n = 0
    while True:
        n = safe_update(
            session, vol_id,
            {'status': destination, 'attach_status': attach_status},
            {'status': initial})
        if n != 0:
            return
        time.sleep(0.01)
