#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import glob
import subprocess

for fname in sorted(glob.glob("topic*.ptx")):
    print(f"Building {fname}")
    subprocess.run(["python3", "build_slides.py", fname])
