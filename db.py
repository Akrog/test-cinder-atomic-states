#!/bin/env python

import functools
import time

from sqlalchemy import Column, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
import uuid
import cProfile
import contextlib


Base = declarative_base()


class Volume(Base):
    __tablename__ = 'volumes'
    id = Column(String(36), primary_key=True)
    status = Column(String(255))  # TODO(vish): enum?
    attach_status = Column(String(255))  # TODO(vish): enum
    migration_status = Column(String(255))


class WrongDataException(Exception):
    pass


class Db(object):
    def __init__(self, user, pwd, ip='127.0.0.1', db_name='cinder',
                 session_cfg={}, *args, **kwargs):
        self.ip = ip
        self.user = user
        self.pwd = pwd
        self.db_name = db_name

        self.engine = create_engine('mysql://%s:%s@%s/%s?charset=utf8' %
                                    (user, pwd, ip, db_name))

        # Base.metadata.create_all(engine)
        Base.metadata.bind = self.engine

        self.session = self.create_session(**session_cfg)

    def create_table(self):
        models = (Volume,)

        # Create all tables in the engine. This is equivalent to "Create Table"
        # statements in raw SQL.
        for model in models:
            model.metadata.create_all(self.engine)

    def close(self):
        self.session.close()
        self.engine.dispose()

    def get_engine(self):
        return self.engine

    def create_session(self, autocommit=True, expire_on_commit=True,
                       *args, **kwargs):
        return sessionmaker(bind=self.engine, autocommit=autocommit,
                            expire_on_commit=expire_on_commit, *args,
                            **kwargs)()

    @property
    def current_uuids(self):
        return map(lambda x: x[0], self.session.query(Volume.id).all())

    def populate(self, num_volumes=10):
        with self.session.begin():
            missing = num_volumes - self.session.query(Volume).count()
            self.session.query(Volume).update({Volume.status: 'available'})
            if missing > 0:
                for __ in xrange(missing):
                    self.session.add(Volume(id=uuid.uuid1(),
                                            status='available'))

    def check_volume(self, vol_id, data):
        with self.session.begin():
            vol = self.session.query(Volume).get(vol_id)
            for k, v in data.iteritems():
                d = getattr(vol, k)
                if d != v:
                    raise WrongDataException(
                        'Wrong data in server %s in %s, key %s, %s != %s' %
                        (self.ip, vol_id, k, v, d))


@contextlib.contextmanager
def profiled(enabled=True):
    pr = cProfile.Profile()
    if enabled:
        pr.enable()
    yield pr
    pr.disable()


def populate_database(db_data, num_rows):
    database = Db(**db_data)
    database.create_table()
    database.populate(num_rows)
    uuids = database.current_uuids[:num_rows]
    database.close()
    return (uuids)


RETRY_TIMEOUT = ('timeouts', 1205, 'Lock wait timeout exceeded')
RETRY_DEADLOCKS = ('deadlocks', 1213, 'Deadlock found')
RETRY_GONE = ('disconnect', 2006, 'MySQL server has gone away')
RETRY_GONE2 = ('disconnect', 2013, 'Lost connection to MySQL')
RETRY_GONE3 = ('disconnect', 2014, 'Lost connection to MySQL')
RETRY_GONE4 = ('disconnect', 2045, 'Lost connection to MySQL')
RETRY_GONE5 = ('disconnect', 2055, 'Lost connection to MySQL')
ALL_RETRIES = (RETRY_TIMEOUT, RETRY_DEADLOCKS, RETRY_GONE, RETRY_GONE2,
               RETRY_GONE3, RETRY_GONE4, RETRY_GONE5)


def retry_on_operational_error(method_or_which_cases):
    """Decorator to retry a DB API call if Deadlock was received."""
    def wrapper(f, which_cases=method_or_which_cases):
        @functools.wraps(f)
        def wrapped(session, *args, **kwargs):
            result = {case[0]: 0 for case in which_cases}
            while True:
                try:
                    f(session, *args, **kwargs)
                    return result
                except OperationalError as e:
                    for case in which_cases:
                        if e.args[0].startswith("(OperationalError) (%d, '%s" %
                                                (case[1], case[2])):
                            result[case[0]] += 1
                            break
                    else:
                        raise

                    # We wait a little bit before retrying
                    time.sleep(0.01)

        functools.update_wrapper(wrapped, f)
        return wrapped

    if callable(method_or_which_cases):
        return wrapper(method_or_which_cases, ALL_RETRIES)

    return wrapper


def check_volume(LOG, db_cfg, vol_id, data):
    """Check that a volumes has the same data in all cluster nodes."""
    def _check_volume(dbs):
        for node in dbs:
            LOG.debug('Checking node %s for %s', node, data)
            node.check_volume(vol_id, data)

    def _close_dbs(dbs):
        for node in dbs:
            node.close()

    def _create_dbs(db_cfg):
        db_cfg = db_cfg.copy()
        del db_cfg['ip']
        return (Db(ip=ip, **db_cfg) for ip in db_cfg.get('nodes_ips', []))

    dbs = _create_dbs(db_cfg)

    num_tries = 6
    i = 0
    while True:
        try:
            _check_volume(dbs)
            _close_dbs(dbs)
            return
        except Exception as e:
            if i < num_tries - 1:
                if isinstance(e, WrongDataException):
                    LOG.debug('Check retry, possible propagation delay with '
                              'changes %s', data)
                    i += 1
                else:
                    LOG.debug('Check exception, retry doesn\'t count: %s', e)
                time.sleep(0.25 * (i+1))
            else:
                LOG.error('Checking %s', data)
                _close_dbs(dbs)
                raise
