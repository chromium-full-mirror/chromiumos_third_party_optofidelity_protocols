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
import traceback

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text, DECIMAL, VARCHAR, BOOLEAN, BLOB
from sqlalchemy.orm import relation, backref, sessionmaker
from sqlalchemy.ext.declarative import declarative_base, declared_attr
from sqlalchemy import create_engine
from sqlalchemy import event
import json
import time
import sqlite3
from scriptpath import join_script_root_directory
import logging

Base = declarative_base()

logger = logging.getLogger(__name__)

def on_connect(conn, record):
    conn.execute('pragma foreign_keys=ON')

def saveLastPath(path):
    f = open(join_script_root_directory('config.json'), 'w')
    f.write(json.dumps({"lastDB": path}))
    f.close()

def create_sqlite_indices(database_file, indices):
    """ Creates indices to the SQLite database """
    db = sqlite3.connect(database_file)

    curindices = get_current_indices(db)

    for index_values in indices:
        # For some reason curindices has '_fkey' appended to names

        index_name = index_values[0] + '_fkey'

        if index_name not in curindices:
            logging.info("Creating database index %s" % index_name)
            create_index(db, index_name, index_values)

    db.close()

def get_current_indices(database):
    """ Returns an array of currently declared indices in the database """

    c = database.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
    indices = [r[0] for r in c.fetchall()]

    return indices

def create_index(database, index_name, index_values):
    """ Creates the specified index in the database """
    database.execute('CREATE INDEX IF NOT EXISTS %s ON %s ( %s )' % (index_name, index_values[0], index_values[1]))

