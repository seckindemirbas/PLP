# .. Copyright (C) 2012-2022 Bryan A. Jones.
#
#   This file is part of the CodeChat System.
#
#   The CodeChat System is free software: you can redistribute it and/or
#   modify it under the terms of the GNU General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.
#
#   The CodeChat System is distributed in the hope that it will be
#   useful, but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#   General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with the CodeChat System.  If not, see
#   <http://www.gnu.org/licenses/>.
#
# *********************************************
# |docname| - Renderers for the CodeChat Server
# *********************************************
# These functions render a document to HTML for a variety of formats.
#
# .. contents:: Table of Contents
#   :local:
#   :depth: 2
#
#
# Imports
# =======
# Library imports
# ---------------
import asyncio
import codecs
from contextlib import contextmanager
from enum import Enum, auto
import fnmatch
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sys
from tempfile import NamedTemporaryFile
from typing import (
    Any,
    cast,
    Callable,
    Coroutine,
    Dict,
    Generator,
    List,
    Optional,
    Tuple,
    Union,
)

# Third-party imports
# -------------------
from CodeChat.CodeToRest import code_to_rest_string, html_static_path  # type: ignore
from CodeChat.CommentDelimiterInfo import SUPPORTED_GLOBS  # type: ignore
import docutils.core
import docutils.writers.html4css1
import markdown  # type: ignore
import pygments.util
import strictyaml


# Local imports
# -------------
# None
#
# Internal renderers
# ==================
# These renderers are invoked via function calls to 3rd party Python libraries.
#
# They all return ``(html, errors)``.
#
# Markdown
# --------
# Convert Markdown to HTML
def _render_markdown(text: str, file_path: str) -> Tuple[str, str]:
    return (
        markdown.markdown(
            text,
            # See https://python-markdown.github.io/extensions/. Enable a few by default.
            extensions=[
                "markdown.extensions.extra",
            ],
        ),
        "",
    )


# reStructuredText (reST)
# -----------------------
# Convert reStructuredText (reST) to HTML.
def _render_ReST(
    text: str, filePath: str, use_codechat: bool = False
) -> Tuple[str, str]:
    errStream = io.StringIO()
    settingsDict = {
        # Make sure to use Unicode everywhere. This name comes from
        # ``docutils.core.publish_string`` version 0.12, lines 392 and following.
        "output_encoding": "unicode",
        # While ``unicode`` **should** work for ``input_encoding``, it doesn't if
        # there's an ``.. include`` directive, since this encoding gets passed to
        # ``docutils.io.FileInput.__init__``, in which line 236 of version 0.12
        # tries to pass the ``unicode`` encoding to ``open``, producing:
        #
        # .. code:: python3
        #    :number-lines:
        #
        #    File "...\python-3.4.4\lib\site-packages\docutils\io.py", line 236, in __init__
        #      self.source = open(source_path, mode, **kwargs)
        #    LookupError: unknown encoding: unicode
        #
        # So, use UTF-8 and encode the string first. Ugh.
        "input_encoding": "utf-8",
        # Don't stop processing, no matter what.
        "halt_level": 5,
        # Capture errors to a string and return it.
        "warning_stream": errStream,
        "stylesheet_dirs": html_static_path(),
        "stylesheet_path": ["docutils.css"]
        + (["CodeChat.css"] if use_codechat else []),
    }
    htmlString = docutils.core.publish_string(
        bytes(text, encoding="utf-8"),
        writer_name="html",
        settings_overrides=settingsDict,
    )
    errString = errStream.getvalue()
    errStream.close()
    return htmlString, errString


# CodeChat
# --------
# Convert source code to HTML.
def _render_CodeChat(text: str, filePath: str) -> Tuple[str, str]:
    try:
        rest_string = code_to_rest_string(text, filename=filePath)
    except KeyError as e:
        return (
            "",
            f"{filePath}:: ERROR: this file, recognized as {e.args[0]}, is not supported by CodeChat.",
        )
    except (ValueError, pygments.util.ClassNotFound):
        # Although the file extension may be in the list of supported
        # extensions, CodeChat may not support the lexer chosen by Pygments.
        # For example, a ``.v`` file may be Verilog (supported by CodeChat)
        # or Coq (not supported). In this case, provide an error message.
        return (
            "",
            f"{filePath}:: ERROR: this file is not supported by CodeChat.",
        )
    return _render_ReST(rest_string, filePath, True)


