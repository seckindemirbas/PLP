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
# ***************************************
# |docname| - a module to lex source code
# ***************************************
# This module classifies source code in any format supported by `CommentDelimiterInfo.py` into an iterable of ``(type, string)`` tuples; see `source_lexer`.
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
import ast
from enum import Enum
import inspect

# Third-party imports
# -------------------
from pygments.lexers import (
    get_lexer_for_filename,
    get_lexer_by_name,
    get_lexer_for_mimetype,
    guess_lexer_for_filename,
    guess_lexer,
)
from pygments.util import guess_decode
from pygments.lexer import _encoding_map
from pygments.token import Token
from pygments.filter import apply_filters

# Local application imports
# -------------------------
from .CommentDelimiterInfo import COMMENT_DELIMITER_INFO


# Supporting routines
# -------------------
#
# .. _get_lexer:
#
# get_lexer
# ^^^^^^^^^
# Provide several ways to find a lexer. Provide any of the following arguments,
# and this function will return the appropriate lexer for it.
def get_lexer(
    # The lexer itself, which will simply be returned.
    lexer=None,
    # The `short name <http://pygments.org/docs/lexers/>`_, or alias, of the
    # lexer to use.
    alias=None,
    # The filename of the source file to lex.
    filename=None,
    # The MIME type of the source file to lex.
    mimetype=None,
    # The code to be highlighted, used to guess a lexer.
    code=None,
    # _`options`: Specify the lexer (see `get_lexer` arguments), and provide it any other needed options.
    **options
):
    # This sets the default tabsize to 4 spaces in
    # `Pygments' lexer <http://pygments.org/docs/api/#pygments.lexer.Lexer>`_,
    # and this link is a list  of
    # `all available lexers <http://pygments.org/docs/lexers/#available-lexers>`_
    options.setdefault("tabsize", 4)

    if lexer:
        return lexer
    if alias:
        return get_lexer_by_name(alias, **options)
    if filename:
        if code:
            # Given code, try to guess a more accurate lexer.
            lexer_ = guess_lexer_for_filename(filename, code, **options)
            # Only use this guess if we support it.
            if lexer_.name in COMMENT_DELIMITER_INFO:
                return lexer_
        # If guessing fails or isn't available, look up a lexer based on the file name.
        return get_lexer_for_filename(filename, **options)
    if mimetype:
        return get_lexer_for_mimetype(mimetype, **options)
    if code:
        return guess_lexer(code, **options)


# Provide the ability to print debug info if needed.
def _debug_print(val):
    # Uncomment for debug prints.
    # print(val),
    pass


# .. _source_lexer:
#
# Implementation
# ==============
# This function transforms source code in any format supported by `CommentDelimiterInfo.py` into an iterable of ``(type, string)`` tuples, where:
#
# - ``type`` is an integer giving the number of spaces in this comment's indent, or -1 if the comment is code. Note that non-CodeChat comments are classified as code.
# - ``string`` is one line of code or comment, ending with a newline. Comments are supplied with the indent and delimiters removed.
#
# **This routine is the heart of the algorithm.**
def source_lexer(
    # _`code_str`: the code to classify.
    code_str,
    # _`lexer`: The lexer used to analyze the code.
    lexer,
):
    _debug_print("Lexer: {}\n".format(lexer.name))
    # Gather some additional information, based on the lexer, which is needed
    # to correctly process comments:
    cdi = COMMENT_DELIMITER_INFO[lexer.name]
    # * If there's no multi-line start info, then classify generic comments as
    #   inline. The exception is HTML, which (currently, as of Pygments v.10.0) classifies as generic comments, but also supports in-line JavaScript comments.
    comment_is_inline = False if lexer.name == "HTML" else not cdi[1]
    # * Likewise, no inline info indicates that generic comments are block
    #   comments. Note that inline comments are a sequence of strings, so look
    #   inside the sequence to the string.
    comment_is_block = True if lexer.name == "HTML" else not cdi[0][0]

    # 1.    Invoke a Pygments lexer on the provided source code, obtaining an
    #       iterable of tokens. Also analyze Python code for docstrings.
    #
    token_iter, ast_docstring, ast_syntax_error = _pygments_lexer(code_str, lexer)

    # 2.    Combine tokens from the lexer into three groups: whitespace, comment,
    #       or other.
    token_group = _group_lexer_tokens(
        token_iter, comment_is_inline, comment_is_block, ast_docstring
    )

    # 3.    Make a per-line list of [group, ws_len, string], so that the last
    #       string in each list ends with a newline. Change the group of block
    #       comments that actually span multiple lines.
    gathered_group = _gather_groups_on_newlines(token_group, cdi)

    # 4.    Classify each line. For CodeChat-formatted comments, remove the leading whitespace and all comment characters (the // or #, for example).
    return ast_syntax_error, _classify_groups(gathered_group, cdi, lexer)


