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
# *****************************************************
# |docname| - a module to translate reST to source code
# *****************************************************
#
#
# .. contents::
#   :local:
#
# Imports
# =======
# These are listed in the order prescribed by `PEP 8
# <http://www.python.org/dev/peps/pep-0008/#imports>`_.
#
# Third-party imports
# -------------------
# For the docutils default style sheet and template
from docutils import io
from pygments.lexers import find_lexer_class
from lxml import html

# Local application imports
# -------------------------
from .CommentDelimiterInfo import COMMENT_DELIMITER_INFO
from .CodeToRest import rest_codechat_style


# Supporting Functions
# ====================
# This section covers all functions that support the main two functions rest_to_code_string_
# and rest_to_code_file_.
#
# _`find_file_ext`: Find the file extension needed, given the language name
def find_file_ext(
    # See lang_.
    lang,
):
    if lang in COMMENT_DELIMITER_INFO:
        # `find_lexer_class <http://pygments.org/docs/api/#pygments.lexers.find_lexer_class>`_
        # operates on the `name <http://pygments.org/docs/api/#pygments.lexer.Lexer.name>`_
        # which is different from the `alias <http://pygments.org/docs/api/#pygments.lexer.Lexer.aliases>`_
        # . The name is an attribute of every lexer class
        lexer_class = find_lexer_class(lang)
        # This grabs the first `filename <http://pygments.org/docs/api/#pygments.lexer.Lexer.filenames>`_.
        file_ext_raw = lexer_class.filenames[0]
        # Use only the ``.py`` part of ``*.py`` and similar.
        file_ext_list = file_ext_raw.split("*", 1)
        file_ext = file_ext_list[-1]
        return file_ext
    else:
        return None


# |
#
# _`language_comment_type`: Allows the use of languages that have only inline comments or only block comments
# Checks to make sure the comment type is available and returns that information
def language_comment_type(
    # | _`comment_delimiters`: This is the Value in the dictionary found in :doc:`CommentDelimiterInfo.py`
    # | Ex: ``( '#',      '"""',          '"""')`` for the key ``'Python'``
    # | and ``( '//',     '/*',            '*/')`` for the key ``'C'``
    comment_delimiters,
):
    # If the language supports inline comments, index zero will have a sequence containing a non-empty string as its first element.
    # If the language supports block comments, index one will have a non-empty string.
    return [bool(comment_delimiters[0][0]), bool(comment_delimiters[1])]


# |
#
# _`formulate_comment`:Tells the program whether to make a block comment or an inline comment.
# Number of lines required for the block comment to activate is currently `10,000 consecutive comments
# <number_consecutive_comments_>`_.
# Block comments also activate if the language has no inline comments.
# Inline comments also activate if the language has no block comments.
def formulate_comment(
    # _`line`: This is a string of reST that will be turned into a comment by placing
    # the correct `comment delimiters <comment_delimiters_>`_ in the correct places.
    line,
    # See lang_.
    lang,
    # _`is_block_comment`: This is a Boolean value that tells the program whether to make line_ into
    # an inline comment or a block comment.
    # This might be overruled if the `language <lang_>`_ does not support the wanted type of comment.
    is_block_comment,
    # _`position`: This variable is an integer, and when paired with `line_counter`_, it allows block
    # comments to be reformatted. The integer starts at the same value as `line_counter`_ and is
    # decremented by one for each line that is written to the string. Once it reaches ``0``, the `end
    # comment delimiter <comment_delimiters>`_ is placed at the end of the line.
    position,
    # _`line_counter`: This variable is an integer. It is the number of lines that exist in this block
    # comment. It remains constant as `position`_ decrements. It is also used to check to see if there
    # are `enough lines <number_consecutive_comments>`_ to be considered a block comment.
    line_counter,
):
    # Grab the comment delimiters for the given language
    comment_delimiters = COMMENT_DELIMITER_INFO[lang]
    # Check to see what kinds of comments the language supports
    has_inline_comment, has_block_comment = language_comment_type(comment_delimiters)
    # Create an inline comment
    if (not is_block_comment and has_inline_comment) or (
        is_block_comment and not has_block_comment
    ):
        # Stops the whole program if there is no inline comment delimiter and it is asking to use an inline comment.
        assert has_inline_comment
        # Formulates an inline comment
        return "{} {}\n".format(comment_delimiters[0][0], line)
    # Create a block comment
    else:
        if not is_block_comment:
            line_counter = None
        return formulate_block_comment(line, comment_delimiters, position, line_counter)


