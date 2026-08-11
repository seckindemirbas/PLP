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
# **************************************************
# |docname| - Render manager for the CodeChat Server
# **************************************************
# The render manager takes rendering requests send from the Thrift interface of the CodeChat Server, renders them, then sends the results to the associated CodeChat Client.
#
# Imports
# =======
# Library imports
# ---------------
import asyncio
from enum import Enum
import logging
import json
from pathlib import Path
import sys
from typing import (
    Any,
    cast,
    Callable,
    Coroutine,
    Dict,
    Optional,
    Union,
)
import urllib.parse
import xml.dom.minidom

# Third-party imports
# -------------------
from lxml import etree as ElementTree
import websockets.asyncio.server

# Local imports
# -------------
from .constants import WEBSOCKET_PORT
from .renderer import is_win, ProjectConfFile, render_file


# RenderManager / render thread
# ==============================
logger = logging.getLogger(__name__)


# .. _GetResultType Py:
#
# These must match the `constants in the client <GetResultType JS>`.
class GetResultType(Enum):
    # A URL indicating that new rendered content is available.
    url = 0
    # A build output message.
    build = 1
    # Errors from the build.
    errors = 2
    # A command, such as ``shutdown```.
    command = 3


# Utilities
# =========
def GetResultReturn(get_result_type: GetResultType, text: str):
    return {"get_result_type": get_result_type.value, "text": text}


# Convert a path to a URI component: make it absolute and use forward (POSIX) slashes. If the provided ``file_path`` is falsey, just return it.
def path_to_uri(file_path: str):
    return Path(file_path).resolve().as_posix() if file_path else file_path


# Store data for about each client. This is a combination of data about the editor/IDE client and the associated CodeChat Client.
class ClientState:
    def __init__(self):
        # A queue of messages for the CodeChat Client.
        self.q: asyncio.Queue = asyncio.Queue()

        # The remaining data in this class should only be accessed by the rendering thread.
        #
        # The most recent HTML and editor text after rendering the specified file_path.
        self._html: Optional[str] = None
        self._editor_text: Optional[str] = None
        self._file_path: Optional[str] = None
        # The path to the CodeChat project configuration file if this is a project; None otherwise.
        self._project_path: Optional[str] = None

        # A flag to indicate if this has been placed in the renderer's job queue.
        self._in_job_q: bool = False
        # A flag to indicate that this client has work to perform.
        self._needs_processing: bool = True

        # A bucket to hold text and the associated file to render.
        self._to_render_editor_text: Optional[str] = None
        self._to_render_file_path: Optional[str] = None
        self._to_render_is_dirty: Optional[bool] = None

        # A bucket to hold a sync request.
        #
        # The index into either the editor text or HTML converted to text.
        self._to_sync_index: Optional[int] = None
        self._to_sync_from_editor: Optional[int] = None
        # The HTML converted to text.
        self._html_as_text: Optional[str] = None

        # Shutdown is tricky; see `this discussion <shut down an editor client>`.
        #
        # A flag to request the worker to delete this client.
        self._is_deleting: bool = False


# Use the contents of the provided ClientState to perform a render.
async def render_client_state(cs: ClientState) -> None:
    # Provide a coroutine used by converters to write build results.
    def co_build(_str: str) -> Coroutine[Any, Any, None]:
        return cs.q.put(
            GetResultReturn(
                GetResultType.build,
                _str,
            )
        )

    (
        is_converted,
        project_path,
        rendered_file_path,
        html,
        err_string,
    ) = await render_file(
        cast(str, cs._to_render_editor_text),
        cast(str, cs._to_render_file_path),
        Path(cs._file_path) if cs._file_path else None,
        co_build,
        cast(bool, cs._to_render_is_dirty),
    )

    if not is_converted:
        return

    cs._project_path = project_path
    cs._file_path = rendered_file_path
    cs._html = html
    cs._editor_text = cs._to_render_editor_text

    # Send any errors. An empty error string will clear any errors from a previous build, and should still be sent.
    await cs.q.put(GetResultReturn(GetResultType.errors, err_string))

    # Sending the HTML signals the end of this build.
    #
    # For Windows, make the path contain forward slashes.
    uri = path_to_uri(cs._file_path)
    # Encode this, for Windows paths which contain a colon (or unusual Linux paths).
    await cs.q.put(GetResultReturn(GetResultType.url, urllib.parse.quote(uri)))