# .. _CodeChat style:
#
# CodeChat style
# --------------
# `css/CodeChat.css` provides some of the CSS needed to properly format CodeChat documents. However, not all the necessary styling can be accomplished using CSS. This script sets the styles that can't be set in CSS. Specifically, it removes the bottom margin for cases where code follows a paragraph, and the top margin for cases where code preceds a paragraph. The expected structure:
#
# .. code-block:: HTML
#   :linenos:
#
#   <!-- All CodeChat-produced code is marked by the ``fenced-code``
#        class. -->
#   <div class="fenced-code">
#       ...Some code here...
#   </div>
#
#   <!-- An indent from CodeChat -- not present with no indent. The
#        code below will add the classes ``CodeChat_noTop
#        CodeChat_noBottom`` to this element.
#   -->
#   <div class="CodeChat-indent">
#       <!-- The code below will add the class ``CodeChat_noTop`` to
#            this element.
#       -->
#       <p>Text.</p>
#       <!-- The code below will add the class ``CodeChat_noBottom``
#            to this element.
#       -->
#       <p>Some text here</p>
#   </div>
#
#   <div class="fenced-code">
#       ...Some more code here...
#   </div>
#
# `Disable Black <https://github.com/psf/black#the-black-code-style>`_ for this block.
# fmt: off
codechat_style = (
    '<script type="text/javascript">'
    # Define a function to add classes as defined above.
    "function CodeChat_doStyle("
        # It takes an optional parameter, the root element to search from. Styles will be applies to this element and all its children. It defaults to ``document``.
        "element"
    ") {"
        # Walk the tree in the given direction.
        "function walk_tree("
            # A list of DOM elements to walk.
            "elements,"
            # The walker function: ``x => x.next/prevElementSibling``.
            "func_walk,"
            # Which child to select, ``x => first/lastElementChild``.
            "func_child) {"

            # Create an array to hold the children found.
            "let walk_children = [];"
            # For each element in the list of elements, find all its next/previous children.
            "for (let index = 0; index < elements.length; ++index) {"
                # If the current element (``that``) does not have a next/previous sibling, ascend the tree until we find one or reach the top.
                "let that = elements[index];"
                "while (that && !func_walk(that)) {"
                    "that = that.parentElement;"
                "}"
                "if (that) {"
                    # We found a next/previous sibling. Go there.
                    "that = func_walk(that);"

                    # Include the next/previous sibling in the output.
                    "walk_children.push(that);"
                    # Add all first/last children of this node to the output.
                    "while (that && func_child(that)) {"
                        "that = func_child(that);"
                        "walk_children.push(that);"
                    "}"
                "}"
            "}"
            "return walk_children;"
        "};"

        # Use ``document`` as the default element if it isn't specified.
        "element = (typeof element !== 'undefined') ? element : document;"
        # All CodeChat-produced code is marked by the ``fenced-code`` class.
        'let code = element.getElementsByClassName("fenced-code");'
        # Go to the next node from code, then set the margin-top of all first children to 0 so that there will be no extra space between the code and the following comment.
        "walk_tree(code, x => x.nextElementSibling, x => x.firstElementChild).map(x =>"
            "x.classList.add('CodeChat_noTop')"
        ");"
        # Same, but remove space between a comment and the following code.
        "walk_tree(code, x => x.previousElementSibling, x => x.lastElementChild).map(x =>"
            "x.classList.add('CodeChat_noBottom')"
        ");"
    "}"

    # Only style after the `DOM is ready <https://stackoverflow.com/questions/799981/document-ready-equivalent-without-jquery>`_.
    'document.addEventListener("DOMContentLoaded", function(event) { CodeChat_doStyle(); });'
    "</script>"
)
# fmt: on