# Fake renderers
# --------------
# "Render" (pass through) the provided text.
def _pass_through(text: str, file_path: str) -> Tuple[str, str]:  # pragma: no cover
    return text, ""


# The "error renderer" when a renderer can't be found.
def _error_renderer(text: str, file_path: str) -> Tuple[str, str]:  # pragma: no cover
    return "", "{}:: ERROR: No converter found for this file.".format(file_path)


# External renderers
# ==================
# These renderers run in an external program and are all invoked as a subprocess.
#
# Provide a type alias for the ``co_build`` function.
Co_Build = Callable[[str], Coroutine[Any, Any, None]]


# Single-file
# -----------
# Convert a single file using an external program.
async def _render_external_file(
    # See text_.
    text: str,
    # See file_path_.
    file_path: str,
    # See html_path_.
    html_path: Optional[str],
    tool_or_project_path: List[Union[bool, str]],
    # See co_build_.
    co_build: Co_Build,
) -> Tuple[str, str]:
    # Split the provided tool path.
    uses_stdin, uses_stdout, *args_ = tool_or_project_path
    args = cast(List[str], args_)

    # Run from the directory containing the file.
    cwd = Path(file_path).parent

    # Save the text in a temporary file for use with the external tool.
    with _optional_temp_file(not uses_stdin) as input_file, _optional_temp_file(
        not uses_stdout
    ) as output_file:
        if input_file:
            # Write the text to the input file then close it, so that it can be opened on all platforms by the external tool. See `NamedTemporaryFile <https://docs.python.org/3/library/tempfile.html#tempfile.NamedTemporaryFile>`_.
            input_file.write(text)
            input_file.close()

        if output_file:
            # Close the output file for the same reason.
            output_file.close()

        # Do replacements on the args.
        args = [
            s.format(
                input_file=input_file and input_file.name,
                output_file=output_file and output_file.name,
            )
            for s in args
        ]

        stdout, stderr = await _run_subprocess(
            args, cwd, None if input_file else text, bool(output_file), co_build
        )

        # Gather the output from the file if necessary.
        if output_file:
            with open(
                output_file.name, "r", encoding="utf-8", errors="backslashreplace"
            ) as f:
                stdout = f.read()

    return stdout, stderr


# Project
# -------
# Define the possible types of projects.
class ProjectTypeEnum(Enum):
    general = auto()
    PreTeXt = auto()
    Doxygen = auto()


