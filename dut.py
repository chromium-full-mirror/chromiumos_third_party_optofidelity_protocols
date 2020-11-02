# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module holds the data structures used for communication between
Optofidelity DUT software and test software.
"""

from collections import namedtuple

Measurement = namedtuple('Measurement', ['panel_x', 'panel_y', 'pressure',
                                         'finger_id', 'delay', 'time', 'event',
                                         'yaw', 'tilt', 'UNKNOWN'])
Measurement.__new__.__defaults__ = (0.0,) * 3