# Step 1 of source_lexer_
# -----------------------
def _pygments_lexer(
    # See code_str_.
    code_str,
    # See lexer_.
    lexer,
):
    # Pygments does some cleanup on the code given to it before lexing it. If
    # this is Python code, we want to run AST on that cleaned-up version, so
    # that AST results can be correlated with Pygments results. However,
    # Pygments doesn't offer a way to do this; so, add that ability in to the
    # detected lexer.
    preprocessed_code_str = _pygments_get_tokens_preprocess(lexer, code_str)
    # Note: though Pygments does support a `String.Doc token type <http://pygments.org/docs/tokens/#literals>`_,
    # it doesn't truly identify docstrings; from Pygments 2.1.3,
    # ``pygments.lexers.python.PythonLexer``:
    #
    # .. code-block:: Python3
    #    :linenos:
    #    :lineno-start: 55
    #
    #    (r'^(\s*)([rRuU]{,2}"""(?:.|\n)*?""")', bygroups(Text, String.Doc)),
    #    (r"^(\s*)([rRuU]{,2}'''(?:.|\n)*?''')", bygroups(Text, String.Doc)),
    #
    # which means that ``String.Doc`` is simply *ANY* triple-quoted string.
    # Looking at other lexers, ``String.Doc`` often refers to a
    # specially-formatted comment, not a docstring. From
    # ``pygments.lexers.javascript``:
    #
    # .. code-block:: Javascript
    #    :linenos:
    #    :lineno-start: 591
    #
    #    (r'//.*?\n', Comment.Single),
    #    (r'/\*\*!.*?\*/', String.Doc),
    #    (r'/\*.*?\*/', Comment.Multiline),
    #
    # So, the ``String.Doc`` token can't be used in any meaningful way by
    # CodeToRest to identify docstrings. Per Wikipedia's `docstrings article
    # <https://en.wikipedia.org/wiki/Docstring>`_, only three languages support
    # this feature. So, we'll need a language-specific approach. For Python,
    # `PEP 0257 <https://www.python.org/dev/peps/pep-0257>`_ provides the
    # syntax and even some code to correctly remove docstring indentation. The
    # `ast <https://docs.python.org/3.4/library/ast.html>`_ module provides
    # routines which parse a given Python string without executing it, which
    # is better than evaluating arbitrary Python then looking at its
    # ``__doc__`` attributes.
    #
    # Perhaps the approach would be to scan with ast_, then see if the line
    # number matches the ending line number of a string, and if so convert the
    # string into a comment. Trickiness: Python will merge strings; consider
    # the following:
    #
    # .. code-block:: pycon
    #    :linenos:
    #
    #    >>> def foo():
    #    ...     ("""A comment.""" \
    #    ...      ' More.'
    #    ...      " And more.")
    #    ...     pass
    #    ...
    #    >>> print(foo.__doc__)
    #    A comment. More. And more.
    #
    # It's probably best not to support this case. Unfortunately, ast_ reports
    # this as a single string, rather than as a list of several elements.
    # The approach: make sure the docstring found by ast_ is in the text of a
    # Pygments string token. If so, replace the string token by a block
    # comment, whose contents come from ``inspect.cleandoc`` of the docstring.
    #
    # So, process this with ast_ if this is Python or Python3 code to find docstrings.
    # If found, store ``{ ending_line_number_of_the_comment: docstring }`` into
    # ``ast_docstring``.
    ast_docstring = {}
    # Provide a place to store syntax errors resulting from parsing the Python code.
    ast_syntax_error = ""
    # Determine if code is Python or Python3. Note that AST processing cannot
    # support Python 2 specific syntax (e.g. the ``<>`` operator).
    if lexer.name == "Python" or lexer.name == "Python 3":
        # Syntax errors cause ``ast.parse`` to fail. Catch and report them.
        try:
            # If so, walk through the preprocessed code to analyze each token.
            for _ in ast.walk(ast.parse(preprocessed_code_str)):
                try:
                    # Check if current token is a docstring. The docstring will
                    # be cleaned later.
                    d = ast.get_docstring(_, False)
                    if d is not None:
                        # If so, store current line number and token value. Note
                        # that ``lineno`` gives the last line of the string,
                        # per http://bugs.python.org/issue16806, for
                        # Python <= 3.7. Per the docs, ``end_lineno`` was
                        # introduced in Python 3.8.
                        end_lineno = getattr(_.body[0], "end_lineno", _.body[0].lineno)
                        ast_docstring[end_lineno] = d
                except (AttributeError, TypeError):
                    pass
        except SyntaxError as err:
            # Take the file name (which shows up as ``<unknown>``) out of the error message returned.
            ast_syntax_error = (
                "SyntaxError: {}. Docstrings cannot be processed.\n".format(
                    err
                ).replace("<unknown>, ", "")
            )

    # Now, run the lexer.
    return (
        _pygments_get_tokens_postprocess(lexer, preprocessed_code_str),
        ast_docstring,
        ast_syntax_error,
    )