# This class reads and interprets a project configuration file.
class ProjectConfFile:
    # The type of the project declared in this project's configuration file.
    project_type: ProjectTypeEnum
    # The absolute path to this project's root directory.
    project_path: Path
    # The absolute path to the currently open file.
    file_path: Path
    # The extension for HTML files.
    html_ext: str
    # The absolute path to this project's source files.
    source_path: Path
    # The absolute path to this project's output files.
    output_path: Path
    # Arguments used to invoke this project's renderer.
    args: Union[list, str]

    # Read and process a CodeChat project configuration file.
    def __init__(self, project_config_file_path: Path, file_path: Path):
        try:
            with open(project_config_file_path, encoding="utf-8") as f:
                data = f.read()
        except Exception as e:
            raise RuntimeError(
                f"{project_config_file_path}:: ERROR: Unable to open. {e}"
            )

        schema = strictyaml.Map(
            {
                strictyaml.Optional("source_path", default="."): strictyaml.Str(),
                "output_path": strictyaml.Str(),
                "args": strictyaml.Str() | strictyaml.Seq(strictyaml.Str()),
                strictyaml.Optional("html_ext", default=".html"): strictyaml.Str(),
                strictyaml.Optional("project_type", default="general"): strictyaml.Enum(
                    [x.name for x in list(ProjectTypeEnum)]
                ),
            }
        )
        try:
            data_dict = strictyaml.load(data, schema).data
        except strictyaml.YAMLError as e:
            raise RuntimeError(
                f"{project_config_file_path}:: ERROR: Unable to parse. {e}"
            )

        # Save items that don't need processing.
        self.project_type = ProjectTypeEnum[data_dict["project_type"]]
        self.html_ext = data_dict["html_ext"]
        self.file_path = file_path

        # Make paths absolute.
        self.project_path = project_config_file_path.parent

        def abs_path(path: Union[str, Path]) -> Path:
            path_ = Path(path)
            if not path_.is_absolute():
                path_ = self.project_path / path_
            return path_

        self.source_path = abs_path(data_dict["source_path"])
        self.output_path = abs_path(data_dict["output_path"])

        # Find the first XML ID in the source file if this is a PreTeXt project.
        xml_id = ""
        if self.project_type == ProjectTypeEnum.PreTeXt:
            # A crude approximation of an XML ID that should cover most cases.
            match = re.search(r'xml:id="([\w:_\-.]+)', self.file_path.read_text())
            if match:
                xml_id = match.group(1)

        # Perform replacement on the args.
        def args_format(arg):
            return arg.format(
                project_path=self.project_path,
                source_path=self.source_path,
                output_path=self.output_path,
                sys_executable=sys.executable,
                xml_id=xml_id,
            )

        args = data_dict["args"]
        self.args = (
            args_format(args)
            if isinstance(args, str)
            else [args_format(arg) for arg in args]
        )

    # _`checkModificationTime`: Verify that ``source_file`` is older than the HTML file produced by this source, reporting errors if this isn't true.
    def checkModificationTime(
        self,
        # A Path to the source file to examine.
        source_file: Path,
        # An optional Path to the previously displayed HTML file.
        html_path: Optional[Path],
    ) -> Tuple[
        # A path to the proposed or found HTML file.
        Path,
        # A list of error messages.
        List[str],
    ]:
        # Determine a first guess at the location of the rendered HTML.
        prefix = (
            self.output_path
            if self.project_type != ProjectTypeEnum.Doxygen
            else Path(".")
        )
        error_arr = []
        try:
            base_html_file = prefix / source_file.relative_to(self.source_path)
        except ValueError as e:
            # Give some arbitrary value to the output path, since it can't be determined.
            base_html_file = prefix
            error_arr.append(
                "{}:: ERROR: unable to compute path relative to {}. {}".format(
                    source_file, self.source_path, e
                )
            )

        # For PreTeXt, use the mapping of source files to XML IDs == output file name.
        if self.project_type == ProjectTypeEnum.PreTeXt:
            try:
                mapping = self.load_pretext_mapping()
            except Exception:
                pass
            else:
                # Before looking up the file, ``resolve()`` it to get the canonical representation (fix case on Windows), then make this relative to the project directory. Make it posix-formatted, so that the mappings work cross-platform. (For example, this runs on Windows, but the PreTeXt CLI runs on Linux in WSL.)
                xml_id_list = mapping.get(
                    str(source_file.resolve().relative_to(self.project_path).as_posix())
                )
                if xml_id_list:
                    # See if any of the mappings match the currently-displayed file. If so, use that one. Otherwise, pick the first mapping.
                    for id_ in reversed(xml_id_list):
                        base_html_file = self.output_path / id_
                        if html_path and base_html_file == html_path.with_suffix(""):
                            break
        # For Doxygen, rename certain characters in the file name. See `util.cpp::escapeCharsInString <https://github.com/doxygen/doxygen/blob/master/src/util.cpp#L3443>`_.
        elif self.project_type == ProjectTypeEnum.Doxygen:
            doxygen_renamed_path = base_html_file.as_posix()
            for old, new in (
                [":", "_1"],
                ["/", "_2"],
                ["<", "_3"],
                [">", "_4"],
                ["*", "_5"],
                ["&", "_6"],
                ["|", "_7"],
                [".", "_8"],
                ["!", "_9"],
                [",", "_00"],
                [" ", "_01"],
                ["{", "_02"],
                ["}", "_03"],
                ["?", "_04"],
                ["^", "_05"],
                ["%", "_06"],
                ["(", "_07"],
                [")", "_08"],
                ["+", "_09"],
                ["=", "_0a"],
                ["$", "_0b"],
                ["\\", "_0c"],
                ["@", "_0d"],
                ["]", "_0e"],
                ["[", "_0f"],
                ["#", "_0g"],
            ):
                doxygen_renamed_path = doxygen_renamed_path.replace(old, new)
            base_html_file = self.output_path / doxygen_renamed_path

        # Look for the resulting HTML using this guess.
        possible_html_file = base_html_file.with_suffix(self.html_ext)
        if possible_html_file.exists():
            html_file = possible_html_file
        else:
            possible_html_file = Path(str(base_html_file) + self.html_ext)
            if possible_html_file.exists():
                html_file = possible_html_file
            else:
                return (
                    base_html_file,
                    error_arr
                    + [
                        f"{source_file}:: ERROR: CodeChat renderer - unable to find the HTML output file {base_html_file}."
                    ],
                )

        # Recall that time is measured in seconds since the epoch,
        # so that larger = newer.
        try:
            if html_file.stat().st_mtime > source_file.stat().st_mtime:
                return html_file, []
            else:
                return (
                    html_file,
                    error_arr
                    + [
                        f"{source_file}:: ERROR: CodeChat renderer - source file newer than the HTML file {html_file}."
                    ],
                )
        except OSError as e:
            return (
                html_file,
                error_arr
                + [
                    f"{source_file}:: ERROR: CodeChat renderer - unable to check modification time of the HTML file {html_file}: {e}."
                ],
            )

    def load_pretext_mapping(self):
        return json.loads((self.output_path / ".mapping.json").read_text())


