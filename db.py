#!/bin/env python

import os
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import uuid
from sqlalchemy import and_


Base = declarative_base()

class Volume(Base):
    __tablename__ = 'volumes'
    id = Column(String(36), primary_key=True)
    status = Column(String(255))  # TODO(vish): enum?
    attach_status = Column(String(255))  # TODO(vish): enum
    migration_status = Column(String(255))


class Db(object):
    def __init__(self, user, pwd, ip='127.0.0.1', db_name='cinder', session_cfg={}):
        self.ip = ip
        self.user = user
        self.pwd = pwd
        self.db_name = db_name

        # Create an engine that stores data in the local directory's
        # sqlalchemy_example.db file.
        #engine = create_engine('sqlite:///sqlalchemy_example.db')
        self.engine = create_engine('mysql://%s:%s@%s/%s?charset=utf8' % (user, pwd,
                                    ip, db_name))

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

    def create_session(self, autocommit=True, expire_on_commit=False, *args, **kwargs):
        return sessionmaker(bind=self.engine, autocommit=autocommit,
                            expire_on_commit=expire_on_commit, *args, **kwargs)()

    @property
    def current_uuids(self):
        return map(lambda x: x[0], self.session.query(Volume.id).all())
            
    def populate(self, num_volumes=10):
        missing = num_volumes - self.session.query(Volume).count()
        if missing > 0:
            for __ in xrange(missing):
                self.session.add(Volume(id=uuid.uuid1(), status='available'))