# Pygments monkeypatching
# ^^^^^^^^^^^^^^^^^^^^^^^
# Provide a way to perform preprocessing on text before lexing it. This code was
# copied from ``pygments.lexer.Lexer.get_token``, v. 2.6.1.
def _pygments_get_tokens_preprocess(self, text, unfiltered=False):
    """
    Return an iterable of (tokentype, value) pairs generated from
    ``text``. If ``unfiltered`` is set to ``True``, the filtering mechanism
    is bypassed even if filters are defined.

    Also preprocess the text, i.e. expand tabs and strip it if
    wanted and applies registered filters.
    """
    if not isinstance(text, str):
        if self.encoding == "guess":
            text, _ = guess_decode(text)
        elif self.encoding == "chardet":
            try:
                import chardet
            except ImportError:
                raise ImportError(
                    "To enable chardet encoding guessing, "
                    "please install the chardet library "
                    "from http://chardet.feedparser.org/"
                )
            # check for BOM first
            decoded = None
            for bom, encoding in _encoding_map:
                if text.startswith(bom):
                    decoded = text[len(bom) :].decode(encoding, "replace")
                    break
            # no BOM found, so use chardet
            if decoded is None:
                enc = chardet.detect(text[:1024])  # Guess using first 1KB
                decoded = text.decode(enc.get("encoding") or "utf-8", "replace")
            text = decoded
        else:
            text = text.decode(self.encoding)
            if text.startswith("\ufeff"):
                text = text[len("\ufeff") :]
    else:
        if text.startswith("\ufeff"):
            text = text[len("\ufeff") :]

    # text now *is* a unicode string
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    if self.stripall:
        text = text.strip()
    elif self.stripnl:
        text = text.strip("\n")
    if self.tabsize > 0:
        text = text.expandtabs(self.tabsize)
    if self.ensurenl and not text.endswith("\n"):
        text += "\n"

    # EDIT: This is not from the original Pygments code. It was added to return
    # the preprocessed text.
    return text


# This code was copied from ``pygments.lexer.Lexer.get_token``, v. 2.6.1 (the last
# few lines).
def _pygments_get_tokens_postprocess(self, text, unfiltered=False):
    def streamer():
        for _, t, v in self.get_tokens_unprocessed(text):
            yield t, v

    stream = streamer()
    if not unfiltered:
        stream = apply_filters(stream, self.filters, self)
    return stream


# Step 2 of source_lexer_
# -----------------------
# Given tokens, group them.
def _group_lexer_tokens(
    # An iterable of (tokentype, string) pairs provided by the lexer, per
    # `get_tokens
    # <http://pygments.org/docs/api/#pygments.lexer.Lexer.get_tokens>`_.
    iter_token,
    # .. _comment_is_inline:
    #
    # When true, classify generic comments as inline.
    comment_is_inline,
    # .. _comment_is_block:
    #
    # When true, classify generic comment as block comments.
    comment_is_block,
    # Docstring dict found from AST scanning.
    ast_docstring,
):
    # Keep track of the current group, string, and line no.
    current_string = ""
    current_group = None
    token_lineno = 1
    # Walk through tokens.
    for tokentype, string in iter_token:
        _debug_print("tokentype = {}, string = {}\n".format(tokentype, [string]))
        # Increase token line no. for every newline found.
        token_lineno += string.count("\n")
        if tokentype == Token.Literal.String.Doc:
            _debug_print(
                "token_lineno = {}, token_docstring = {}\n".format(token_lineno, string)
            )
            # Compare formatted token containing docstring with AST result.
            if ast_docstring.get(token_lineno) == string[3:-3]:
                tokentype = Token.Comment.Multiline
                string = inspect.cleandoc(string)
                # Insert an extra space after the docstring delimiter, making
                # this look like a reST comment.
                string = string[0:3] + " " + string[3:]
        group = _group_for_tokentype(tokentype, comment_is_inline, comment_is_block)

        # If there's a change in group, yield what we've accumulated so far,
        # then initialize the state to the newly-found group and string.
        if current_group is None:
            current_group = group
        if current_group != group:
            yield current_group, current_string
            current_group = group
            current_string = string
        # Otherwise, keep accumulating.
        else:
            current_string += string

    # Output final pair, if we have it.
    if current_string:
        yield current_group, current_string


# Supporting routines and definitions
# ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
# Define the groups into which tokens will be placed.
class _GROUP(Enum):
    # The basic classification used by group_for_tokentype_.
    whitespace = 1
    inline_comment = 2
    other = 3
    # A ``/* comment */``-style comment contained in one string.
    block_comment = 4
    # Grouping is::
    #
    #    /* BLOCK_COMMENT_START
    #       BLOCK_COMMENT_BODY, (repeats for all comment body)
    #       BLOCK_COMMENT_END */
    block_comment_start = 5
    block_comment_body = 6
    block_comment_end = 7


