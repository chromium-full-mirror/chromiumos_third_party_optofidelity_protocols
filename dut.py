# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module holds the data structures used for communication between
Optofidelity DUT software and test software.
"""

from collections import namedtuple
from enum import IntEnum

Measurement = namedtuple('Measurement', ['panel_x', 'panel_y', 'pressure',
                                         'finger_id', 'delay', 'time', 'event',
                                         'yaw', 'tilt', 'UNKNOWN',
                                         'touch_major', 'touch_minor',
                                         'tool_type', 'button_pressed'])
Measurement.__new__.__defaults__ = (0.0, 0.0, 0, 0, 0, 0, False)
Axis = namedtuple('Axis', ['min', 'max', 'resolution'])
DUTConfig = namedtuple('DUTConfig', ['client_id', 'x', 'y', 'pressure',
                                     'touch_major', 'touch_minor'])


class Action(IntEnum):
    """ Touch actions"""
    DOWN        = 0
    UP          = 1
    MOVE        = 2
    CANCEL      = 3
    HOVER_MOVE  = 7
    HOVER_DOWN  = 9
    HOVER_UP    = 10