# |
#
# _`formulate_block_comment`: Formulates a block comment one line at a time.
def formulate_block_comment(
    # See line_.
    line,
    # See comment_delimiters_.
    comment_delimiters,
    # See position_.
    position,
    # See line_counter_.
    line_counter,
):
    # This covers the case that the language does not support inline comments.
    # It places block comment delimiters around a single line to give an inline effect
    # There is no added space between the end of the comment and the end delimiter because this
    # space is not taken out in the Code to reST translation. If a space is added, it is no
    # longer round trip stable. (It adds a space every time it is translated.)
    if line_counter is None:
        f = "{} {}{}\n".format(comment_delimiters[1], line, comment_delimiters[2])
    # This is the regular block comment case.
    else:
        # It places the open comment delimiter in front of the first line of the comment,
        if position == line_counter:
            f = "{} {}\n".format(comment_delimiters[1], line)
        # It places a ``' * '`` in front of every other line, including the last line in the comment
        # for consistency and visual appeal.
        elif position > 0:
            f = " * " + line + "\n"
        # It places the closing comment delimiter at the end of the last line of the comment.
        else:
            f = " * {}{}\n".format(line, comment_delimiters[2])

    return f


# Core Functions
# ==============
# This section contains the main two functions rest_to_code_string_
# and rest_to_code_file_.
# |
#
# _`rest_to_code_file`: This function uses rest_to_code_string_ to convert a reST file into
# another language. Inputs a reST file, outputs a code file.
def rest_to_code_file(
    # _`lang`: Specify the language that the reST will be translated into. This is the key to
    # the dictionary found in :doc:`CommentDelimiterInfo.py`
    # Ex: ``'Python'`` or ``'C'``
    lang,
    # _`source_rst_path`: Path to a source reST file to process.
    source_rst_path,
    # _`out_path`:Path to a destination code file to create. It will be overwritten if it
    # already exists. If out_path_ is None, the output path will be the source_rst_path_
    # but with the correct file extension for the given lang_
    out_path=None,
    # _`input_encoding`: Encoding to use for the input file. The default of None detects the encoding
    # of the input file.
    input_encoding=None,
    # _`output_encoding`: Encoding to use for the output file.
    output_encoding="utf-8",
):
    if out_path is None:
        # Find the file extension of the given language.
        file_ext = find_file_ext(lang)
        # Obtain the file path without the ``.rst`` extension.
        file_name_list = source_rst_path.rsplit(".", 1)
        file_name = file_name_list[0]
        # Place the file extension on the file path.
        out_path = "{}{}".format(file_name, file_ext)

    # Use docutil's I/O classes to better handle and sniff encodings.
    #
    # Note: both these classes automatically close themselves after a
    # read or write.
    fi = io.FileInput(source_path=source_rst_path, encoding=input_encoding)
    fo = io.FileOutput(destination_path=out_path, encoding=output_encoding)
    # Gather the entire file into a singe string for easy parsing.
    rest_str = fi.read()
    # Convert the string of reST to code.
    code = rest_to_code_string(rest_str, lang)
    # Write the code to the output file.
    fo.write(code)


# Remove the `CodeChat style` from the beginning of the given reST if it's present.
def remove_codechat_style(rest):
    # If the rest begins with the `CodeChat style`,
    if rest.startswith(rest_codechat_style):
        # Snip it off.
        return rest[len(rest_codechat_style) :]
    else:
        return rest


