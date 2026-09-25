#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Probe v2: faulthandler stack dump on the old harness hang."""
from __future__ import annotations

import faulthandler
import importlib.util
import os
import random
import sys
import time

sys.argv = ["x"]
spec = importlib.util.spec_from_file_location("old_diff", "cpp/tests/_old_diff.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

LOG = open("cpp/tests/_probe2.log", "w", encoding="utf-8")


def log(msg):
    LOG.write("%s %s\n" % (time.strftime("%H:%M:%S"), msg))
    LOG.flush()


# Dump stacks of all threads after 40s and hard-exit.
faulthandler.dump_traceback_later(40, exit=True, file=LOG)

orig_send = m.Engine.send
orig_rl = m.Engine.readline


def send(self, cmd):
    log("send %r" % cmd)
    return orig_send(self, cmd)


def rl(self):
    t0 = time.time()
    line = self.p.stdout.readline()
    log("  rl dt=%.2f line=%r" % (time.time() - t0, line[:16]))
    return line.rstrip("\r\n")


m.Engine.send = send
m.Engine.readline = rl

log("spawning e2")
e2 = m.Engine()
log("spawned pid=%r" % e2.p.pid)
try:
    ok = m.make_undo_test(e2, random.Random(7))
    log("ok %r" % ok)
except Exception as ex:
    log("EXC %r" % (ex,))
log("DONE")
