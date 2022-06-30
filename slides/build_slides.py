#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import lxml.etree as ET
from pathlib import Path
import subprocess
import sys

# use pretext xsl from the install of the pretext-cli
from pretext.static import core_xsl

if len(sys.argv) != 2:
    print("Need source ptx:", sys.argv)
    quit()

# source file = blah.ptx
sourceFile = Path(sys.argv[1])
if sourceFile.suffix != ".ptx":
    print("Need sourcefile ptx:", sourceFile)
    quit()

# source stem = blah
sourceStem = sourceFile.stem

html_out_file = sourceStem + ".html"

print("Reading in XSL transforms")
pretext_xsl_dir = Path(core_xsl(as_path=True))
xsltFile = pretext_xsl_dir / "pretext-revealjs.xsl"
xslt = ET.parse(xsltFile)
transform = ET.XSLT(xslt)

print("Reading in source file")
# read in the source file
src = ET.parse(sourceFile)
# and its xincludes
try:
    src.xinclude()
except Exception as err:
    print(">>> ERROR <<< ")
    print(err)
    exit(1)

# # build parameters as dict
param = {
    "publisher": "'./publication.ptx'",  # this loads in the publisher options
}

print("Transform the source")
htmlSource = transform(src, **param)

print("Error log:")
print(transform.error_log)

print("Writing HTML")
with open(html_out_file, "w") as fh:
    fh.write(str(htmlSource))
print("HTML written")

# comment out "quit" below if you want to build the pdfs too
# uses 'decktape' to covert reveal.js to pdf
# assumes that you have working pretext-cli install and
# also decktape installed through npm as per instructions here
# https://github.com/astefanutti/decktape
quit()

# run NPM to get the bin path for decktape
try:
    npm_bin_output = subprocess.check_output(["npm", "bin"]).decode()
    decktape_path = Path(npm_bin_output.strip()) / "decktape"
except subprocess.CalledProcessError as err:
    print(f"Something went wrong trying to call find npm and decktape - {err}")
    print("Stopping without PDF conversion")
    quit()

# some directory for pdf output
pdf_dir = Path("pdf_out")
pdf_dir.mkdir(exist_ok=True)
pdf_out_file = pdf_dir / (sourceStem + ".pdf")

print("Converting to PDF")
subprocess.run(
    [
        decktape_path,
        "-s",
        "1920x1080",
        html_out_file,
        pdf_out_file,
    ]
)
