# .. Copyright (C) 2012-2022 Bryan A. Jones.
#
#    This file is part of CodeChat.
#
#    CodeChat is free software: you can redistribute it and/or modify it under
#    the terms of the GNU General Public License as published by the Free
#    Software Foundation, either version 3 of the License, or (at your option)
#    any later version.
#
#    CodeChat is distributed in the hope that it will be useful, but WITHOUT ANY
#    WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#    FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
#    details.
#
#    You should have received a copy of the GNU General Public License along
#    with CodeChat.  If not, see <http://www.gnu.org/licenses/>.
#
# ********************************************************
# |docname| - a module to translate source code to PreTeXt
# ********************************************************
# The API_ lists two functions which convert source code into `PreTeXt <https://pretextbook.org/>`_. It relies on `source_lexer` to classify the source as code or comment, then `_generate_pretext`_ to convert this to PreTeXt.
#
# .. contents::
#
# Imports
# =======
# These are listed in the order prescribed by `PEP 8
# <http://www.python.org/dev/peps/pep-0008/#imports>`_.
#
# Standard library
# ----------------
import html
from io import StringIO
import re

# Third-party imports
# -------------------
# None.

# Local application imports
# -------------------------
from .SourceClassifier import source_lexer, get_lexer, _debug_print


# API
# ===
# The following routines provide easy access to the core functionality of this
# module.
#
# .. _code_to_pretext_string:
#
# code_to_pretext_string
# -----------------------
# This function converts a string containing source code to PreTeXt, preserving all indentations of both source code and comments. To do so, the comment characters are stripped from CodeChat-formatted comments and all code is placed inside fenced code blocks.
def code_to_pretext_string(
    # _`code_str`: the code to translate to PreTeXt.
    code_str,
    # See `options <options>`.
    **options,
):
    # Use a StringIO to capture writes into a string.
    output_ptx = StringIO()
    ast_syntax_error, classified_lines = source_lexer(
        code_str, get_lexer(code=code_str, **options)
    )
    # Remove the newline from a syntax error, so that source line numbers match exactly with the lines output by this function.
    if ast_syntax_error:
        output_ptx.write(
            f"<warning>CodeChat parse error: {html.escape(ast_syntax_error, False)[:-1]}</warning>"
        )
    output_ptx.write("<program><input>")
    _generate_pretext(classified_lines, output_ptx)
    output_ptx.write("</input></program>")
    return output_ptx.getvalue()


# .. _code_to_pretext_file:
#
# code_to_pretext_file
# ---------------------
# Convert a source file to a PreTeXt file.
def code_to_pretext_file(
    # .. _source_path:
    #
    # Path to a source code file to process.
    source_path,
    # Path to a destination PreTeXt file to create. It will be overwritten if it
    # already exists. If not specified, it is ``source_path.ptx``.
    pt_path=None,
    # .. _input_encoding:
    #
    # Encoding to use for the input file. The default of None detects the
    # encoding of the input file.
    input_encoding="utf-8",
    # .. _output_encoding:
    #
    # Encoding to use for the output file.
    output_encoding="utf-8",
    # See `options <options>`.
    **options,
):
    # Provide a default ``rst_path``.
    if not pt_path:
        pt_path = source_path + ".ptx"
    with open(source_path, encoding=input_encoding) as fi:
        code_str = fi.read()
    # If not already present, provide the filename of the source to help in identifying a lexer.
    options.setdefault("filename", source_path)
    rst = code_to_pretext_string(code_str, **options)
    with open(pt_path, "w", encoding=output_encoding) as fo:
        fo.write(rst)


# Converting classified code to PreTeXt
# =====================================
# A regex to match part of an opening XML tag in a comment context, allowing for leading whitespace. At this time, a comment must always begin with a ``<p>`` tag and end with a closing ``</p>`` tag.
xml_partial_opening_tag_regex = re.compile(r"^\s*<p\s*>")
xml_closing_tag_regex = re.compile(r"</p\s*>\s*$")


# _generate_pretext
# -----------------
# Generate PreTeXt from the classified code. To do this, create a state machine, where current_type defines the state. When the state changes, exit the previous state, then enter the new state.
def _generate_pretext(
    # An iterable of (type, string) pairs, one per line.
    classified_lines,
    # .. _out_file:
    #
    # A file-like output to which the pretext source is written.
    out_file,
):
    # Determine the number of characters produced when a newline is written.
    newline_chars = out_file.write("\n")
    # Undo this write.
    out_file.seek(out_file.tell() - newline_chars, 0)

    # Keep track of the current type. Begin with neither comment nor code.
    current_type = -2

    # Keep track of the current line number.
    line = 1

    for type_, string in classified_lines:
        _debug_print(
            "type_ = {}, line = {}, string = {}\n".format(type_, line, [string])
        )

        # See if there's a change in state.
        if current_type != type_:
            # Exit the current state.
            _exit_state(current_type, string, out_file, newline_chars)

            # Enter the new state.
            #
            # Code state:
            if type_ == -1:
                # Nothing is needed.
                pass
            # Comment state:
            else:
                # Add an opening ``<p>`` if there's no XML tag at the beginning of this string.
                if not re.search(xml_partial_opening_tag_regex, string):
                    string = "<p>" + string

        # Escape characters in code; pass comments through with appropriate leading whitespace.
        out_file.write(
            html.escape(string, False) if type_ == -1 else " " * type_ + string
        )

        # Update the state.
        current_type = type_
        line += 1

    # When done, exit the last state.
    _exit_state(current_type, string, out_file, newline_chars)


# _exit_state
# -----------
# Output text produced when exiting a state. Supports `_generate_pretext`_.
def _exit_state(
    # The type (classification) of the last line.
    type_,
    # One line from the program being translated.
    string,
    # See out_file_.
    out_file,
    # The number of character written by a newline.
    newline_chars,
):
    # Code state: do nothing.
    if type_ == -1:
        pass
    # Comment state: emit a closing ``</p>`` tag if it wasn't provided.
    elif type_ >= 0:
        if not re.search(xml_closing_tag_regex, string):
            # Append it to the end of the string by backing up one character (the existing newline at the end of the current line).
            out_file.seek(out_file.tell() - newline_chars, 0)
            out_file.write("</p>\n")
    # Initial state. Nothing needed.
    else:
        pass