# .. _group_for_tokentype:
#
# Given a tokentype, group it.
def _group_for_tokentype(
    # The tokentype to place into a group.
    tokentype,
    # See comment_is_inline_.
    comment_is_inline,
    # See comment_is_block_.
    comment_is_block,
):
    # The list of Pygments `tokens <http://pygments.org/docs/tokens/>`_ lists
    # ``Token.Text`` (how a newline is classified) and ``Token.Whitespace``.
    # Consider either as whitespace.
    if tokentype in Token.Text or tokentype in Token.Whitespace:
        return _GROUP.whitespace
    # There is a Token.Comment, but this can refer to inline or block comments.
    # Therefore, use info from CommentDelimiterInfo as a tiebreaker.
    if (
        tokentype == Token.Comment.Single
        or
        # A few goofy lexers use this as of Pygments 2.1.3. See https://bitbucket.org/birkenfeld/pygments-main/issues/1251/use-of-commentsingleline-instead-of.
        tokentype == Token.Comment.Singleline
        or (tokentype == Token.Comment and comment_is_inline)
    ):
        return _GROUP.inline_comment
    if tokentype == Token.Comment.Multiline or (
        tokentype == Token.Comment and comment_is_block
    ):
        return _GROUP.block_comment
    # If the tiebreaker above doesn't classify a Token.Comment, then assume it
    # to be an inline comment. This occurs in the Matlab lexer using Pygments
    # 2.0.2.
    if tokentype == Token.Comment:
        return _GROUP.inline_comment

    return _GROUP.other


# Step #3 of source_lexer_
# ------------------------
# Given an iterable of groups, break them into lists based on newlines. The list
# consists of (group, comment_leading_whitespace_length, string) tuples.
def _gather_groups_on_newlines(
    # An iterable of (group, string) pairs provided by
    # ``group_lexer_tokens``.
    iter_grouped,
    # .. _comment_delim_info:
    #
    # An element of COMMENT_DELIMITER_INFO for the language being classified.
    comment_delim_info,
):
    # Keep a list of (group, string) tuples we're accumulating.
    _list = []

    # Keep track of the length of whitespace at the beginning of the body and
    # end portions of a block comment.
    ws_len = 0

    # The length of an opening block comment
    len_opening_block_comment = len(comment_delim_info[1])

    # Accumulate until we find a newline, then yield that.
    for group, string in iter_grouped:
        _debug_print("group = {}, string = {}\n".format(group, [string]))
        # A given group (such as a block string) may extend across multiple
        # newlines. Split these groups apart first.
        splitlines = string.splitlines(True)

        # Look for block comments spread across multiple lines and label
        # them correctly.
        if len(splitlines) > 1 and group == _GROUP.block_comment:
            group = _GROUP.block_comment_start
            # Look for an indented multi-line comment block. First, determine
            # what the indent must be: (column in which comment starts) +
            # (length of comment delimiter) + (1 space).
            ws_len = len_opening_block_comment + 1
            for group_, ws_len_, string_ in _list:
                ws_len += len(string_)
            # Determine the indent style (all spaces, or spaces followed by a
            # character, typically ``*``). If it's not spaces only, it must
            # be spaces followed by a delimiter.
            #
            # First, get the last character of the block comment delimiter.
            # This is expressed as a 1-character range, so that '' will be
            # returned if the index is past the end of the string. Perl's PODs
            # consist of ``=whatever text you want\n``, meaning the entire line
            # should be discarded. To make this "easy", I define
            # comment_delim_info[1] as a very large number, so that the entire
            # line will be discarded. Hence, the need for the hack below.
            last_delim_char = string[
                len_opening_block_comment - 1 : len_opening_block_comment
            ]
            if _is_space_indented_line(
                splitlines[1],
                ws_len,
                last_delim_char,
                len(splitlines) == 1,
                comment_delim_info,
            ):
                is_indented_line = _is_space_indented_line
            else:
                is_indented_line = _is_delim_indented_line

            # Look at the second and following lines to see if their indent is
            # consistent.
            for i, line in enumerate(splitlines[1:]):
                if not is_indented_line(
                    line,
                    ws_len,
                    last_delim_char,
                    len(splitlines) - 2 == i,
                    comment_delim_info,
                ):
                    # It's inconsistent. Set ws_len to 0 to signal that this
                    # isn't an indented block comment.
                    ws_len = 0
                    break

        for index, split_str in enumerate(splitlines):
            # Accumulate results.
            _list.append((group, ws_len, split_str))

            # For block comments, move from a start to a body group.
            if group == _GROUP.block_comment_start:
                group = _GROUP.block_comment_body
            # If the next line is the last line, update the block
            # group.
            is_next_to_last_line = index == len(splitlines) - 2
            if is_next_to_last_line and group == _GROUP.block_comment_body:
                group = _GROUP.block_comment_end

            # Yield when we find a newline, then clear our accumulator.
            if split_str.endswith("\n"):
                yield _list
                _list = []

        # We've output a group; reset the ws_len to 0 in case the group just
        # output was a multi-line block comment with ws_len > 0.
        ws_len = 0

    # Output final group, if one is still accumulating.
    if _list:
        yield _list