class RenderManager:
    def __init__(self, shutdown_event):
        self.shutdown_event = shutdown_event
        self._is_shutdown = False

    # Provide a way to perform thread-safe access of methods in this class.
    def __getattr__(self, name: str) -> Callable:
        if name.startswith("threadsafe_"):
            # Strip off ``threadsafe`` and look for the function.
            internal_func = self.__getattr__(name[11:])

            # Invoke it as an async if needed.
            async def async_wrap(*args, **kwargs):
                return internal_func(*args, **kwargs)

            # See if we need to wrap this in an async.
            async_func = (
                internal_func
                if asyncio.iscoroutinefunction(internal_func)
                else async_wrap
            )

            # Wrap the async func in a threadsafe call.
            def threadsafe_async(*args, **kwargs):
                future = asyncio.run_coroutine_threadsafe(
                    async_func(*args, **kwargs), self._loop
                )
                return future.result()

            return threadsafe_async

        # Not found. Let Python raise the exception for us.
        return self.__getattribute__(name)

    # Determine if the provided id exists and is not being deleted. Return the ClientState for the id if so; otherwise, return False.
    def get_client_state(self, id: int) -> Union[bool, ClientState]:
        cs = self._client_state_dict.get(id)
        # Signal an error if this client doesn't exist or is being deleted; otherwise, return it.
        return cs if cs and not cs._is_deleting else False

    # Add the provided client to the job queue.
    def _enqueue(self, id: int) -> None:
        # Add to the job queue unless it's already there.
        cs = self._client_state_dict[id]
        cs._needs_processing = True
        if not cs._in_job_q:
            self._job_q.put_nowait(id)
            cs._in_job_q = True

    # Create a new client. Returns the client id on success or False on failure. The client may optionally provide an id for a new client.
    def create_client(self, id: Optional[int] = None) -> int:
        if self._is_shutdown:
            return -1
        if id is None:
            self._last_id += 1
            id = self._last_id
        if id in self._client_state_dict:
            # Indicate failure if this id exists.
            return False
        self._client_state_dict[id] = ClientState()
        return id

    # `<-- <Delete step 3.>` _`Delete step 4.` `--> <Delete step 5.>` _`delete_client`: Request a worker to delete this MultiClient.
    def delete_client(self, id: int) -> bool:
        cs = self.get_client_state(id)
        if not cs:
            return False
        assert isinstance(cs, ClientState)
        # Tell the worker to delete this. We can't simply delete it now, since it may be in the middle of a render. Allowing the worker to delete it ensures it's in a safe (unused) state for deletion.
        self._enqueue(id)
        # Prevent any new entries in the queue by setting this flag; see ``get_client_state``.
        cs._is_deleting = True
        return True

    # Place the item in the render queue; must be called from another (non-render) thread. Returns True on success, or False if the provided id doesn't exist.
    def start_render(
        self, editor_text: str, file_path: str, id: int, is_dirty: bool
    ) -> bool:
        cs = self.get_client_state(id)
        if not cs:
            # Signal an error for an invalid client id.
            return False
        assert isinstance(cs, ClientState)

        # Add to the job queue.
        self._enqueue(id)

        # Update the job parameters.
        cs._to_render_editor_text = editor_text
        cs._to_render_file_path = file_path
        cs._to_render_is_dirty = is_dirty

        # Indicate success
        return True

    # Get a CodeChat Client's queue.
    def get_queue(self, id: int) -> Optional[asyncio.Queue]:
        cs = self.get_client_state(id)
        return cast(ClientState, cs).q if cs else None

    # Return the results of rendering the provided URL:
    #
    # - If the URL matches with the latest render, return the resulting HTML for a non-project render. Return ``None`` for a project render, indicating that the render was stored to disk and the URL is a path to the rendered file.
    # - If there's no match to the URL or the ID doesn't exist, return False. Note that the "HTML" can be None, meaning
    def get_render_results(self, id: int, url_path: str) -> Union[None, str, bool]:
        cs = self.get_client_state(id)
        return (
            cast(ClientState, cs)._html
            if cs
            and path_to_uri(cast(str, cast(ClientState, cs)._file_path)) == url_path
            else False
        )

    # Communicate with a CodeChat Client via a websocket.
    async def websocket_handler(
        self, websocket: websockets.asyncio.server.ServerConnection
    ):
        # First, read this client's ID.
        try:
            data = await websocket.recv()
        except websockets.exceptions.WebSocketException:
            # Give up if there's a websocket error.
            return

        # Find the queue for this CodeChat Client.
        try:
            id_ = json.loads(data)
        except json.decoder.JSONDecodeError:
            id_ = f"<invalid id {repr(data)}>"
        q = self.get_queue(id_)
        if not q:
            try:
                await websocket.send(
                    json.dumps(
                        GetResultReturn(
                            GetResultType.command, f"error: unknown client {id_}."
                        )
                    )
                )
            except websockets.exceptions.WebSocketException:
                # Ignore any errors here, since we're closing the socket anyway.
                pass
            return

        # Start one task to get read results from the websocket.
        read_websocket_handler = asyncio.create_task(
            self.read_websocket_handler(websocket, id_)
        )

        # Send messages until shutdown. However, this function should typically never exit using this conditional; instead, the shutdown code below should break out of the loop.
        q_task = asyncio.create_task(q.get())
        socket_closed_task = asyncio.create_task(websocket.wait_closed())
        while not self._is_shutdown:
            done, pending = await asyncio.wait(
                [q_task, socket_closed_task], return_when=asyncio.FIRST_COMPLETED
            )
            # If the socket was closed, wrap up.
            if socket_closed_task in done:
                # Stop waiting on the queue.
                q_task.cancel()
                break
            # The usual case: we have data to send over the websocket.
            if q_task in done:
                ret = q_task.result()
                # Prepare for the next run.
                q_task = asyncio.create_task(q.get())
                try:
                    await websocket.send(json.dumps(ret))
                except websockets.exceptions.WebSocketException:
                    # An error occurred -- close the websocket. The client will open another, so we can try again.
                    return

                # Delete the client if this was a shutdown command.
                if (ret["get_result_type"] == GetResultType.command.value) and (
                    ret["text"] == "shutdown"
                ):
                    # `<-- <Delete step 2.>` _`Delete step 3.` `--> <Delete step 4.>` The MultiClient must be kept working until it sends the CodeChat Client a shutdown message. The message is sent, so we can now delete the MultiClient.
                    logger.info(f"Sent shutdown command to CodeChat Client id {id_}.")
                    # Check that the queue is empty
                    if not q.empty():
                        logger.warning(
                            f"CodeChat warning: CodeChat Client id {id_} shut down with pending commands."
                        )
                    # Request MultiClient deletion.
                    assert self.delete_client(id_)
                    # Shut down this websocket.
                    break

        # Wait for the read to shut down.
        if not read_websocket_handler.done():
            await read_websocket_handler
        logger.info(f"Websocket for CodeChat Client id {id_} exiting.")

    # _`read_websocket_handler`: this responds to `messages sent by the CodeChat Client <messages sent by the CodeChat Client>`.
    async def read_websocket_handler(
        self, websocket: websockets.asyncio.server.ServerConnection, id_: int
    ):
        while not self._is_shutdown:
            try:
                ret = await websocket.recv()
            except websockets.exceptions.WebSocketException:
                # If anything breaks, exit.
                return

            msg, data = json.loads(ret)
            if msg == "save_file":
                print(
                    f"Save to {data['xml_node']} values:\n{data['file_contents'][:77]}..."
                )
                # Get the location of the project file.
                csd = self._client_state_dict[id_]
                pp = csd._project_path
                if not pp:
                    print("Unable to save: no project file available.")
                    continue
                # Read the source path from it.
                project_conf = ProjectConfFile(
                    Path(pp), Path(cast(str, csd._file_path))
                )
                # Find the source file which matches this mapping.
                xml_id_to_replace = data["xml_node"]
                for (
                    source_file,
                    xml_id_list,
                ) in project_conf.load_pretext_mapping().items():
                    if xml_id_to_replace in xml_id_list:
                        try:
                            # Load in this source.
                            src_tree = ElementTree.parse(source_file)
                            # Parse the replacement source for it.
                            new_node = ElementTree.fromstring(data["file_contents"])
                        except Exception as e:
                            print(f"Unable to load file or parse new source: {e}")
                            break
                        # Find the node in this source file and replace it. Find only looks at children, so manually check the root element.
                        xml_id_attrib = "{http://www.w3.org/XML/1998/namespace}id"
                        xml_node_to_replace = (
                            src_tree.getroot()
                            if src_tree.getroot().get(xml_id_attrib)
                            == xml_id_to_replace
                            else src_tree.find(
                                f"//*[@{xml_id_attrib} = '{xml_id_to_replace}']"
                            )
                        )
                        if xml_node_to_replace is None:
                            print(
                                f"Unable to save: can't find node {xml_node_to_replace} in {source_file}."
                            )
                            break
                        # The correct method to replace this node is either ``_setroot`` (this is is the root element) or ``replace`` (otherwise).
                        parent = xml_node_to_replace.getparent()
                        if parent is None:
                            src_tree._setroot(new_node)
                        else:
                            parent.replace(xml_node_to_replace, new_node)
                        # Save the updated file. I can't find a way using lxml (including looking at the `docinfo <https://lxml.de/api/lxml.etree.DocInfo-class.html>`_ class) to determine if the loaded document contained an XML declaration (the ``<?xml version="1.0" encoding="UTF-8"?>`` header) or not. The following comes from `SO <https://stackoverflow.com/a/54942605/16038919>`__.
                        has_xml_declaration = bool(
                            xml.dom.minidom.parse(source_file).version
                        )
                        src_tree.write(
                            source_file,
                            encoding="utf-8",
                            xml_declaration=has_xml_declaration,
                        )
                        print(f"Saved to {source_file}.")
                        break
                else:
                    print(
                        f"Unable to write: can't find source file containing {xml_id_to_replace}."
                    )
            elif msg == "navigate_to_error":
                # TODO
                print(
                    f"TODO: navigate to error on line {data['line']} of file {data['file_path']}."
                )
            elif msg == "browser_navigation":
                # TODO
                print(f"TODO: browser navigation to {data['pathname']}.")
                # Translate the path from a URL to a Path, removing the expected prefix of ``/client/id/``.
                pathname_raw = urllib.parse.unquote(data["pathname"])
                expected_pathname_prefix = f"/client/{id_}/"
                assert pathname_raw.startswith(expected_pathname_prefix)
                pathname = Path(pathname_raw[len(expected_pathname_prefix) :])

                # Update the HTML path
                cs = self._client_state_dict[id_]
                cs._file_path = str(pathname)

                # Get the location of the project file. TODO
                pp = cs._project_path
                if pp:
                    # For projects, we need to find the source file that maps to this HTML pathname.
                    pass
            else:
                print(f"Error: unknown message {msg} with data '{data}'.")

    # `<-- <Delete step 1.>` _`Delete step 2.` `--> <Delete step 3.>` Begin the MultiClient shutdown process by sending a shutdown message to the CodeChat Client.
    async def shutdown_client(self, id: int) -> bool:
        q = self.get_queue(id)
        # Fail if the ID is unknown.
        if not q:
            return False
        # Send the shutdown command to the CodeChat Client.
        await q.put(GetResultReturn(GetResultType.command, "shutdown"))
        # In case the CodeChat Client is dead, shut down after a delay.
        asyncio.create_task(self._delete_client_later(id))
        # Indicate success.
        return True

    # Delete a CodeChat Client after a delay.
    async def _delete_client_later(self, id: int):
        await asyncio.sleep(1)
        if self.delete_client(id):
            logger.warning(f"CodeChat Client {id} not responding -- deleted it.")

    # Shut down the render manager, called from another thread.
    def threadsafe_shutdown(self):
        # If the shutdown is in progress, don't do it again.
        if self._is_shutdown:
            return
        # We can't wait for a result, since this causes the asyncio event loop to exit, but the result must be retrieved from a Future running within the event loop. Therefore, call without waiting.
        self._loop.call_soon_threadsafe(asyncio.create_task, self.shutdown())

    # Shut down the render manager.
    async def shutdown(self):
        logger.info("Render manager shutting down...")
        assert not self._is_shutdown
        self._is_shutdown = True

        # Request a shutdown for each MultiClient.
        for id in self._client_state_dict.keys():
            # The await doesn't mean the shut down is complete, but only that the request was made.
            await self.shutdown_client(id)

        # Wait for all MultiClients to shut down. Special case: if the server never created a MultiClient, then skip this.
        logger.info("Waiting for client shutdown...")
        if len(self._client_state_dict):
            await self._MultiClients_deleted.wait()

        # Shut down the websocket, since only the MultiClient can use it.
        logger.info("Waiting for websocket server to close...")
        self.websocket_server.close()
        await self.websocket_server.wait_closed()

        # Shut the workers down now that the MultiClients have shut down.
        logger.info("Shutting down workers...")
        for i in range(self._num_workers):
            await self._job_q.put(None)

    # Start the render manager.
    def run(self, *args, debug: bool = True, **kwargs) -> None:
        # The default Windows event loop doesn't support asyncio subprocesses.
        if is_win:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

        try:
            asyncio.run(self._run(*args, **kwargs), debug=debug)
        except Exception:
            # If something goes wrong, don't try a clean shutdown of this thread, since the event loop already died. This must precede the event below, so that when the main thread tries calling ``threadsafe_shutdown``, this flag is already set.
            self._is_shutdown = True
            # Shut the server down instead of hanging.
            self.shutdown_event.set()
            raise
        logger.info("Render manager is shut down.")

    # Run the rendering thread with the given number of workers.
    async def _run(self, server_host, num_workers: int = 1) -> None:
        self._num_workers = num_workers
        # Create a queue of jobs for the renderer to process. This must be created from within the main loop to avoid ``got Future <Future pending> attached to a different loop`` errors.
        self._job_q: asyncio.Queue = asyncio.Queue()
        # Keep a dict of id: ClientState for each client.
        self._client_state_dict: Dict[int, ClientState] = {}
        # The next ID will be 0.
        self._last_id = -1
        self._loop = asyncio.get_running_loop()
        self._is_shutdown = False
        self._MultiClients_deleted = asyncio.Event()

        self.websocket_server = await websockets.serve(  # type:ignore
            self.websocket_handler, server_host, WEBSOCKET_PORT
        )
        # _`CODECHAT_READY`: let the user know that the server is now ready -- this is the last piece of it to start.
        #
        # NOTE: The ``CodeChat_Server start`` CLI command reads this line, then quits. This means (on Windows at least) that all future ``print`` statements will block, preventing the server from shutting down. Outputing info to the logger avoids this problem. Therefore, **do not include print statements after this point in the code**.
        print("The CodeChat Server is ready.\nCODECHAT_READY", file=sys.stderr)
        # Flush this since extension and test code waits for it before connecting to the server/running the rest of a test.
        sys.stderr.flush()
        await asyncio.gather(*[self._worker(i) for i in range(num_workers)])

    # Process items in the render queue.
    async def _worker(self, worker_index: int) -> None:
        while True:
            # Get an item to process.
            id = await self._job_q.get()
            # Check for shutdown.
            if id is None:
                logger.info(f"Render worker {worker_index} is shut down.")
                break
            cs = self._client_state_dict[id]
            assert cs._in_job_q
            # Every item in the queue should have some work to do.
            assert cs._needs_processing
            # Indicate that the current jobs in this ClientState will all be completed.
            cs._needs_processing = False

            # If the client should be deleted, ignore all other requests.
            if cs._is_deleting:
                # `<-- <Delete step 4.>` _`Delete step 5.` Now, the deletion can safely proceed. Done.
                del self._client_state_dict[id]
                # If there are no more MultiClients, shut down and signal that shutdown can proceed.
                if len(self._client_state_dict) == 0:
                    self.shutdown_event.set()
                    # Indicate that all MultiClients have been deleted; shutdown can now proceed.
                    assert not self._MultiClients_deleted.is_set()
                    self._MultiClients_deleted.set()
            else:
                # Sync first.
                # TODO: sync.

                # Render next.
                await render_client_state(cs)

                # If this client received more work to do while working on the current job, add it back to the queue -- it can't safely be added to the queue while the job is in process. Otherwise, we would potentially allow two workers to render the same job in parallel, which would confuse the renderer.
                if cs._needs_processing:
                    self._job_q.put_nowait(id)
                else:
                    cs._in_job_q = False
