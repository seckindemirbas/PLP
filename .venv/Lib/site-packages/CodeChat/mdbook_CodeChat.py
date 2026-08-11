# **********************************************
# |docname| - A CodeChat preprocessor for mdbook
# **********************************************
# `mdbook <https://rust-lang.github.io/mdBook/index.html>`_ allows preprocessors to modify the provided source before processing it with a Markdown engine. This preprocessor transforms source code in files collected by mdbook_ into Markdown based on CodeChat.
#
# See the mdbook template for an example of how to integrate CodeChat with mdbook.
#
# See the `mdbook docs <https://rust-lang.github.io/mdBook/index.html>`_ on `configuring preprocessors <https://rust-lang.github.io/mdBook/format/configuration/preprocessors.html>`_ and `preprocessors in the For Developers chapter <https://rust-lang.github.io/mdBook/for_developers/preprocessors.html>`_ for more information.
#
#
# Imports
# =======
# These are listed in the order prescribed by `PEP 8
# <http://www.python.org/dev/peps/pep-0008/#imports>`_.
#
# Standard library
# ----------------
import sys
import json
from pathlib import Path

# Third-party imports
# -------------------
import pygments.util

# Local application imports
# -------------------------
from CodeChat.CommentDelimiterInfo import SUPPORTED_GLOBS
from CodeChat.CodeToMarkdown import code_to_markdown_string
from CodeChat.SourceClassifier import get_lexer


# Code
# ====
# This is the heart of the program: given a list of ``sub_items``, walk the list, transforming source code to Markdown.
def process_sections(sub_items, source_suffixpatterns, lexer_for_glob):
    for section in sub_items:
        # If this is a chapter, instead of a section title / separator / etc., process it. (Note that separators aren't a dict, but instead the string "Separator".)
        chapter = None if isinstance(section, str) else section.get("Chapter")
        if chapter:
            source_path = Path(chapter["source_path"])
            content = chapter["content"]
            # Don't process Markdown files. Try everything else.
            if source_path.suffix != ".md" and is_supported_language(
                source_path, source_suffixpatterns
            ):
                # See if it's an extension we should process.
                try:
                    # See if ``source_file`` matches any of the globs.
                    lexer = None
                    for glob, lexer_alias in lexer_for_glob.items():
                        if source_path.match(glob):
                            # On a match, pass the specified lexer alias.
                            lexer = get_lexer(alias=lexer_alias)
                            break
                    # Do this after checking the ``lexer_for_glob`` list, since this will raise an exception on failure.
                    lexer = lexer or get_lexer(filename=str(source_path), code=content)

                    chapter["content"] = code_to_markdown_string(content, lexer=lexer)
                    print(
                        f"Converted {source_path} using the {lexer.name} lexer.",
                        file=sys.stderr,
                    )

                except (KeyError, pygments.util.ClassNotFound):
                    # We don't support this language.
                    pass

            process_sections(
                chapter["sub_items"], source_suffixpatterns, lexer_for_glob
            )


# Return True if the provided filename is a source code language CodeChat supports.
def is_supported_language(filename, source_suffixpatterns):
    for source_suffixpattern in source_suffixpatterns:
        if filename.match(source_suffixpattern):
            return True
    return False


# main
# ----
def main():
    # See if this is asking for renderer support, or for an actual render.
    if len(sys.argv) > 1:
        # Renderer support -- html only.
        sys.exit(len(sys.argv) == 3 and sys.argv[1:2] == ["supports", "html"])

    # Delay imports until this point, so the first phase of the build (detecting support, which is handled above) can run without these.
    # Load both the context and the book representations from stdin.
    context, book = json.load(sys.stdin)
    # Get the lexer_for_glob dict.
    lexer_for_glob = context["config"]["preprocessor"]["CodeChat"]["lexer_for_glob"]
    source_suffixpatterns = SUPPORTED_GLOBS | set(lexer_for_glob.keys())
    # Walk through each file, rendering it if possible.
    process_sections(book["sections"], source_suffixpatterns, lexer_for_glob)
    # Dump the updated book back to mdbook via stdout.
    print(json.dumps(book))


if __name__ == "__main__":
    main()