# |
#
# _`rest_to_code_string`: Take string of reST as input, returns a string of code. The string is
# separated into lines and fed through the conversion one line at a time.
def rest_to_code_string(
    # _`rest_str`: The string of reST that will get converted into code.
    # This string is generally multiple lines. The program separates and processes all the lines it is given.
    rest_str,
    # See lang_.
    lang,
):
    boolean = False
    i = 0
    # This replaces all tabs with four spaces. This is put into place to
    # maintain a consistent translation and promote healthy habits.
    rest_str = rest_str.replace("\t", "    ")
    rest_str = remove_codechat_style(rest_str)
    # Split the reST string into lines. These are compiled into the line_list.
    line_list = rest_str.split("\n")
    string_out = ""
    # While there are still lines left, convert them.
    while i < len(line_list):
        # This try/except pair is put in place to catch unexpected input.
        # If the try doesn't work, it checks to see if it is even valid reST input.
        try:
            line_list[i + 1]
            # This is translation for regular code, not comments
            if line_list[i + 1] == ".. fenced-code::":
                # Makes sure that the lines that are supposed to be there are there.
                if line_list[i + 2] != "" or line_list[i + 3] != " Beginning fence":
                    # See Boolean_.
                    boolean = True
                    break
                i += 4
                while line_list[i] != " Ending fence":
                    # Take the front space off
                    s = line_list[i].split(" ", 1)
                    f = s[1] + "\n"
                    # Add the line of code to the output string.
                    string_out += f
                    i += 1
                try:
                    # skips over the added code not including the setline part of the code.
                    # Makes sure that the lines that are supposed to be there are there.
                    if (
                        line_list[i + 1] != ""
                        or line_list[i + 2] != ".."
                        or line_list[i + 3] != ""
                    ):
                        # See Boolean_.
                        boolean = True
                        break
                    i += 4
                # this exception catches the case that the file ends with code rather than a comment
                except Exception:
                    # Makes sure that the lines that are supposed to be there are there.
                    if (
                        line_list[i + 1] != ""
                        or line_list[i + 2] != ".."
                        or line_list[i + 3] != ""
                    ):
                        # See Boolean_.
                        boolean = True
                        break
                    i += 3

            # This is to find the ``<div>`` comments and turn them into comments.
            elif line_list[i + 1] == ".. raw:: html":
                # Makes sure that the lines that are supposed to be there are there.
                if line_list[i + 2] != "" or not line_list[i + 3].startswith(
                    ' <div class="CodeChat-indent" style="margin-left'
                ):
                    # See Boolean_.
                    boolean = True
                    break
                # Used to control the line number of the document
                i += 3
                # Splits the line into ``' <div style="margin-left'`` and ``'{size}em;">'``
                s = line_list[i].split(":", 1)
                # Splits ``'{size}em;">'`` into ``'{size}'`` and ``'m;">'``
                s2 = s[1].split("e", 1)
                # Turns ``'{size}'`` into a number of divs. Ex. ``1.0`` or ``3.5``
                size = float(s2[0])
                # Gets the number of spaces needed to put the comment(s) back where it was.
                # Also, needs to be ``int()`` in order to work in the for loop. size starts out as a float.
                size = int(size * 2)

                # Makes sure that the lines that are supposed to be there are there.
                if (
                    line_list[i + 1] != ""
                    or line_list[i + 2] != ""
                    or line_list[i + 3][0:13] != ".. set-line::"
                    or line_list[i + 4] != ""
                    or line_list[i + 5] != ".."
                    or line_list[i + 6] != ""
                ):
                    # See Boolean_.
                    boolean = True
                    break
                # Skips over the added code including the setline part of the code.
                i += 7

                while line_list[i + 1] != ".. raw:: html":
                    spaces = ""
                    for index in range(size):
                        spaces += " "
                    # All ``<div>`` comments are considered to be inline comments.
                    s = formulate_comment(line_list[i], lang, False, 0, None)
                    f = spaces + s
                    string_out += f
                    i += 1

                # Makes sure that the lines that are supposed to be there are there.
                if (
                    line_list[i + 2] != ""
                    or line_list[i + 3] != " </div>"
                    or line_list[i + 4] != ""
                    or line_list[i + 5] != ".."
                    or line_list[i + 6] != ""
                ):
                    # See Boolean_.
                    boolean = True
                    break
                # skips over the added code
                i += 7

            #
            elif line_list[i + 1][0:13] == ".. set-line::":
                # Makes sure that the lines that are supposed to be there are there.
                if (
                    line_list[i + 2] != ""
                    or line_list[i + 3] != ".."
                    or line_list[i + 4] != ""
                ):
                    # See Boolean_.
                    boolean = True
                    break
                i += 5

                temp_i = i
                line_counter = 0
                # Check to see how many lines the comment has.
                while line_list[temp_i + 1] != ".. fenced-code::":
                    line_counter += 1
                    temp_i += 1
                    try:
                        line_list[temp_i + 1]
                    except Exception:
                        temp_i += 1
                        break
                # .. _number_consecutive_comments:
                #
                # This line sets the lower limit for consecutive comments turning into block comments
                if line_counter < 10000:
                    is_block_comment = False
                    position = 0
                else:
                    is_block_comment = True
                    position = line_counter

                # Actually formulate the comments.
                while line_list[i + 1] != ".. fenced-code::":
                    f = formulate_comment(
                        line_list[i], lang, is_block_comment, position, line_counter
                    )
                    string_out += f
                    position -= 1
                    i += 1
                    # This catches the case that the string runs out of lines.
                    # This ensures that the while loop does not loop forever due to the next line being ``None``
                    try:
                        line_list[i + 1]
                    except Exception:
                        f = formulate_comment(
                            line_list[i], lang, is_block_comment, position, line_counter
                        )
                        string_out += f
                        i += 1
                        break
            else:
                # See Boolean_.
                boolean = True
                break

            if boolean:
                break
        except Exception:
            if line_list[i] != "":
                # See Boolean_.
                boolean = True
            i += 1
            break

    # _`Boolean`: If Boolean is set to True, there was a line of invalid reST, so the program returns an error string.
    if boolean:
        # Return an error message.
        string_out += "This was not recognized as valid reST. Please check your input and try again."

    return string_out