# Convert an project using an external renderer.
async def _render_external_project(
    # See text_.
    text: str,
    # See file_path_.
    file_path_: str,
    # See html_path_.
    html_path: Optional[Path],
    _tool_or_project_path: str,
    # See co_build_.
    co_build: Co_Build,
) -> Tuple[str, str]:
    # Run from the directory containing the project file.
    project_conf_file_path = Path(_tool_or_project_path)
    await co_build(
        f"Loading project file {project_conf_file_path}.\n",
    )

    # The ``text`` argument isn't used, since this is an external project, meaning that everything must be saved to disk, instead of rendering the ``text`` currently being edited.
    del text
    file_path = Path(file_path_)

    # Read the project configuration.
    try:
        project_conf = ProjectConfFile(project_conf_file_path, file_path)
    except RuntimeError as e:
        return "", str(e)

    # Compare dates to see if the rendered file is current
    html_path, error_arr = project_conf.checkModificationTime(file_path, html_path)

    # If not, render and try again.
    if error_arr:
        # Render.
        stdout, stderr = await _run_subprocess(
            project_conf.args, project_conf_file_path.parent, None, True, co_build
        )
        html_path, error_arr = project_conf.checkModificationTime(file_path, html_path)
    else:
        stderr = ""

    # Display an error in the main window if one exists.
    if error_arr:
        stderr += "\n".join(error_arr)
    return str(html_path), stderr


# Support
# -------
# OS detection: This follows the `Python recommendations <https://docs.python.org/3/library/sys.html#sys.platform>`_.
is_win = sys.platform == "win32"


# These functions support external renderers.
# If need_temp_file is True, provide a NamedTemporaryFile; otherwise, return a dummy context manager.
def _optional_temp_file(need_temp_file: bool) -> Any:
    return (
        NamedTemporaryFile(mode="w", encoding="utf-8")
        if need_temp_file
        else _dummy_context_manager()
    )


@contextmanager
def _dummy_context_manager() -> Generator:
    yield