# Block comment indentation processing
# ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#
# #. A single line: ``/* comment */``. No special handling needed.
# #. Multiple lines, indented with spaces. For example:
#
#    .. code-block:: c
#       :linenos:
#
#       Column:  1
#       1234567890234567
#
#         /* A multi-
#
#            line
#         WRONG INDENTATION
#              string
#          */
#
#    In the code above, the text of the comment begins at column 6 of line 4,
#    with the letter A. Therefore, line 7 lacks the necessary 6-space indent,
#    so that no indentation will be removed from this comment.
#
#    If line 6 was indented properly, the resulting reST would be:
#
#    .. code-block:: rest
#
#       ...rest to indent the left margin of the following text 2 spaces...
#
#       A multi-
#
#       line
#       RIGHT INDENTATION
#         string
#
#       ...rest to end the left margin indent...
#
#    Note that the first 5 characters were stripped off each line, leaving only
#    line 8 indented (preserving its indentation relative to the comment's
#    indentation). Some special cases in doing this processing:
#
#    * Line 5 may contain less than the expected 5 space indent: it could be
#      only a newline. This must be supported with a special case.
#    * The comment closing (line 9) contains just 3 spaces; this is allowed.
#      If there are non-space characters before the closing comment delimiter,
#      they must not occur before column 6. For example,
#
#      .. code-block:: c
#
#         /* A multi-
#            line comment */
#
#      and
#
#      .. code-block:: c
#
#         /* A multi-
#            line comment
#         */
#
#      have consistent indentation. In particular, the last line of a multi-line
#      comment may contain zero or more whitespace characters followed by the
#      closing block comment delimiter. However,
#
#      .. code-block:: c
#
#         /* A multi-
#           line comment */
#
#      is not sufficiently indented to qualify for indentation removal.
#
#      So, to recognize:
#
def _is_space_indented_line(
    # A line from a multi-line comment to examine.
    line,
    # The expected indent to check for; a length, in characters.
    indent_len,
    # Placeholder for delimiter expected near the end of an indent (one
    # character). Not used by this function, but this function must take the
    # same parameters as is_delim_indented_line_.
    delim,
    # True if this is the last line of a multi-line comment.
    is_last,
    # See comment_delim_info_.
    comment_delim_info,
):
    # A line containing only whitespace is always considered valid.
    if line.isspace():
        return True
    # A line beginning with ws_len spaces has the expected indent.
    if len(line) > indent_len and line[:indent_len].isspace():
        return True

    # The closing delimiter will always be followed by a newline, hence the - 1
    # factor.
    line_except_closing_delim = line[: -len(comment_delim_info[2]) - 1]
    # Last line: zero or more whitespaces followed by the closing block comment
    # delimiter is valid. Since ``''.isspace() == False``, check for this case
    # and consider it true.
    if is_last and (
        not line_except_closing_delim or line_except_closing_delim.isspace()
    ):
        return True
    # No other correctly indented cases.
    return False


