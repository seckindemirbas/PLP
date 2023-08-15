#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import lxml.etree as ET
from pathlib import Path
import subprocess
import sys

def insert_user_css(filename, css_file_name):
    # insert link to user css at the end of the head.
    # this is a bit hacky but works
    lines = []
    # read in lines
    with open(filename, "r") as fh:
        for line in fh:
            # if the line is the end of the header put in user css link
            if line.find("</head>") != -1:
                lines.append(
                    f"""
                <link href="{css_file_name}" rel="stylesheet"/>
                """
                )
            lines.append(line)
    # now write the file back with the new content.
    with open(filename, "w") as fh:
        for line in lines:
            fh.write(line)


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

# use this if you have a pretext-cli install
pretext_xsl_dir = Path().home()/".ptx"/"xsl"
# else set to path to your local pretext install



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

# now insert a link to user-css to style the resulting html more
insert_user_css(html_out_file, "plp_styling.css")


# comment out "quit" below if you want to build the pdfs too
# uses 'decktape' to covert reveal.js to pdf
# assumes that you have working pretext-cli install and
# also decktape installed through npm as per instructions here
# https://github.com/astefanutti/decktape
# quit()

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
