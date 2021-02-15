"""
Copyright (c) 2019, OptoFidelity OY

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

    1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
    2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
    3. All advertising materials mentioning features or use of this software must display the following acknowledgement: This product includes software developed by the OptoFidelity OY.
    4. Neither the name of the OptoFidelity OY nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY
EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY
DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text, BLOB
from sqlalchemy.orm import relation, backref, sessionmaker
from sqlalchemy.ext.declarative import declarative_base, declared_attr
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
import json
import time
import sqlite3
import logging

Base = declarative_base()

logger = logging.getLogger(__name__)

database_path = None
config_path = None

# The global database singleton instance
database = None


def setup_database(db_path, conf_path):
    global database_path, config_path
    database_path, config_path = db_path, conf_path


def get_database():
    """ Returns the global database instance """
    global database
    if database is None:
        db_path = get_last_path() if database_path is None else database_path
        database = ResultDatabase(db_path)
    return database


def on_connect(conn, record):
    conn.execute('pragma foreign_keys=ON')


def save_last_path(path):
    with open(config_path, 'w') as f:
        f.write(json.dumps({"lastDB": path}))


def get_last_path():
    try:
        with open(config_path, 'r') as f:
            data = json.load(f)
        return data.get('lastDB', database_path)

    except FileNotFoundError as e:
        logger.error(str(e))
        return database_path


def create_sqlite_indices(database_file, indices):
    """ Creates indices to the SQLite database """
    db = sqlite3.connect(database_file)

    curindices = get_current_indices(db)

    for index_values in indices:
        # For some reason curindices has '_fkey' appended to names

        index_name = index_values[0] + '_fkey'

        if index_name not in curindices:
            logging.info('Creating database index %s' % index_name)
            create_index(db, index_name, index_values)

    db.close()


def get_current_indices(database):
    """ Returns an array of currently declared indices in the database """

    c = database.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
    return [r[0] for r in c.fetchall()]


def create_index(database, index_name, index_values):
    """ Creates the specified index in the database """
    database.execute('CREATE INDEX IF NOT EXISTS %s ON %s ( %s )' % (index_name, index_values[0], index_values[1]))


class ResultDatabase:

    def __init__(self, filename):
        self.db = None
        self.session = None
        self.dbpath = None

        self.initialize(filename)
        save_last_path(filename)

    def initialize(self, filename):

        self.dbpath = filename
        self.db = create_engine('sqlite:///' + filename)
        event.listen(self.db, 'connect', on_connect)
        self.session = sessionmaker(bind=self.db, autoflush=False)
        Base.metadata.create_all(self.db)

        # These are database indices for various test and test result tables.
        indices = [
            ('dut_parameters', 'dut_id'),
            ('session_parameters', 'testsession_id'),
            ('test_item', 'testsession_id'),
            ('test_result', 'test_id'),
        ]

        for test in BaseTest.__subclasses__():
            indices.append((test.__tablename__, 'test_id'))
        for result in BaseResults.__subclasses__():
            indices.append((result.__tablename__, 'gesture_id'))

        create_sqlite_indices(filename, indices)

        # Check if ResultDatabase already contains test types below.
        try:
            # TODO (b/148627899): It would be nice if these test type names were defined in respective test case Python
            #  files. However, do we want the ID values to be unique if test case order or number changes? Perhaps
            #  hash from name?
            # Note: TestType integer IDs must match the ones used in analysis.
            session = self.session()
            session.add(TestType(0, 'Finger Tracking Test'))
            session.add(TestType(1, 'Finger To Edge Test'))
            session.add(TestType(2, 'Swipe Test'))
            session.add(TestType(3, 'Pinch Test'))
            session.add(TestType(4, 'Tap Test'))
            session.add(TestType(5, 'Repeated Taps Test'))
            session.add(TestType(6, 'Stationary Then Move Test'))
            session.add(TestType(7, 'Drumroll Test'))
            session.add(TestType(8, 'Compass Test'))
            session.add(TestType(9, 'Compass With Taps Test'))
            session.add(TestType(10, 'Stationary With Taps Test'))
            session.add(TestType(11, 'Single Line With Noise Test'))
            session.add(TestType(12, 'Stationary With Noise Test'))
            session.commit()
            session.close()
        except IntegrityError:
            # Already created
            pass

        self.check_setting(
            Setting('max_linearity', 2.0, 'mm', 'Max linearity error limit'))
        self.check_setting(
            Setting('rms_linearity', 0.5, 'mm', 'RMS linearity error limit'))
        self.check_setting(
            Setting('max_circularity', 2.0, 'mm', 'Max circularity error limit'))
        self.check_setting(
            Setting('rms_circularity', 0.5, 'mm', 'RMS circularity error limit'))
        self.check_setting(
            Setting('angle_error', 4.0, 'deg', 'Maximum angle error for swipe'))
        self.check_setting(
            Setting('gap_ratio', 1.8, '', 'Maximum ratio of gaps between adjacent touch reports'))
        self.check_setting(
            Setting('reversed_motion', 1.0, 'mm', 'Maximum reversed motion during swipe'))
        self.check_setting(
            Setting('report_rate', 60.0, 'Hz', 'Minimum report rate'))
        self.check_setting(
            Setting('stationary_movement', 1.0, 'mm', 'Maximum movement for stationary touches'))
        self.check_setting(
            Setting('minimum_radius', 0.5, 'mm', 'Minimum enclosing radius for repeated taps'))
        self.check_setting(
            Setting('drumroll_radius', 2.0, 'mm', 'Minimum enclosing radius for any drumroll location'))
        self.check_setting(
            Setting('edge_range', 0.5, 'mm', 'Maximum gap for reporting from screen edge'))
        self.check_setting(
            Setting('swipe_length', 1.0, 'mm', 'Maximum error for length of swipe'))
        self.check_setting(
            Setting('packet_count', 3, '', 'Minimum packet count'))
        self.check_setting(
            Setting('movement_hysteresis', 2.0, '', 'Maximum ratio (d1/d2) of distance moved for a previously '
                                                    'stationary finger, where d1 is the distance from the first to '
                                                    'second positions and d2 is the distance from the second to third '
                                                    'positions'))

        # When adding settings, remember to add them to settings.py categories in the TPPT analysis repo

    def change_database(self, path):
        self.initialize(path)
        save_last_path(path)

    def add(self, data, commit=True, expire_on_commit=True):
        session = self.session(expire_on_commit=expire_on_commit)
        session.add(data)
        if commit:
            self.session_commit(session)
        try:
            return data.id
        finally:
            session.close()

    def add_all(self, data, commit=True):
        session = self.session()
        session.add_all(data)
        if commit:
            self.session_commit(session)
        session.close()

    def get_engine(self):
        return self.db

    def update(self, data):
        session = self.session()
        session.merge(data)
        self.session_commit(session)
        session.close()

    def commit(self):
        session = self.session()
        self.session_commit(session)
        session.close()

    def session_commit(self, session):
        # If database is locked, try again until timeout occurs
        max_wait_time = 15
        start = time.time()
        while True:
            try:
                session.commit()
                break
            except sqlite3.OperationalError as e:
                if time.time() - start > max_wait_time:
                    raise e

    def get_test_sessions(self, db_session=None):
        if db_session is None:
            db_session = self.session()
        try:
            return db_session.query(TestSession).all()
        finally:
            db_session.close()

    def get_test_session(self, session_id):
        session = self.session()
        try:
            return session.query(TestSession).filter_by(id=session_id).first()
        finally:
            session.close()

    def get_test_type(self, type_id):
        session = self.session()
        try:
            return session.query(TestType).filter_by(id=type_id).all()
        finally:
            session.close()

    def get_test_types(self):
        session = self.session()
        try:
            return session.query(TestType).all()
        finally:
            session.close()

    def get_programs(self):
        session = self.session()
        try:
            return session.query(TestSession.program).order_by(TestSession.program)
        finally:
            session.close()

    def get_manufacturers(self):
        session = self.session()
        try:
            return session.query(TestSession.manufacturer).order_by(TestSession.manufacturer).all()
        finally:
            session.close()

    def check_setting(self, setting):
        session = self.session()
        db_setting = session.query(Setting).filter_by(id=setting.id).first()
        if db_setting is None:
            # Setting does not exist
            session.add(setting)
            self.session_commit(session)
        session.close()


# Define database tables


class TestSession(Base):
    # TestSession is constant to all test cases
    __tablename__ = 'test_session'

    id = Column(Integer, primary_key=True)
    operator = Column(String)
    starttime = Column(String)
    endtime = Column(String)
    invalid = Column(Boolean)
    notes = Column(String)
    tnt_version = Column(String)
    tppt_version = Column(String)
    station_id = Column(String)


class TestDUT(Base):
    # A DUT that is tested in one or multiple test sessions and referenced to in Test Items
    __tablename__ = 'test_dut'
    id = Column(Integer, primary_key=True)

    # Dut parameters
    program = Column(String)
    manufacturer = Column(String)
    batch = Column(String)
    serial = Column(String)
    sample_id = Column(String)
    svg_data = Column(BLOB)


class TestType(Base):
    # Device digitizer touch test types stored here
    __tablename__ = 'test_type'

    id = Column(Integer, primary_key=True)
    name = Column(String)

    def __init__(self, _id, name):
        self.id = _id
        self.name = name


class TestItem(Base):
    # A single test related to device digitizer touch is defined here
    __tablename__ = 'test_item'

    id = Column(Integer, primary_key=True)
    testsession_id = Column(Integer, ForeignKey('test_session.id', ondelete='CASCADE'), nullable=False)
    testsession = relation(TestSession, backref=backref('test_items', order_by=id))
    dut_id = Column(Integer, ForeignKey('test_dut.id'), nullable=False)
    dut = relation(TestDUT, backref=backref('test_items', order_by=id))
    starttime = Column(String)
    endtime = Column(String)
    slot_id = Column(Integer)
    finger_type = Column(String)
    invalid = Column(Boolean)
    kmsg_log = Column(Text)
    testtype_id = Column(Integer, ForeignKey('test_type.id', ondelete='CASCADE'), nullable=False)
    type = relation(TestType, backref=backref('test_items', order_by=id))


class SessionParameters(Base):
    __tablename__ = 'session_parameters'

    id = Column(Integer, primary_key=True)
    testsession_id = Column(Integer, ForeignKey('test_session.id', ondelete='CASCADE'), nullable=False)
    testsession = relation(TestSession, backref=backref('session_parameters', order_by=id))
    name = Column(String)
    valueFloat = Column(Float)
    valueString = Column(String)
    isFloat = Column(Boolean)


class DutParameters(Base):
    __tablename__ = 'dut_parameters'

    id = Column(Integer, primary_key=True)
    dut_id = Column(Integer, ForeignKey('test_dut.id', ondelete='CASCADE'), nullable=False)
    dut = relation(TestDUT, backref=backref('dut_parameters', order_by=id))
    name = Column(String)
    valueFloat = Column(Float)
    valueString = Column(String)
    isFloat = Column(Boolean)


class Setting(Base):
    __tablename__ = 'settings'
    id = Column(String, primary_key=True)
    value = Column(Float, nullable=False)
    unit = Column(String)
    desc = Column(String)

    def __init__(self, _id, value, unit, desc):
        self.id = _id
        self.value = value
        self.unit = unit
        self.desc = desc


class TestResult(Base):
    __tablename__ = 'test_result'
    id = Column(Integer, primary_key=True)
    test_id = Column(Integer, ForeignKey('test_item.id', ondelete='CASCADE'), nullable=False)
    test = relation(TestItem, backref=backref('test_results'))
    result = Column(String)
    calculated = Column(DateTime)


def camel_to_snake(camel):
    snake = [camel[0].lower()]
    for c in camel[1:]:
        if c.isupper():
            snake.append('_')
        snake.append(c.lower())
    return ''.join(snake)


class BaseTest(object):
    """ Mixin class for test gestures.

    Each test case should have a table definition using this mixin, defining a single
    gesture performed by the robot. The class must be named XXXXTest, and there must
    be a corresponding XXXXResults class defined to hold measurement results. This mixin
    and the BaseResults mixin set up the mappings between the database tables.
    """

    @declared_attr
    def __tablename__(cls):
        if not cls.__name__.endswith('Test'):
            raise ValueError('BaseTest class names must end in "Test"')
        return camel_to_snake(cls.__name__)

    @declared_attr
    def test_id(cls):
        return Column(Integer, ForeignKey('test_item.id', ondelete='CASCADE'), nullable=False)

    @declared_attr
    def test(cls):
        return relation(TestItem, backref=backref(cls.__tablename__, order_by=cls.id))

    id = Column(Integer, primary_key=True)


class BaseResults(object):
    """ Mixin class for test results.

    Each test case should have a table definition using this mixin, defining a single
    touch measurement. The class must be named XXXXResults, and there must be a corresponding
    XXXXTest class defined. This mixin sets up the mappings between the tables, and defines the
    common results fields.
    """

    def _test_table_name(cls):
        return cls.__tablename__[:cls.__tablename__.rfind('results')] + 'test'

    def _test_class_name(cls):
        return cls.__name__[:cls.__name__.rfind('Results')] + 'Test'

    @declared_attr
    def __tablename__(cls):
        if not cls.__name__.endswith('Results'):
            raise ValueError('BaseResults class names must end in "Results"')
        return camel_to_snake(cls.__name__)

    @declared_attr
    def gesture_id(cls):
        return Column(Integer, ForeignKey(cls._test_table_name(cls) + '.id', ondelete='CASCADE'), nullable=False)

    @declared_attr
    def gesture(cls):
        return relation(cls._test_class_name(cls), backref=backref(cls.__tablename__, order_by=cls.id))

    id = Column(Integer, primary_key=True)

    panel_x = Column(Float)
    panel_y = Column(Float)
    pressure = Column(Float)
    finger_id = Column(Integer)
    time = Column(Float)
    event = Column(Integer)


class CompassTest(Base, BaseTest):
    center_x = Column(Float)
    center_y = Column(Float)

    finger_size = Column(Float)
    separation = Column(Float)
    start_azimuth = Column(Float)
    end_azimuth = Column(Float)


class CompassResults(Base, BaseResults):
    pass


class CompassWithTapsTest(Base, BaseTest):
    center_x = Column(Float)
    center_y = Column(Float)

    finger_size = Column(Float)
    separation = Column(Float)
    start_azimuth = Column(Float)
    end_azimuth = Column(Float)

    tap_azimuth_step = Column(Float)


class CompassWithTapsResults(Base, BaseResults):
    pass


class DrumrollTest(Base, BaseTest):
    center_x = Column(Float)
    center_y = Column(Float)

    finger_size = Column(Float)
    separation = Column(Float)
    azimuth = Column(Float)
    number_taps = Column(Integer)


class DrumrollResults(Base, BaseResults):
    pass


class FingerToEdgeTest(Base, BaseTest):
    # For multi-finger lines, these are the coordinates of the primary finger (left-most with
    # zero azimuth)
    start_x = Column(Float)
    start_y = Column(Float)
    end_x = Column(Float)
    end_y = Column(Float)


class FingerToEdgeResults(Base, BaseResults):
    pass


class FingerTrackingTest(Base, BaseTest):
    # For multi-finger lines, these are the coordinates of the primary finger (left-most with
    # zero azimuth)
    start_x = Column(Float)
    start_y = Column(Float)
    end_x = Column(Float)
    end_y = Column(Float)

    num_fingers = Column(Integer)
    finger_size = Column(Float)
    swipe_speed = Column(Float)
    separation = Column(Float)
    azimuth = Column(Float)


class FingerTrackingResults(Base, BaseResults):
    pass


class PinchTest(Base, BaseTest):
    center_x = Column(Float)
    center_y = Column(Float)

    finger_size = Column(Float)
    start_separation = Column(Float)
    end_separation = Column(Float)
    azimuth = Column(Float)


class PinchResults(Base, BaseResults):
    pass


class RepeatedTapsTest(Base, BaseTest):
    tap_x = Column(Float)
    tap_y = Column(Float)

    number_taps = Column(Integer)

    finger_size = Column(Float)
    edge_width = Column(Float)


class RepeatedTapsResults(Base, BaseResults):
    pass


class SingleLineWithNoiseTest(Base, BaseTest):
    start_x = Column(Float)
    start_y = Column(Float)
    end_x = Column(Float)
    end_y = Column(Float)

    finger_size = Column(Float)
    frequency = Column(Float)


class SingleLineWithNoiseResults(Base, BaseResults):
    pass


class StationaryThenMoveTest(Base, BaseTest):
    start_x = Column(Float)
    start_y = Column(Float)
    end_x = Column(Float)
    end_y = Column(Float)

    finger_size = Column(Float)
    swipe_speed = Column(Float)


class StationaryThenMoveResults(Base, BaseResults):
    pass


class StationaryWithNoiseTest(Base, BaseTest):
    tap_x = Column(Float)
    tap_y = Column(Float)

    finger_size = Column(Float)
    frequency = Column(Float)


class StationaryWithNoiseResults(Base, BaseResults):
    pass


class StationaryWithTapsTest(Base, BaseTest):
    center_x = Column(Float)
    center_y = Column(Float)

    finger_size = Column(Float)
    separation = Column(Float)
    start_azimuth = Column(Float)
    end_azimuth = Column(Float)

    tap_azimuth_step = Column(Float)


class StationaryWithTapsResults(Base, BaseResults):
    pass


class SwipeTest(Base, BaseTest):
    # For multi-finger lines, these are the coordinates of the primary finger (left-most with
    # zero azimuth)
    start_x = Column(Float)
    start_y = Column(Float)
    end_x = Column(Float)
    end_y = Column(Float)

    num_fingers = Column(Integer)
    finger_size = Column(Float)
    swipe_speed = Column(Float)
    separation = Column(Float)
    azimuth = Column(Float)


class SwipeResults(Base, BaseResults):
    pass


class TapTest(Base, BaseTest):
    # For multi-finger taps, these are the coordinates of the primary finger (left-most with
    # zero azimuth)
    tap_x = Column(Float)
    tap_y = Column(Float)

    separation = Column(Float)
    azimuth = Column(Float)
    num_fingers = Column(Integer)
    finger_size = Column(Float)
    edge_width = Column(Float)


class TapResults(Base, BaseResults):
    pass
