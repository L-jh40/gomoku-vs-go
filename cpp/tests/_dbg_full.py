#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Runner v2: instrument Engine to trace stdio handles."""
from __future__ import annotations

import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import diff_forbidden as d  # noqa: E402

_orig_readline = d.Engine.readline


def readline(self):
    line = self.p.stdout.readline()
    if line == "":
        print("!!! EOF on stdout of pid=%s" % self.p.pid, flush=True)
        print("    stdout=%r stderr=%r stdin=%r"
              % (self.p.stdout, self.p.stderr, self.p.stdin), flush=True)
        print("    poll=%r" % (self.p.poll(),), flush=True)
        try:
            out = subprocess.run(["tasklist", "/FI", "PID eq %d" % self.p.pid],
                                 capture_output=True, text=True, timeout=10)
            print("    tasklist: %s" % out.stdout.strip(), flush=True)
        except Exception as e:
            print("    tasklist failed: %r" % (e,), flush=True)
        raise RuntimeError("engine closed its stdout unexpectedly")
    return line.rstrip("\r\n")


d.Engine.readline = readline
sys.exit(d.main())