class ResultDatabase:

    def __init__(self, filename, test_case_modules):
        self.db = None
        self.session = None
        self.dbpath = None

        # curved line test contains different tests
        # define new ones here
        self.CURVED_LINE_TESTS = {1: "Handwriting"}

        self.CURVED_ANALYSIS_TYPES = {1: ["path_accuracy",
                                          "curved_path_linearity",
                                          "reported_pos_proximity_to_robot_pos",
                                          "path_length_comparison"]
                                      }

        self.initialize(filename, test_case_modules)
        saveLastPath(filename)

    def initialize(self, filename, test_case_modules):

        self.dbpath = filename
        self.db = create_engine('sqlite:///' + filename)
        event.listen(self.db, 'connect', on_connect)
        self.session = sessionmaker(bind=self.db, autoflush=False)
        Base.metadata.create_all(self.db)

        # TODO: Some explanation is in order.
        # These are database indices for various test and test result tables.
        indices = [
            ['dut_parameters', 'dut_id'],
            ['test_item', 'testsession_id']
            ]

        for test in BaseTest.__subclasses__():
            indices.append((test.__tablename__, 'test_id'))
        for result in BaseResults.__subclasses__():
            indices.append((result.__tablename__, 'gesture_id'))

        # Insert database indices defined by test case modules.
        # TODO (b/148627899): Remove when legacy test cases are purged
        for module in test_case_modules:
            if not hasattr(module, 'DB_TABLE_INDICES'):
                continue

            for module_indices in module.DB_TABLE_INDICES:
                indices.append(module_indices)

        create_sqlite_indices(filename, indices)

        # Check if ResultDatabase already contains test types below.
        try:
            # TODO: It would be nice if these test type names were defined in respective test case Python files.
            # However, do we wan't the ID values to be unique if test case order or number changes? Perhaps hash from name?
            # Note: TestType integer IDs must match the ones used in analysis.
            session = self.session()
            session.add( TestType( 0, 'One Finger Tap Test' ) )
            session.add( TestType( 1, 'One Finger Swipe Test' ) )
            session.add( TestType( 2, 'One Finger First Contact Latency Test' ) )
            session.add( TestType( 5, 'MultiFinger Swipe Test'))
            session.add( TestType( 8, 'MultiFinger Tap Test'))
            session.add( TestType( 9, 'One Finger Stationary Jitter'))
            session.add( TestType( 10, 'One Finger Tap Repeatability'))
            session.add( TestType( 11, 'One Finger Stationary Reporting Rate Test'))
            session.add( TestType( 12, 'One Finger Non Stationary Reporting Rate Test'))
            session.add( TestType( 13, 'Linearity Test'))
            session.add( TestType( 14, 'Separation Test'))
            session.add( TestType( 15, 'Grid Accuracy Test'))
            session.add( TestType( 16, 'Stationary Jitter Static Noise Test'))
            session.add( TestType( 17, 'One Finger Tapping Repeatability Test'))
            session.add( TestType( 18, 'Finger Tracking Test'))
            session.add( TestType( 19, 'Finger To Edge Test'))
            session.add( TestType( 20, 'Swipe Test'))
            session.add( TestType( 21, 'Pinch Test'))
            session.add( TestType( 22, 'Tap Test'))
            session.add( TestType( 23, 'Repeated Taps Test'))
            session.add( TestType( 24, 'Stationary Then Move Test'))
            session.add( TestType( 25, 'Drumroll Test'))
            session.add( TestType( 26, 'Compass Test'))
            session.add( TestType( 27, 'Compass With Taps Test'))
            session.add( TestType( 28, 'Stationary With Taps Test'))
            session.commit()
            session.close()
        except:
            # Already created
            pass
        try:
            # Grid accuracy settings
            self.checksetting(
                Setting('max_error_edge', 1.5, 'mm', 'Max error in edge area (not including 4 corners and notch)'))
            self.checksetting(
                Setting('max_error_edge_corner_notch', 2.0, 'mm',
                        'Max error in edge area (including 4 corners and notch'))
            self.checksetting(
                Setting('max_error_center', 1.0, 'mm', 'Max error in center area'))
            self.checksetting(
                Setting('grid_acc_missing_points', 10, '%', 'Max amount of missing points in percents'))

            # Linearity settings
            self.checksetting(
                Setting('max_avg_of_max_errors', 0.75, 'mm',
                        'Maximum allowed max of averages of max linearity errors '))
            self.checksetting(
                Setting('max_rms_error', 0.5, 'mm', 'Maximum allowed rms linearity error'))
            self.checksetting(
                Setting('min_report_rate', 120, 'Hz', 'Minimum reporting rate in active mode'))
            self.checksetting(
                Setting('min_report_rate_noise_inj_single', 120, 'Hz',
                        'Minimum reporting rate with noise injected in active mode at single touch'))
            self.checksetting(
                Setting('min_report_rate_noise_inj_multi', 100, 'Hz',
                        'Minimum reporting rate with noise injected in active mode at multi touch'))
            self.checksetting(
                Setting('max_missing_swipes', 10, '%', 'Maximum amount of missing swipes in percents'))
            self.checksetting(
                Setting('max_broken_lines', 0, 'pcs', 'Maximum amount of broken lines'))
            self.checksetting(
                Setting('max_ghost_fingers', 0, 'pcs', 'Maximum amount of ghost fingers'))
            self.checksetting(Setting('jitter_mask', 10.0, "mm", "Non stationary jitter search mask"))

            # Stationary jitter static noise settings
            self.checksetting(
                Setting('max_stat_jitter_no_noise', 0.5, 'mm', 'Max stationary jitter with no noise injected'))
            self.checksetting(
                Setting('max_stat_jitter_noise', 1.0, 'mm', 'Max stationary jitter with noise injected'))
            self.checksetting(
                Setting('max_noise_test_jitter', 1.0, 'mm', 'Max stationary jitter in static noise test'))
            self.checksetting(
                Setting('jitter_missing_points', 10, '%', 'Max percentage of allowed missing points'))

            # Tapping repeatability settings
            self.checksetting(
                Setting('max_error_edge_down', 1.5, 'mm', 'Maximum repeatability error at the edge on pen down'))
            self.checksetting(
                Setting('max_error_edge_up', 1.5, 'mm', 'Maximum repeatability error at the edge on pen lift-off'))
            self.checksetting(
                Setting('max_error_corner_down', 1.5, 'mm', 'Maximum repeatability error in the corner on pen down'))
            self.checksetting(
                Setting('max_error_corner_up', 1.5, 'mm', 'Maximum repeatability error in the corner on pen lift-off'))
            self.checksetting(
                Setting('max_error_center_down', 1.0, 'mm', 'Maximum repeatability error at the center on pen down'))
            self.checksetting(
                Setting('max_error_center_up', 1.0, 'mm', 'Maximum repeatability error at the center on pen lift-off'))
            self.checksetting(
                Setting('repeatability_missing_points', 10, '%',
                        'Maximum amount of allowed missing points in repeatability'))

            # Legacy settings
            self.checksetting(Setting('maxjitter', 1.0, "mm", "Maximum allowed non stationary jitter"))
            self.checksetting(Setting('maxstationaryjitter', 1.0, "mm", "Maximum allowed stationary jitter"))
            self.checksetting(Setting('maxstationaryjitter_with_noise', 1.0, "mm",
                                      "Maximum allowed stationary jitter with noise source"))
            self.checksetting(Setting('jittermask', 10.0, "mm", "Non stationary jitter search mask"))
            self.checksetting(Setting('maxactiveresponselatency', 25.0, "ms",
                                      "Maximum allowed response latency from an active state for the initial input"))
            self.checksetting(
                Setting('maxidleresponselatency', 50.0, "ms", "Maximum allowed response latency from an idle state"))
            self.checksetting(Setting('minreportingrate', 100.0, "Hz", "Minimum allowed reporting rate"))
            self.checksetting(Setting('maxposerror', 1.0, "mm", "Maximum allowed accuracy error"))
            self.checksetting(Setting('maxmissing', 0.0, "pcs", "Maximum allowed missing inputs"))
            self.checksetting(Setting('maxoffset', 1.0, "mm", "Maximum allowed offset"))
            self.checksetting(Setting('maxseparation', 12.0, "mm",
                                      "Maximum allowed finger separation distance (vertical and horizontal)"))
            self.checksetting(
                Setting('maxdiagseparation', 15.0, "mm", "Maximum allowed finger separation distance (diagonal)"))
            self.checksetting(Setting('minppi', 200.0, "ppi", "Minimum display resolution"))
            self.checksetting(Setting('maxhoveroffset', 1.0, "mm", "Maximum allowed hover offset"))
            self.checksetting(Setting('maxrepeaterror', 1.0, "mm", "Maximum tap repeatability error"))
            self.checksetting(Setting('edgelimit', -1.0, "mm", "Edge area distance from edge in Tap test"))
            self.checksetting(Setting('edgepositioningerror', 1.0, "mm", "Maximum allowed accuracy error in edge area"))
            self.checksetting(Setting('maxedgemissing', 0.0, "pcs", "Maximum allowed missing edge inputs"))
            self.checksetting(Setting('maxmissingswipes', 0.0, "pcs", "Maximum allowed missing swipes in swipe test"))
            self.checksetting(Setting('maxbrokenswipes', 0.0, "pcs", "Maximum allowed broken swipes in linearity test"))
            self.checksetting(Setting('maxghostfingerswipes', 0.0, "pcs",
                                      "Maximum allowed swipes with ghost finger in linearity test"))
            self.checksetting(Setting('maxmissinghover', 0.0, "pcs", "Maximum allowed missing swipes in hover test"))
            self.checksetting(Setting('maxhoverjitter', 1.0, "mm", "Maximum allowed jitter in hover test"))

            # When adding settings, remember to add them to settings.py categories
        except: #IntegrityError:
            logging.info(traceback.format_exc())
            # Already created
            pass

    def changeDatabase(self, path):
        self.initialize(path)
        saveLastPath(path)

    def add( self, data, commit = True, expire_on_commit=True ):
        session = self.session(expire_on_commit=expire_on_commit)
        session.add( data )
        if commit == True:
            self.session_commit(session)
        _id = data.id
        session.close()
        return _id

    def addAll( self, data, commit = True ):
        session = self.session()
        session.add_all( data )
        if commit == True:
            self.session_commit(session)
        session.close()

    def getEngine(self):
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
        while(True):
            try:
                session.commit()
                break
            except sqlite3.OperationalError as e:
                if time.time() - start > max_wait_time:
                    raise e
                else:
                    pass

    def get_test_sessions( self, dbsession=None ):
        if dbsession is None:
            dbsession = self.session()
        try:
            return dbsession.query( TestSession ).all()
        finally:
            dbsession.close()

    def get_test_session( self, session_id ):
        session = self.session()
        try:
            return session.query( TestSession ).filter_by( id=session_id ).first()
        finally:
            session.close()

    def get_TestType( self, type_id ):
        session = self.session()
        try:
            return session.query(TestType).filter_by( id=type_id ).all()
        finally:
            session.close()

    def get_TestTypes( self ):
        session = self.session()
        try:
            return session.query(TestType).all()
        finally:
            session.close()

    def get_programs( self ):
        session = self.session()
        try:
            return session.query( TestSession.program).order_by(TestSession.program)
        finally:
            session.close()

    def get_manufacturers( self, Program ):
        session = self.session()
        try:
            return session.query( TestSession.manufacturer).order_by(TestSession.manufacturer).all()
        finally:
            session.close()

    def checksetting( self, setting ):
        session = self.session()
        dbsetting = session.query(Setting).filter_by(id=setting.id).first()
        if dbsetting is None:
            # Setting does not exist
            session.add(setting)
            self.session_commit(session)
        session.close()