# |
#
# _`html_to_code_file`: This function uses html_to_code_string_ to convert a HTML file into
# another language. Inputs a HTML file, outputs a code file.
def html_to_code_file(
    # See lang_
    lang,
    # _`source_html_path`: Path to a source HTML file to process.
    source_html_path,
    # See out_path_. If out_path_ is None, the output path will be the source_html_path_
    # but with the correct file extension for the given lang_
    out_path=None,
    # See input_encoding_
    input_encoding=None,
    # See output_encoding_
    output_encoding="utf-8",
):
    if out_path is None:
        # Find the file extension of the given language.
        file_ext = find_file_ext(lang)
        # Obtain the file path without the ``.rst`` extension.
        file_name_list = source_html_path.rsplit(".", 1)
        file_name = file_name_list[0]
        # Place the file extension on the file path.
        out_path = "{}{}".format(file_name, file_ext)

    # Use docutil's I/O classes to better handle and sniff encodings.
    #
    # Note: both these classes automatically close themselves after a
    # read or write.
    fi = io.FileInput(source_path=source_html_path, encoding=input_encoding)
    fo = io.FileOutput(destination_path=out_path, encoding=output_encoding)
    # Gather the entire file into a singe string for easy parsing.
    html_str = fi.read()
    # Convert the string of HTML to code.
    code = html_to_code_string(html_str, lang)
    # Write the code to the output file.
    fo.write(code)


