#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Probe the OLD harness's make/undo hang: log every readline with timing."""
from __future__ import annotations

import importlib.util
import random
import sys
import time

sys.argv = ["x"]
spec = importlib.util.spec_from_file_location("old_diff", "cpp/tests/_old_diff.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

LOG = open("cpp/tests/_probe.log", "w", encoding="utf-8")


def log(msg):
    LOG.write(msg + "\n")
    LOG.flush()


orig = m.Engine.readline


def rl(self):
    t0 = time.time()
    line = self.p.stdout.readline()
    dt = time.time() - t0
    log("  [rl dt=%.2f line=%r poll=%r]" % (dt, line[:20], self.p.poll()))
    if line == "":
        log("  EOF pid=%r rc=%r stdin_closed=%s stderr_closed=%s"
            % (self.p.pid, self.p.poll(), self.p.stdin.closed, self.p.stderr.closed))
        # is the process alive?
        try:
            rc = self.p.wait(timeout=5)
            log("  wait rc=%r hex=%s" % (rc, hex(rc & 0xFFFFFFFF)))
        except Exception as e:
            log("  wait failed %r" % (e,))
            try:
                err = self.p.stderr.read()
                log("  stderr=%r" % (err,))
            except Exception as e2:
                log("  stderr read failed %r" % (e2,))
        raise RuntimeError("eof")
    return line.rstrip("\r\n")


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
LOG.close()
