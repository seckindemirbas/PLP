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
# ***********************************
# |docname| - Run the CodeChat Server
# ***********************************
# This parses command-line parameters then invokes the requested CodeChat System functionality.
#
# Imports
# =======
# These are listed in the order prescribed by `PEP 8
# <http://www.python.org/dev/peps/pep-0008/#imports>`_.
#
# Standard library
# ----------------
import asyncio
import os
from pathlib import Path
import shutil
import sys
import subprocess
import threading
from time import sleep
from typing import List, Optional, Sequence

# Third-party imports
# -------------------
import json5
import psutil
from thrift.transport import TSocket
from thrift.transport import TTransport
from thrift.protocol import TBinaryProtocol
import typer
from watchdog.observers import Observer
from watchdog.events import FileSystemEvent, PatternMatchingEventHandler

# Local application imports
# -------------------------
from . import __version__
from .constants import LOCALHOST, THRIFT_PORT
from .gen_py.CodeChat_Services import EditorPlugin
from .gen_py.CodeChat_Services.ttypes import (
    CodeChatClientLocation,
)


# Utilities
# =========
def get_client() -> EditorPlugin.Client:
    socket = TSocket.TSocket(LOCALHOST, THRIFT_PORT)
    transport = TTransport.TBufferedTransport(socket)
    protocol = TBinaryProtocol.TBinaryProtocol(transport)
    client = EditorPlugin.Client(protocol)
    transport.open()
    return client


# Return the file's contents if it exists, or an empty string if not.
def file_text(path_to_file: Path) -> str:
    try:
        with open(path_to_file, encoding="utf-8", errors="backslashreplace") as f:
            return f.read()
    except Exception:
        return ""


# Watcher client
# ==============
# Provide a simple class to invoke a build when the file system watcher sends an event.
class WatcherClient:
    def __init__(
        self,
        directories: Sequence[Path],
        patterns: List[str],
        ignore_patterns: List[str],
    ):
        self.observer = Observer()
        self.thrift_client = get_client()

        # Request a client ID.
        try:
            ret = self.thrift_client.get_client(CodeChatClientLocation.browser)
        except ConnectionResetError as e:
            typer.echo(f"Unable to connect to the CodeChat Server: {e}.", err=True)
            sys.exit(1)
        if ret.error:
            typer.echo(
                f"Error connecting to the CodeChat Server: {ret.error}.",
                err=True,
            )
            sys.exit(1)
        assert ret.html == ""
        self.client_id = ret.id

        # See the `docs <https://watchdog.readthedocs.io/en/latest/api.html#watchdog.events.PatternMatchingEventHandler>`__. Rather than derive a separate class, just add a method to this instance.
        self.event_handler = PatternMatchingEventHandler(
            patterns=patterns, ignore_patterns=ignore_patterns
        )
        self.event_handler.on_any_event = self.on_any_event  # type: ignore

        for pathname in set(directories):
            # See the `docs <https://watchdog.readthedocs.io/en/latest/api.html#watchdog.observers.api.BaseObserver.schedule>`__.
            self.observer.schedule(self.event_handler, str(pathname), recursive=True)
        self.observer.start()
        typer.echo(
            f"Watcher started, monitoring the path(s) {directories} containing patterns {patterns} but ignoring {ignore_patterns}.",
        )

    # See the `docs <https://watchdog.readthedocs.io/en/latest/api.html#watchdog.events.FileSystemEventHandler.on_any_event>`__.
    def on_any_event(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            typer.echo(f"{event}, {str(event.src_path)}", err=True)
            src_path = Path(str(event.src_path)).absolute()
            with open(src_path, encoding="utf-8", errors="backslashreplace") as f:
                try:
                    ret = self.thrift_client.start_render(
                        f.read(), str(src_path), self.client_id, False
                    )
                except TTransport.TTransportException as e:
                    typer.echo(
                        f"Unable to communicate with the CodeChat Server when requesting a render: {e}.",
                        err=True,
                    )
                    self.running = False
                else:
                    if ret:
                        typer.echo(
                            f"Error requesting a render from the CodeChat Server: {ret}.",
                            err=True,
                        )
                        self.running = False

    def run(self) -> None:
        self.running = True
        try:
            while self.running:
                sleep(1)
        except KeyboardInterrupt:
            pass
        self.shutdown()

    def shutdown(self) -> None:
        typer.echo("Watcher shutting down...")
        try:
            ret = self.thrift_client.stop_client(self.client_id)
        except TTransport.TTransportException as e:
            typer.echo(
                f"Unable to communicate when the CodeChat Server when shutting down the CodeChat Client: {e}.",
                err=True,
            )
        else:
            if ret:
                typer.echo(f"Error shutting down the CodeChat Client: {ret}.", err=True)
        self.observer.stop()
        self.observer.join()
        typer.echo("Watcher shut down.")


# .. _CLI interface:
#
# CLI interface
# =============
app = typer.Typer()


# Add a ``--version`` optional globally.
def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"The CodeChat Server, v.{__version__}")
        sys.exit(0)