# (continuing from the list above...)
#
# #. Multiple lines, indented with spaces followed by a delimiter. For example:
#
#    .. code-block:: c
#       :linenos:
#
#       Column:  1
#       1234567890123456789
#         /* Multi-
#          *   line
#          *
#          *WRONG INDENTATION
#         *  WRONG INDENTATION
#          */
#
#    The rules are similar to the previous case (indents with space alone).
#    However, there is one special case: line 5 doesn't require a space after
#    the asterisk; a newline is acceptable. If the indentation is corrected, the
#    result is:
#
#    .. code-block:: rest
#
#       ...rest to indent the left margin of the following text 2 spaces...
#
#       Multi-
#         line
#
#       RIGHT INDENTATION
#       RIGHT INDENTATION
#
#       ...rest to end left margin indent...
#
#    So, to recognize:
#
# .. _is_delim_indented_line:
#
def _is_delim_indented_line(
    # A line from a multi-line comment to examine.
    line,
    # The expected indent to check for; a length, in characters.
    indent_len,
    # Delimiter expected near the end of an indent (one character).
    delim,
    # True if this is the last line of a multi-line comment.
    is_last,
    # See comment_delim_info_.
    comment_delim_info,
):
    # A line the correct number of spaces, followed by a delimiter then either
    # a space or a newline is correctly indented.
    if (
        len(line) >= indent_len
        and line[: indent_len - 2].isspace()
        and line[indent_len - 2] == delim
        and line[indent_len - 1] in "\n "
    ):
        return True
    # Last line possibility: indent_len - 2 spaces followed by the delimiter
    # is a valid indent. For example, an indent of 3 begins with ``/* comment``
    # and can end with ``_*/``, a total of (indent_len == 3) - (2 spaces
    # that are usually a * followed by a space) + (closing delim ``*/`` length
    # of 2 chars) == 3.
    if (
        is_last
        and len(line) == indent_len - 2 + len(comment_delim_info[2])
        and line[: indent_len - 2].isspace()
    ):
        return True
    # No other correctly indented cases.
    return False


# Step #4 of source_lexer_
# ------------------------
# Classify the output of ``gather_groups_on_newlines`` into either a code or
# comment with n leading whitespace types. Remove all comment characters.
#
# .. Note::
#
#    This is a destructive edit, instead of a classification. To make this
#    invertible, it needs to be non-destructive. The idea:
#
#    * Output s, the entire line as a string, if it's not a reST comment.
#      Currently, it outputs -1, s.
#    * Output whitespace characters or '', opening comment delimiter and
#      space, comment text, closing comment delimiter or '', newline).
#      Currently, it outputs len(leading whitespace characters), comment text +
#      newline.
def _classify_groups(
    # An iterable of [(group1, string1_no_newline), (group2, string2_no_newline),
    # ..., (groupN, stringN_ending_newline)], produced by
    # ``gather_groups_on_newlines``.
    iter_gathered_groups,
    # See comment_delim_info_.
    comment_delim_info,
    # See lexer_.
    lexer,
):
    # Keep track of block comment state.
    is_block_rest_comment = False

    # Walk through groups.
    for _list in iter_gathered_groups:
        _debug_print("[(group, ws_len, string), ...] = {}\n".format(_list))

        if _is_rest_comment(_list, is_block_rest_comment, comment_delim_info, lexer):
            first_group, first_ws_len, first_string = _list[0]
            # The type = # of leading whitespace characters, or 0 if none.
            if first_group == _GROUP.whitespace:
                # Encode this whitespace in the type, then drop it.
                type_ = len(first_string)
                _list.pop(0)
                first_group, first_ws_len, first_string = _list[0]
            # For body or end block comments, use the indent set by at the
            # beginning of the comment. Otherwise, there is no indent, so
            # set it to 0.
            elif not _is_block_body_or_end(first_group):
                type_ = 0

            # Update the block reST state.
            if first_group == _GROUP.block_comment_start:
                is_block_rest_comment = True

            # Strip all comment characters off the strings and combine them.
            string = "".join(
                [
                    _remove_comment_delim(group, string, comment_delim_info, lexer)
                    for group, ws_len, string in _list
                ]
            )
            # Remove the initial space character from the first comment,
            # or ws_len chars from body or end comments.
            if _is_block_body_or_end(first_group):
                # Some of the body or end block lines may be just whitespace.
                # Don't strip these: the line may be too short or we might
                # remove a newline. Or, this might be inconsistent indentation
                # in which ws_len == 0, in which case we should also strip
                # nothing.
                if not string.isspace() and first_ws_len > 0:
                    # The first ws_len - 1 characters should be stripped.
                    string = string[first_ws_len - 1 :]
                    # The last character, if it exists and is a space, should also be
                    # stripped.
                    if string and string[0] == " ":
                        string = string[1:]
            # A comment of ``//\n`` qualifies as a reST comment, but should
            # not have the ``\n`` stripped off. Avoid this case. Otherwise,
            # handle the more typical ``// comment`` case, in which the space
            # after the comment delimiter should be removed.
            elif len(string) > 0 and string[0] == " ":
                string = string[1:]

        # Everything else is considered code.
        else:
            type_ = -1
            string = "".join([string for group, ws_len, string in _list])
            is_block_rest_comment = False

        yield type_, string


