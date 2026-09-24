#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Runner: run diff_forbidden.main() with Engine.readline instrumented."""
from __future__ import annotations

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import diff_forbidden as d  # noqa: E402


def readline(self):
    line = self.p.stdout.readline()
    if line == "":
        rc = self.p.poll()
        try:
            err = self.p.stderr.read()
        except Exception as e:
            err = repr(e)
        print("!!! ENGINE CLOSED stdout: pid=%s rc=%s (hex=%s) stderr=%r"
              % (self.p.pid, rc, hex(rc & 0xFFFFFFFF) if rc is not None else None, err),
              flush=True)
        raise RuntimeError("engine closed its stdout unexpectedly")
    return line.rstrip("\r\n")


d.Engine.readline = readline
sys.exit(d.main())