# Run a subprocess, optionally streaming the stdout.
async def _run_subprocess(
    args: Union[List[str], str],
    cwd: Path,
    input_text: Optional[str],
    stream_stdout: bool,
    co_build: Co_Build,
) -> Tuple[str, str]:
    # If the args were provided a single string, split it since the asyncio subprocess doesn't accept a string (the standard subprocess does).
    if isinstance(args, str):
        args = shlex.split(args, posix=not is_win)

    # Turn ``args[0]`` into a fully-qualified path to avoid `platform-specific behavior <https://docs.python.org/3/library/subprocess.html#subprocess.Popen>`_.
    #
    # If the path isn't absolute, work on it.
    if not Path(args[0]).is_absolute():
        args[0] = (
            # If this is a relative path, then prepend cwd.
            str(cwd / args[0])
            # Relative paths have a path separator. Note that `os.altsep <https://docs.python.org/3/library/os.html#os.altsep>`_ may be ``None``.
            if os.sep in args[0] or (os.altsep is not None and os.altsep in args[0])
            # Otherwise, search the PATH. If it's not found, then go with the original value, which should raise an error when subprocess can't find it.
            else shutil.which(args[0]) or args[0]
        )

    # Explain what's going on.
    await co_build("{} > {}\n".format(cwd, " ".join(args)))

    # Start the process.
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=cwd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return (
            "",
            ":: ERROR: CodeChat renderer - when starting render process, unable to find renderer executable '{}'.\n".format(
                args[0] if len(args) > 0 else "<undefined>"
            ),
        )
    except Exception as e:
        return (
            "",
            ":: ERROR: CodeChat renderer - when starting render process, {}.\n".format(
                e
            ),
        )

    # Provide a way to send stdout from the process a line at a time to the web client.
    async def stdout_streamer(stdout_stream: asyncio.StreamReader):
        # Use an `incremental decoder <https://docs.python.org/3/library/codecs.html#codecs.getincrementaldecoder>`_ to decode a stream.
        decoder_ = codecs.getincrementaldecoder("utf-8")(errors="backslashreplace")
        # Wrap than with an incremental decoder for universal newlines. The `docs <https://docs.python.org/3/library/io.html#io.IncrementalNewlineDecoder>`_ are very sparse. From the Visual Studio Code help that pops up (likely from https://github.com/python/cpython/blob/master/Modules/_io/textio.c#L237):
        #
        #   IncrementalNewlineDecoder(decoder: Optional[codecs.IncrementalDecoder], translate: bool, errors: str=...)
        #
        #   Codec used when reading a file in universal newlines mode.
        #   It wraps another incremental decoder, translating \r\n and \r into \n. It also records the types of newlines encountered.  When used with translate=False, it ensures that the newline sequence is returned in one piece. When used with decoder=None, it expects unicode strings as decode input and translates newlines without first invoking an external decoder.
        decoder = io.IncrementalNewlineDecoder(decoder_, True, "")
        while True:
            ret = await stdout_stream.read(80)
            if ret:
                await co_build(decoder.decode(ret))
            else:
                # Tell the decoder the stream is done and collect any last output.
                s = decoder.decode(b"", True)
                if s:
                    await co_build(s)
                break

    # An awaitable sequence to interact with the subprocess.
    aws = [proc.communicate(None if input_text is None else input_text.encode("utf-8"))]

    # If we have an output file, then stream the stdout.
    if stream_stdout:
        assert proc.stdout
        aws.append(stdout_streamer(proc.stdout))
        # Hack: make it look like there's no stdout, so communicate won't use it.
        proc.stdout = None

    # Run the subprocess.
    try:
        (stdout, stderr), *junk = await asyncio.gather(*aws)
    except Exception as e:
        return "", "external command:: ERROR:When running. {}".format(e)

    return (
        stdout.decode("utf-8", errors="backslashreplace") if stdout else "",
        stderr.decode("utf-8", errors="backslashreplace"),
    )


# Select and invoke a renderer
# ============================
# Build a map of file names/extensions to the converter to use.
#
# TODO:
#
# #.    Read this from a StrictYAML file instead.
# #.    Use Pandoc to offer lots of other format conversions.
GLOB_TO_RENDERER: Dict[
    # glob: The glob which accepts files this renderer can process.
    str,
    Tuple[
        # The `renderer`_.
        Callable,
        # An list of parameters used to invoke the renderer.
        Optional[List[Union[bool, str]]],
    ],
] = {glob: (_render_CodeChat, None) for glob in SUPPORTED_GLOBS}
GLOB_TO_RENDERER.update(
    {
        # Leave (X)HTML unchanged.
        "*.xhtml": (_pass_through, None),
        "*.html": (_pass_through, None),
        "*.htm": (_pass_through, None),
        # Use the integrated Python libraries for these.
        "*.md": (_render_markdown, None),
        "*.rst": (_render_ReST, None),
        # External tools
        #
        # `Textile <https://www.promptworks.com/textile>`_:
        "*.textile": (
            _render_external_file,
            [
                # Does this tool read the input file from stdin?
                True,
                # Does this tool produce the output on stdout?
                True,
                # The remaining elements are the arguments used to invoke the tool.
                "pandoc",
                # Specify the input format https://pandoc.org/MANUAL.html#option--to>`_.
                "--from=textile",
                # `Output to HTML <https://pandoc.org/MANUAL.html#option--from>`_.
                "--to=html",
                # `Produce a complete (standalone) HTML file <https://pandoc.org/MANUAL.html#option--standalone>`_, not a fragment.
                "--standalone",
            ],
        ),
    }
)