# Supporting routines
# ^^^^^^^^^^^^^^^^^^^
# Given a (group, string) tuple, return the string with comment delimiter
# removed if it is a comment, or just the string if it's not a comment.
def _remove_comment_delim(
    # The group this string was classified into.
    group,
    # The string corresponding to this group.
    string,
    # See comment_delim_info_.
    comment_delim_info,
    # See lexer_.
    lexer,
):
    # Number of characters in an opening block comment.
    len_opening_block_comment_delim = len(comment_delim_info[1])
    # Number of characters in an closing block comment.
    len_closing_block_comment_delim = len(comment_delim_info[2])

    if group == _GROUP.inline_comment:
        # .. _COBOL special case:
        #
        # Special case: COBOL. A comment has the character ``*`` or ``/`` in column 7.
        if lexer.name == "COBOL":
            return string[7:] if string[6] in ("*", "/") else string
        # Unlike the opening and closing block comment delimiters, the inline comment delimiter may be a sequence. Check each possibility for a match.
        inline_comment_delim_seq = comment_delim_info[0]
        # Look at each possibility for a match.
        string_lower = string.lower()
        for inline_comment_delim in inline_comment_delim_seq:
            if string_lower.startswith(inline_comment_delim):
                return string[len(inline_comment_delim) :]
        return string
    if group == _GROUP.block_comment:
        return string[len_opening_block_comment_delim:-len_closing_block_comment_delim]
    if group == _GROUP.block_comment_start:
        return string[len_opening_block_comment_delim:]
    if group == _GROUP.block_comment_end:
        return string[:-len_closing_block_comment_delim]
    else:
        return string


# Return a string with the given delimiter removed from its beginning.
#
# .. note::
#
#    This code isn't used yet -- it's for a rewrite which will support multiple
#    delimiters.
def _remove_beginning_comment_delim(
    # Either the number of characters in the beginning delimiter, or a tuple of
    # strings which give all valid beginning comment delimiters.
    beginning_comment_delim_seq,
    # The string which start with the delimiter to be removed.
    string,
):
    # Loop through all delimiters.
    for bcd in beginning_comment_delim_seq:
        # If we find one at the beginning of the string, strip it off.
        if string.startswith(bcd):
            return string[len(bcd) :]

    # Not found -- panic.
    assert False


# Determine if the given line is a comment to be interpreted by reST.
# Supports ``remove_comment_chars``, ``classify_groups``.
def _is_rest_comment(
    # A sequence of (group, string) representing a single line.
    line_list,
    # True if this line contains the body or end of a block comment
    # that will be interpreted by reST.
    is_block_rest_comment,
    # See comment_delim_info_.
    comment_delim_info,
    # See lexer_.
    lexer,
):
    # See if there is any _GROUP.other in this line. If so, it's not a reST
    # comment.
    group_tuple, ws_len_tuple, string_tuple = list(zip(*line_list))
    if _GROUP.other in group_tuple:
        return False
    # If there's no comments (meaning the entire line is whitespace), it's not a
    # reST comment.
    if group_tuple == (_GROUP.whitespace,):
        return False

    # Find the first comment. There may be whitespace preceding it, so select
    # the correct index.
    first_comment_index = 1 if group_tuple[0] == _GROUP.whitespace else 0
    first_group = group_tuple[first_comment_index]
    first_string = string_tuple[first_comment_index]
    # The cases are:
    #
    # 1. ``// comment, //\n, #`` -> reST comment. Note that in some languages
    #    (Python is one example), the newline isn't included in the comment.
    # 2. ``//comment`` -> not a reST comment.
    # 3. ``/* comment, /*\n`` -> reST comment
    # 4. Any block comment body or end for which its block start was a reST
    #    comment -> reST comment.
    # 5. ``/**/`` -> a reST comment. (I could see this either as reST or not;
    #    because it was simpler, I picked reST.)
    #
    # Begin by checking case #4 above.
    if is_block_rest_comment and _is_block_body_or_end(first_group):
        return True
    # To check the other cases, first remove the comment delimiter so we can
    # examine the next character following the delimiter.
    first_comment_text = _remove_comment_delim(
        first_group, first_string, comment_delim_info, lexer
    )
    first_char_is_rest = (
        len(first_comment_text) > 0 and first_comment_text[0] in (" ", "\n")
    ) or len(first_comment_text) == 0
    if first_char_is_rest and not _is_block_body_or_end(first_group):
        return True
    return False


# Determine if this group is either a block comment body or a block comment end.
def _is_block_body_or_end(group):
    return group in (_GROUP.block_comment_body, _GROUP.block_comment_end)