# Define database tables

class TestSession( Base ):

# TestSession is constant to all test cases

    __tablename__ = 'test_session'

    id = Column( Integer, primary_key=True )
    operator = Column( String )
    starttime = Column( String )
    endtime = Column( String )
    invalid = Column( Boolean )
    notes = Column( String )
    tnt_version = Column( String )
    tppt_version = Column( String )
    station_id = Column( String )

class TestDUT( Base ):

    # A DUT that is tested in one or multiple test sessions and referenced to in Test Items
    __tablename__ = 'test_dut'
    id = Column( Integer, primary_key=True )

    # Dut parameters
    program = Column( String )
    manufacturer = Column( String )
    batch = Column( String )
    serial = Column( String )
    sample_id = Column( String )
    svg_data = Column( BLOB )


class TestType( Base ):

    #Device digitizer touch test types stored here

    __tablename__ = 'test_type'

    id = Column( Integer, primary_key = True )
    name = Column( String )

    def __init__( self, id, name ):
        self.id = id
        self.name = name

class TestItem( Base ):

    #A single test related to device digitizer touch is defined here
    __tablename__ = 'test_item'

    id = Column( Integer, primary_key= True )
    testsession_id = Column( Integer, ForeignKey('test_session.id', ondelete='CASCADE'), nullable=False )
    testsession = relation( TestSession, backref = backref('test_items', order_by =  id) )
    dut_id = Column( Integer, ForeignKey('test_dut.id'), nullable=False )
    dut = relation( TestDUT, backref = backref('test_items', order_by =  id) )
    starttime = Column( String )
    endtime = Column( String )
    slot_id = Column( Integer )
    finger_type = Column( String )
    invalid = Column( Boolean )
    kmsg_log = Column( Text )
    testtype_id = Column( Integer, ForeignKey('test_type.id', ondelete='CASCADE'), nullable=False )
    type = relation( TestType, backref = backref('test_items', order_by = id) )

class DutParameters( Base ):

    #DUT parameters are defined here
    __tablename__ = 'dut_parameters'

    id = Column( Integer, primary_key = True )
    dut_id = Column( Integer, ForeignKey('test_dut.id', ondelete='CASCADE'), nullable=False )
    dut = relation(TestDUT, backref = backref('dut_parameters', order_by = id ) )
    name = Column( String )
    valueFloat = Column( Float )
    valueString = Column( String )
    isFloat = Column( Boolean )

class Setting(Base):

    __tablename__ = 'settings'
    id = Column(String,primary_key = True)
    value = Column(Float,nullable=False)
    unit = Column(String)
    desc = Column(String)
    def __init__(self,id,value,unit,desc):
        self.id = id
        self.value = value
        self.unit = unit
        self.desc = desc


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

    finger_size = Column(Float)


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


class StationaryThenMoveTest(Base, BaseTest):
    start_x = Column(Float)
    start_y = Column(Float)
    end_x = Column(Float)
    end_y = Column(Float)

    finger_size = Column(Float)
    swipe_speed = Column(Float)


class StationaryThenMoveResults(Base, BaseResults):
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
