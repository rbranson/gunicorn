# -*- coding: utf-8 -
#
# This file is part of gunicorn released under the MIT license.
# See the NOTICE for more information.

import os
import time

from gunicorn import util
from multiprocessing import Value

INITIAL_TICKER_VALUE = 0
SLEEP_TICKER_VALUE = -1
WRAP_TICKER_AT = 2 ** 30

#
# Implements a cross-process Heartbeat mechanism to allow one process to
# determine if another process has stopped responding or working.
#
class Heartbeat(object):
    def __init__(self):
        # The cross-process shared memory unsigned long value we will share
        self._ticker = Value("l", INITIAL_TICKER_VALUE)
        self._saw()

    # Perform a heartbeat
    def notify(self):
        self._ticker.value += 1

        # Wrap the ticker back around to zero once we hit a safe max value
        if self._ticker.value == WRAP_TICKER_AT:
            self._ticker.value = 0

    # Returns the last timestamp when the current process saw a heartbeat
    def last_update(self):
        # If the ticker value has changed since we last checked it,
        # bump the timestamp.
        if self._ticker.value == SLEEP_TICKER_VALUE or self._last_seen != self._ticker.value:
            self._saw()

        return self._last_updated_ts 

    # Sets the heartbeat into a sleep state so that last_update will always
    # respond with the current time. This is useful if you know what you're
    # monitoring is in a "safe" sleep state like waiting for a blocking
    # accept()
    def sleep(self):
        self._ticker.value = SLEEP_TICKER_VALUE 

    def _saw(self):
        self._last_seen = self._ticker.value
        self._last_updated_ts = time.time()
