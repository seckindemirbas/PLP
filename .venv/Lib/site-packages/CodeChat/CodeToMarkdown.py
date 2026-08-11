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
# *********************************************************
# |docname| - a module to translate source code to Markdown
# *********************************************************
# The API_ lists two functions which convert source code into Markdown. It relies on `source_lexer` to classify the source as code or comment, then `_generate_markdown`_ to convert this to Markdown. To convert this output to HTML using `Markdown <https://python-markdown.github.io/>`_ or `CommonMark <https://github.com/rtfd/CommonMark-py#commonmark-py>`_:
#
# .. code-block:: Python
#   :linenos:
#
#   from CodeChat.CodeToMarkdown import code_to_markdown_string
#   import markdown
#   import CommonMark
#
#   # Translate code to Markdown.
#   md_str = code_to_markdown_string("# Testing, 1, 2, 3.")
#   # Render it, using two different Markdown implementations.
#   print(markdown.markdown(s))
#   print(CommonMark.commonmark(s))
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
from io import StringIO

# Third-party imports
# -------------------
# None.

# Local application imports
# -------------------------
from .SourceClassifier import source_lexer, get_lexer, _debug_print, codechat_style


# API
# ===
# The following routines provide easy access to the core functionality of this
# module.
#
# .. _code_to_markdown_string:
#
# code_to_markdown_string
# -----------------------
# This function converts a string containing source code to Markdown, preserving all indentations of both source code and comments. To do so, the comment characters are stripped from CodeChat-formatted comments and all code is placed inside fenced code blocks.
def code_to_markdown_string(
    # _`code_str`: the code to translate to markdown.
    code_str,
    # See `options <options>`.
    **options
):
    # Use a StringIO to capture writes into a string.
    output_md = StringIO()
    # Include a header containing some `CodeChat style`.
    output_md.write(codechat_style + "\n\n")
    ast_syntax_error, classified_lines = source_lexer(
        code_str, get_lexer(code=code_str, **options)
    )
    if ast_syntax_error:
        output_md.write("# Error\n{}\n".format(ast_syntax_error))
    _generate_markdown(classified_lines, output_md)
    return output_md.getvalue()


# .. _code_to_markdown_file:
#
# code_to_markdown_file
# ---------------------
# Convert a source file to a Markdown file.
def code_to_markdown_file(
    # .. _source_path:
    #
    # Path to a source code file to process.
    source_path,
    # Path to a destination Markdown file to create. It will be overwritten if it
    # already exists. If not specified, it is ``source_path.md``.
    md_path=None,
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
    **options
):
    # Provide a default ``rst_path``.
    if not md_path:
        md_path = source_path + ".md"
    with open(source_path, encoding=input_encoding) as fi:
        code_str = fi.read()
    # If not already present, provide the filename of the source to help in identifying a lexer.
    options.setdefault("filename", source_path)
    rst = code_to_markdown_string(code_str, **options)
    with open(md_path, "w", encoding=output_encoding) as fo:
        fo.write(rst)


# Converting classified code to markdown
# ======================================
# The fence used for a `fenced code block <http://spec.commonmark.org/0.27/#fenced-code-blocks>`_. We hope the code doesn't contain this.
_fence = "`" * 100


# _generate_markdown
# ------------------
# Generate markdown from the classified code. To do this, create a state machine,
# where current_type defines the state. When the state changes, exit the
# previous state (output a closing fence or closing ``</div>``, then enter the
# new state (output a fenced code block or an opening ``<div style=...>``.
def _generate_markdown(
    # An iterable of (type, string) pairs, one per line.
    classified_lines,
    # .. _out_file:
    #
    # A file-like output to which the markdown text is written.
    out_file,
):
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
            _exit_state(current_type, out_file)

            # Enter the new state.
            #
            # Code state: emit the beginning of a fenced block.
            if type_ == -1:
                out_file.write(_fence + "\n")
            # Comment state: emit an opening indent for non-zero indents.
            else:
                # Add an indent if needed.
                if type_ > 0:
                    out_file.write(
                        '\n<div class="CodeChat-indent" style="margin-left:{}em;">\n\n'.format(
                            0.5 * type_
                        )
                    )

        out_file.write(string)

        # Update the state.
        current_type = type_
        line += 1

    # When done, exit the last state.
    _exit_state(current_type, out_file)


# _exit_state
# -----------
# Output text produced when exiting a state. Supports `_generate_markdown`_.
def _exit_state(
    # The type (classification) of the last line.
    type_,
    # See out_file_.
    out_file,
):
    # Code state: emit an ending fence.
    if type_ == -1:
        out_file.write(_fence + "\n")
    # Comment state: emit a closing indent.
    elif type_ > 0:
        out_file.write("\n</div>\n\n")
    # Initial state or non-indented comment. Nothing needed.
    else:
        pass