# |
#
# _`html_to_code_string`: Take string of HTML as input, returns a string of code. The string is
# separated into lines and fed through the conversion one line at a time.
def html_to_code_string(
    # _`html_str`: The string of HTML that will get converted into code.
    # This string is generally multiple lines. The program separates and processes all the lines it is given.
    html_str,
    # See lang_.
    lang,
):
    string_out = "\n.. set-line:: -3\n\n..\n\n"

    def traverse_etree(element):
        nonlocal string_out
        if isinstance(element.tag, str):
            tag = element.tag
            if tag == "p":
                string_out += "\n.. set-line:: -3\n\n..\n\n"
                if element.get("id") is not None:
                    s = element.get("id")
                    s = s.replace("-", "_")
                    string_out += ".. _{}:\n\n".format(s)
                if element.text is not None:
                    # ``element.text`` starts out as ``NoneType``, so tell the program to convert it to a string.
                    string_out += str(element.text)
            elif tag == "div":
                div(element)
                if element.get("class") == "contents topic":
                    return
            elif tag == "pre":
                s = str(element.text)
                s = s.replace("\n", "\n ")
                s, _ = s.rsplit(" ", 1)
                string_out += "\n.. fenced-code::\n\n Beginning fence\n {} Ending fence\n\n..\n\n".format(
                    s
                )
            elif tag == "a":
                link(element)
            elif tag == "b":
                string_out += "**{}**".format(element.text)
                if element.tail is not None:
                    string_out += str(element.tail)
            elif tag == "i" or tag == "em":
                string_out += "*{}*".format(element.text)
                if element.tail is not None:
                    string_out += str(element.tail)
            elif tag == "span":
                if element.get("class") == "target":
                    string_out += "_`{}`".format(element.text)
                if element.tail is not None:
                    string_out += str(element.tail)
            elif tag == "tt":
                if element.get("class") == "docutils literal":
                    string_out += "``{}".format(element.text)

        for child in element:
            traverse_etree(child)

        if isinstance(element.tag, str):
            tag = element.tag
            if tag == "p":
                string_out += "\n"
            elif tag == "div":
                div_end(element)
            elif tag == "tt":
                string_out += "``"
                if element.tail is not None:
                    string_out += str(element.tail)

    def div(element):
        nonlocal string_out
        if element.get("style") is not None:
            string_out += '\n.. raw:: html\n\n <div style="{}">\n\n'.format(
                element.get("style")
            )
        elif element.get("class") == "contents topic":
            string_out += "\n.. contents::\n\n"

    def div_end(element):
        nonlocal string_out
        if element.get("style") is not None:
            string_out += "\n\n.. raw:: html\n\n </div>\n\n..\n\n"

    def link(element):
        nonlocal string_out
        if element.get("class") == "reference internal":
            target = element.get("href")
            _, target = target.split("#")
            target = target.replace("-", "_")
            string_out += "`{} <{}_>`_".format(element.text, target)
        elif element.get("class") == "reference external":
            target = element.get("href")
            string_out += "`{} <{}>`_".format(element.text, target)
        if element.tail is not None:
            string_out += str(element.tail)

    # Take out the xml encoding; it messes up the tree
    for i in range(1):
        try:
            html_list = html_str.split("<?xml", 1)
            html_list2 = html_list[1].split('.dtd">\n', 1)
            html_str = html_list[0] + html_list2[1]
        # If the style sheets are not in the string, get out of the for loop.
        except Exception:
            break
    # Take out the 2 style sheets; they are not needed
    for i in range(2):
        try:
            html_list = html_str.split('<style type="text/css">', 1)
            html_list2 = html_list[1].split("</style>\n", 1)
            html_str = html_list[0] + html_list2[1]
        # If the style sheets are not in the string, get out of the for loop.
        except Exception:
            break

    # This needs to be preprocessed because there are cases where there are ``<span>``\ (s) in the middle,
    # preventing the end tics from being placed in the right spot
    # html_str = html_str.replace('<tt class="docutils literal">', '``')
    # html_str = html_str.replace('</tt>', '``')
    root = html.fromstring(html_str)

    traverse_etree(root)
    # need to write a recursive function so it can catch all the levels of divs

    # string_out = rest_to_code_string(string_out, lang)

    return string_out


"""    # Take out the 2 style sheets; they are not needed
    for i in range(2):
        try:
            html_list = html_str.split('<style type="text/css">', 1)
            html_list2 = html_list[1].split('</style>\n', 1)
            html_str = html_list[0] + html_list2[1]
        # If the style sheets are not in the string, get out of the for loop.
        except:
            break
    has_code_block = True
    string_out = ""
    while has_code_block:
        try:
            html_to_run, html_to_parse = html_str.split('<pre class="code literal-block">\n', 1)
            rst = convert_text(html_to_run, to='rst', format='html')

            code, html_str = html_to_parse.split('</pre>', 1)
            string_out = string_out + rst + code
        except:
            rst = convert_text(html_str, to='rst', format='html')
            string_out = string_out + rst
            has_code_block = False




    #string_out = html_str
    return string_out
"""
