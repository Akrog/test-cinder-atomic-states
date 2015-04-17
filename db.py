#!/bin/env python

import pdb

import functools
import os
import time

from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
import uuid
from sqlalchemy import and_
import cProfile
import StringIO
import pstats
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

        # Create an engine that stores data in the local directory's
        # sqlalchemy_example.db file.
        #engine = create_engine('sqlite:///sqlalchemy_example.db')
        self.engine = create_engine('mysql://%s:%s@%s/%s?charset=utf8' %
                                    (user, pwd, ip, db_name))

        #Base.metadata.create_all(engine)
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
                        (node[2], vol_id, k, v, d))


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
                    #print 'Operational', e
                    for case in which_cases:
                        #print 'Trying with', case
                        if e.args[0].startswith("(OperationalError) (%d, '%s" %
                                                (case[1], case[2])):
                            #print 'found'
                            result[case[0]] += 1
                            break
                    else:
                        raise

                    #print 'retyring'
                    # We wait a little bit before retrying
                    time.sleep(0.01)

        functools.update_wrapper(wrapped, f)
        return wrapped

    if callable(method_or_which_cases):
        return wrapper(method_or_which_cases, ALL_RETRIES)

    return wrapper