@app.callback()
def common(
    version: Optional[bool] = typer.Option(
        None, "--version", callback=version_callback, is_eager=True
    ),
) -> None:
    pass


INSECURE_HELP = "Setting this True allows the webserver and websocket to accept connections from any address (they bind to 0.0.0.0). This is extremely dangerous and insecure. If enabled, these ports should be firewalled and carefully protected. This mode is offered to support remote development using Visual Studio Code, which provides a secure (SSH-based) connection. The default value of False allows only connections from the machine this program runs on."


@app.command()
def start(
    insecure: bool = typer.Option(False, help=INSECURE_HELP),
    coverage: bool = typer.Option(False, help="Run with code coverage enabled."),
) -> None:
    "Start the server."

    sys.exit(_start(insecure, coverage))


# Typer's default arguments don't work when called directly from Python. This avoid provides a function which returns a value (0 for success, a non-zero value for failure), instead of calling ``sys.exit()``. The following CLI functions follow this pattern as well.
def _start(insecure: bool = False, coverage: bool = False) -> int:
    typer.echo(
        "Starting the server -- searching for an already-running instance...",
    )

    # Try pinging the server to see if it's up.
    try:
        client = get_client()
        assert client.ping() == ""
        typer.echo("A running CodeChat Server instance was found.")
        return 0
    except Exception:
        typer.echo("No running CodeChat Server instances found.")

    # The server isn't up or has crashed. Stop any existing instances in case it crashed.
    ret = _stop()
    if ret:
        return ret

    # Start the server, now that any hung instances are terminated.
    cov_args = ["-m", "coverage", "run"] if coverage else []
    args = ["--insecure"] if insecure else []
    p = subprocess.Popen(
        [sys.executable, *cov_args, "-m", "CodeChat_Server", "serve", "--quiet", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Terminate the server after 5 seconds if it doesn't start.
    server_starting = True

    def timeout():
        sleep(10)
        if server_starting:
            p.terminate()
            typer.echo(
                "The server failed to start before the timeout expired.",
                err=True,
            )

    # Make this a daemon thread, so it will exit when the main thread finishes.
    timeout_thread = threading.Thread(target=timeout, daemon=True)
    timeout_thread.start()

    # Wait for the server to start.
    typer.echo("Waiting for the server to start...")
    out = ""
    line = ""
    while "CODECHAT_READY\n" not in line:
        # To make mypy happy.
        assert p.stderr is not None
        p.stderr.flush()
        line = p.stderr.readline()
        out += line
        typer.echo(line, nl=False)
        if p.poll() is not None:
            # The server shut down. Print the output collected to help the user understand what went wrong.
            #
            # Make mypy happy.
            assert p.stdout is not None
            typer.echo(p.stdout.read())
            typer.echo(p.stderr.read(), err=True)
            typer.echo("The server exited unexpectedly.", err=True)
            return 1
        sleep(0.001)
    # Indicate the server started to the timeout thread, so the timeout won't kill the server now that it's started.
    server_starting = False
    return 0


@app.command()
def stop() -> None:
    "Stop the server."
    sys.exit(_stop())


def _stop() -> int:
    typer.echo("Stopping all CodeChat Server instances...")
    # Look for the server. TODO: should I avoid hard-coding this?
    server_name = "CodeChat_Server"
    ret = 0
    # This code was copied from the `psutil docs <https://psutil.readthedocs.io/en/latest/#find-process-by-name>`_ then lightly modified.
    for p in psutil.process_iter(["cmdline", "exe", "name", "pid"]):
        if (
            server_name == p.info["name"]
            or p.info["exe"]
            and os.path.basename(p.info["exe"]) == server_name
            or p.info["cmdline"]
            # On Windows, sometimes the process cmdline contains ``C:\...\venv\Scripts\CodeChat_Server-script.py``. So, we need to search inside each of the cmdline strings.
            and any([server_name in x for x in p.info["cmdline"]])
        ) and (
            # Don't kill the current process (its parent is often a Python launcher).
            p.pid != os.getpid()
            and p.pid != os.getppid()
            # If we have the command line, then "serve" must be in it.
            and (not p.info["cmdline"] or "serve" in p.info["cmdline"])
        ):
            typer.echo(
                f"Killing server process {p.pid} named {p.info['name']} with command line {p.info['cmdline']}.",
            )
            # Killing the parent of a CodeChat Server process will kill the child; ignore the exception in this case.
            try:
                p.kill()
            except psutil.NoSuchProcess:
                pass
            except Exception as e:
                typer.echo(f"Unable to kill: {e}.", err=True)
                ret = 1

    return ret


@app.command()
def serve(
    insecure: bool = typer.Option(False, help=INSECURE_HELP),
    quiet: bool = typer.Option(False, help="Omit diagnostic messages."),
) -> None:
    "Run the server in the current terminal/console."

    # This file takes a long time to load and run. Print a status message as it starts.
    typer.echo("Loading...")
    from .server import run_servers

    sys.exit(run_servers(insecure, quiet))


@app.command()
def build(path_to_build: List[Path]) -> None:
    "Build the specified CodeChat project(s)."

    from .renderer import render_file

    async def aprint(_str):
        typer.echo(_str, err=True, nl=False)

    # Build each path provided.
    for ptb in path_to_build:
        ptb = ptb.resolve()
        # In this function, send ALL status messages to stderr, so that a build can produce only the build output to stdout.
        typer.echo(f"Building {ptb}...", err=True)
        (
            was_performed,
            rendered_project_path,
            rendered_file_path,
            html,
            err_string,
        ) = asyncio.run(render_file(file_text(ptb), str(ptb), None, aprint, False))
        assert was_performed
        # Print all errors produced by the render.
        typer.echo(err_string, err=True)
        # Dump the HTML produced.
        if html is None:
            typer.echo(
                f"The rendered result is stored in {rendered_file_path}.",
                err=True,
            )
        else:
            if ptb.is_file():
                typer.echo(html)
            else:
                typer.echo(
                    f"Error: file {ptb} not found, and no containing project to render was found.",
                    err=True,
                )
                sys.exit(1)


@app.command()
def render(path_to_build: Path, id: int) -> None:
    "Render the specified CodeChat project in a web browser."

    typer.echo(f"Rendering {path_to_build} using ID {id}.")
    ret = _start()
    if ret:
        sys.exit(ret)

    # Ensure the ID is negative.
    id = -abs(id) - 1

    # Request a render.
    path_to_build = path_to_build.resolve()
    thrift_client = get_client()
    thrift_client.start_render(file_text(path_to_build), str(path_to_build), id, False)


@app.command()
def watch(
    paths: List[Path] = typer.Option(
        [Path(".")], help="Directory(s) to watch for changes."
    ),
    patterns: List[str] = typer.Option(
        ["*"], help="Patterns of files to watch in the provided directory(s)."
    ),
    ignore_patterns: List[str] = typer.Option(
        [], help="Patterns of files to ignore in the provided directory(s)."
    ),
) -> None:
    "Watch the specified directories; perform a render when a matching file is changed."

    ret = _start()
    if ret:
        sys.exit(ret)

    wc = WatcherClient(paths, patterns, ignore_patterns)
    wc.run()


@app.command()
def vscode_install():
    """Install the CodeChat Server extension (see https://marketplace.visualstudio.com/items?itemName=CodeChat.codechat) into the Visual Studio Code editor, and set the extension's path to point to this CodeChat Server executable.

    Note: Visual Studio Code must be installed before running this command.
    """

    # This follows the `Python recommendations <https://docs.python.org/3/library/sys.html#sys.platform>`_.
    is_win = sys.platform == "win32"
    is_linux = sys.platform.startswith("linux")
    is_darwin = sys.platform == "darwin"

    # Install the VSCode extension.
    vscode_executable = shutil.which("code")
    if vscode_executable is None:
        print(
            "Error: unable to find the Visual Studio Code executable in the path. Note that\n"
            "Visual Studio Code must be installed and in the path before running this command."
        )
        if is_darwin:
            print(
                "See https://code.visualstudio.com/docs/setup/mac for instructions on updating\n"
                "the path to contain VSCode."
            )
        raise typer.Exit(1)
    cmd = [vscode_executable, "--install-extension", "CodeChat.codechat"]
    print(f"Installing the CodeChat Visual Studio Code extension...\n  {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

    print("Configuring the CodeChat extension...")
    # See the `VSCode docs <https://code.visualstudio.com/docs/getstarted/settings>`_.
    if is_win:
        settings_file = Path(f"{os.environ['APPDATA']}/Code/User/settings.json")
    elif is_linux:
        settings_file = Path(f"{os.environ['HOME']}/.config/Code/User/settings.json")
    elif is_darwin:
        settings_file = Path(
            f"{os.environ['HOME']}/Library/Application\\ Support/Code/User/settings.json"
        )
    else:
        print("Unsupported operating system.")
        raise typer.Exit(1)

    # Read the current settings (if they exist).
    try:
        settings_contents = settings_file.read_text()
    except FileNotFoundError:
        settings_contents = "{}"

    # Update the CodeChat Server command. We use the ``json5`` package -- the settings file is actually JSON5. TODO: the current json5 implementation discards comments without a lot of `complexity <https://json-five.readthedocs.io/en/latest/comments.html>`_. Find a way to keep comments when writing the file back out.
    settings = json5.loads(settings_contents)
    settings["CodeChat.CodeChatServer.Command"] = str(Path(sys.argv[0]).absolute())

    # Write the results back.
    settings_file.write_text(json5.dumps(settings, indent=4))
    print("Success.")


if __name__ == "__main__":
    app()