# Return the converter for the provided file.
def _select_renderer(
    # See file_path_.
    file_path: Path,
) -> Tuple[
    # _`renderer`: a function or coroutine which will perform the render.
    Callable,
    # tool_or_project_config_file_path:
    #
    # - The path to the CodeChat System configuration file if this is a project.
    # - A sequence of parameters used to invoke a single-file renderer if one was found.
    # - None if no renderer was found for ``file_path``.
    Union[str, List[Union[bool, str]], None],
    # is_project: True if this is a project; False if not.
    bool,
]:
    # If this is a directory, start searching there. Otherwise, assume it's a file and remove the file name to produce a directory.
    project_path_search = file_path if file_path.is_dir() else file_path.parent

    # Search for an external builder configuration file. I can't find an equivalent of `parents <https://docs.python.org/3/library/pathlib.html#pathlib.PurePath.parents>`_ that includes the full path, so the list below constructs it.
    for project_path in [project_path_search, *project_path_search.parents]:
        project_config_file_path = project_path / "codechat_config.yaml"
        if project_config_file_path.exists():
            return _render_external_project, str(project_config_file_path), True

    # Otherwise, look for a single-file converter.
    str_file_path = str(file_path)
    for glob, (converter, tool_or_project_config_file_path) in GLOB_TO_RENDERER.items():
        if fnmatch.fnmatch(str_file_path, glob):
            return converter, tool_or_project_config_file_path, False
    return _error_renderer, None, False


# Run the appropriate converter for the provided file or return an error.
async def render_file(
    # _`text`: The text to be converted. If this is a project, the text will be loaded from the disk by the external renderer instead.
    text: str,
    # _`file_path`: The path to the file which (mostly -- see ``is_dirty``) contains this text OR a directory containing a CodeChat project.
    file_path: str,
    # _`html_path`: The html file currently being displayed (if available).
    html_path: Optional[Path],
    # _`co_build`: A coroutine that an external renderer should call to stream build output.
    co_build: Co_Build,
    # True if the provided text hasn't been saved to disk.
    is_dirty: bool,
) -> Tuple[
    # was_performed: True if the render was performed. False if this is a project and the source file is dirty; in this case, the render is skipped.
    bool,
    # project_path: If this is a project, then ``project_path``` contains a path to the CodeChat project configuration file; otherwise, ``project_path`` is ``None``.
    Optional[str],
    # rendered_file_path: A path to the rendered file.
    #
    # - If this is a project, the rendered file is different from ``file_path``, since it points to the location on disk where the external renderer wrote the HTML. In this case, the ``html`` return value is ``None``, since the HTML should be read from the disk instead.
    # - Otherwise, it's the same as the ``file_path``, and the resulting rendered HTML is returned in ``html``.
    str,
    # html: ``None`` for projects, or the resulting HTML otherwise; see the ``rendered_file_path`` return value.
    Optional[str],
    # err_string: A string containing error messages produced by the render.
    str,
]:
    # Determine the renderer for this file/project.
    renderer, tool_or_project_path, is_project = _select_renderer(Path(file_path))

    # Projects require a clean file in order to render.
    if is_project and is_dirty:
        return False, None, "", None, ""

    if asyncio.iscoroutinefunction(renderer):
        # Coroutines get the queue, so they can report progress during the build.
        html_string_or_file_path, err_string = await renderer(
            text, file_path, html_path, tool_or_project_path, co_build
        )
    else:
        assert tool_or_project_path is None
        html_string_or_file_path, err_string = renderer(text, file_path)

    # Update the client's state, now that the rendering is complete.
    if is_project:
        # For projects, the rendered HTML is already on disk; a path to this rendered file is returned.
        return (
            True,
            str(tool_or_project_path),
            html_string_or_file_path,
            None,
            err_string,
        )
    else:
        # Otherwise, the rendered HTML is returned as a string and can be directly used. Provide a path to the source file which was just rendered.
        return True, None, file_path, html_string_or_file_path, err_string
