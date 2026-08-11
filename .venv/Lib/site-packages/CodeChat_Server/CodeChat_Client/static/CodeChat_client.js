// .. Copyright (C) 2012-2022 Bryan A. Jones.
//
//  This file is part of the CodeChat System.
//
//  The CodeChat System is free software: you can redistribute it and/or
//  modify it under the terms of the GNU General Public License as
//  published by the Free Software Foundation, either version 3 of the
//  License, or (at your option) any later version.
//
//  The CodeChat System is distributed in the hope that it will be
//  useful, but WITHOUT ANY WARRANTY; without even the implied warranty
//  of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
//  General Public License for more details.
//
//  You should have received a copy of the GNU General Public License
//  along with the CodeChat System.  If not, see
//  <http://www.gnu.org/licenses/>.
//
// ***************************************************************************
// |docname| - Core code for the CodeChat Client
// ***************************************************************************
"use strict";

// Constants
// =========
// .. _GetResultType JS:
//
// These must match the `constants in the server <GetResultType Py>`.
const GetResultType = {
    url: 0,
    build: 1,
    errors: 2,
    command: 3,
};

// A regex to match a percentage: one or more digits, optionally followed by a period and one or more digits, and ending with a percent sign.
const percent_regex = new RegExp(
    // Capture the number in front of the percent sign.
    "(" +
        // Look for one or more digits, ...
        "\\d+" +
        // Optionally followed by a decimal point and one ore more digits. (Don't include these in a capture group.)
        "(?:\\.\\d+)?" +
        // End the capture group, then require a percent sign.
        ")%",
    // Search globally (for all matches).
    "g"
);

// Core client
// ===========
// Given an ID to use, run the CodeChat Client.
function run_client(
    // The ID of the CodeChat Client for this window.
    id,
    // The port to use for a websocket connection to the CodeChat Server.
    ws_port
) {
    // Set up variables used by the functions below
    // --------------------------------------------
    // Get commonly-used nodes in the DOM.
    const status_message = document.getElementById("status_message");
    const build_progress = document.getElementById("build_progress");
    const status_errors_div = document.getElementById("status_errors");
    const outputElement = document.getElementById("output");
    const build_div = document.getElementById("build");
    const build_contents = document.getElementById("build_contents");
    const errors_div = document.getElementById("errors");

    // True if the output/errors should be cleared on the next result.
    let clear_output = true;
    // True if the most recent reload was caused by the user; false if this was a programmatic reload.
    let is_user_navigation = false;
    // True if there were warnings or errors in the last build. Initialize to true so that the build messages pane is visible initially.
    let errors_or_warnings = true;
    // The size of the splitter, with a key of ``errors_or_warnings``.
    let splitter_size = {
        true: 85,
        false: 100,
    };

    // Core code
    // ---------
    splitMe.init();
    set_splitter_percent(splitter_size[errors_or_warnings]);

    // Create a websocket to communicate with the CodeChat Server.
    //
    // If the hosting page uses HTTPS, then use a secure websocket (WSS protocol); otherwise, use an insecure websocket (WS).
    const protocol = window.location.protocol === "http:" ? "ws" : "wss";
    // Compute the URI for this websocket, dealing with special cases for CoCalc and GitHub Codespaces.
    let ws_uri;
    const is_cocalc = window.location.hostname === "cocalc.com";
    const is_gihub_codespaces = window.location.hostname.endsWith("github.dev");
    if (is_cocalc || !is_gihub_codespaces) {
        // A special case for CoCalc: use a different URL per the `CoCalc docs <https://doc.cocalc.com/howto/webserver.html>`_.
        const separator = is_cocalc ? "/" : ":";
        // The pathname is all but the last one or two elements of the hosting page's pathname: transform ``/a/long/path/to/the/client`` to ``/a/long/path/to/the``. For CoCalc, this transforms ``/f1d3f8ac-39da-48fe-9357-7d5c4ee132de/server/27377/client`` into ``/f1d3f8ac-39da-48fe-9357-7d5c4ee132de/server``.
        const pathname = window.location.pathname
            .split("/")
            .slice(0, is_cocalc ? -2 : -1)
            .join("/");
        // Transform the hosting page's URL for the websocket. For example, transform from ``http://foo.org/client?id=0`` into ``ws://foo.org:27377``.
        ws_uri = `${protocol}://${window.location.hostname}${pathname}${separator}${ws_port}`;
    } else {
        // We're using GitHub CodeSpaces, where the ``window.location`` is (for example) ``https://bjones1-organic-goggles-wv46gpj9x4cv5qq-27377.preview.app.github.dev/client?id=0``. The desired URI for this example is ``wss://bjones1-organic-goggles-wv46gpj9x4cv5qq-27378.preview.app.github.dev``.
        //
        // Throw away everything after the last hyphen.
        const hostname_prefix = window.location.hostname
            .split("-")
            .slice(0, -1)
            .join("-");
        // Throw away everything before the first period.
        const hostname_suffix = window.location.hostname
            .split(".")
            .slice(1)
            .join(".");
        // Now, build the desired URI.
        ws_uri = `${protocol}://${hostname_prefix}-${ws_port}.${hostname_suffix}`;
    }
    const ws = new ReconnectingWebSocket(ws_uri);

    // Identify this client on connection.
    ws.onopen = () => {
        console.log(
            `CodeChat Client: websocket to CodeChat Server open. Sending ID of ${id}.`
        );
        ws.send(JSON.stringify(id));
    };

    // Provide logging to help track down errors.
    ws.onerror = (event) => {
        console.error(`CodeChat Client: websocket error ${event}.`);
    };

    ws.onclose = (event) => {
        console.log(
            `CodeChat Client: websocket closed by event ${event}. This should only happen on shutdown.`
        );
    };

    // Handle messages.
    ws.onmessage = (event) => {
        const result = JSON.parse(event.data);
        if (result.get_result_type === GetResultType.url) {
            console.log(
                `CodeChat Client: URL ${result.text} received; loading...`
            );
            // Save and restore scroll location through the content update, if we can.
            const [scrollX, scrollY] = getScroll();
            // See ideas in https://stackoverflow.com/a/16822995. Works for same-domain only.
            outputElement.onload = function () {
                if (is_user_navigation) {
                    console.log("CodeChat Client: User navigation.");
                    const outputElement_location =
                        outputElement.contentWindow.window.location;
                    // Only send a message if the navigation occurs in the local server.
                    if (
                        window.location.origin == outputElement_location.origin
                    ) {
                        browser_navigation(outputElement_location.pathname);
                    }
                } else {
                    status_message.innerHTML = "Build complete.";
                    build_progress.style.display = "none";
                    outputElement.classList.remove("building");
                    // Restore the scroll location if we were able to save it.
                    if (scrollX !== undefined && scrollY !== undefined) {
                        this.contentWindow.scrollBy(scrollX, scrollY);
                    }
                    // The programmatic reload is done -- anything else that happens now is from the user.
                    is_user_navigation = true;
                    // Get new content only *after* the load finishes. The case to avoid:
                    //
                    // #.   One load stores the x, y coordinates and begins to load a new page. This sets the scroll bars to 0.
                    // #.   Before the load finishes, another request comes. The x, y coordinates are saved as 0.
                    // #.   The first load finishes, but scrolls to 0, 0; the second load finish does the same.

                    console.log("CodeChat Client: load complete.");
                }
            };

            // Set the new src to (re)load content. At startup, the ``srcdoc`` attribute shows some welcome text. Remove it so that we can now assign the ``src`` attribute.
            outputElement.removeAttribute("srcdoc");
            outputElement.src =
                window.location.protocol +
                "//" +
                window.location.host +
                window.location.pathname +
                "/" +
                id +
                // Windows pathnames don't begin with a slash; Linux/Mac pathnames do. Avoid repeating the slash on Linux/Mac to get prettier URLs.
                (result.text[0] === "/" ? "" : "/") +
                result.text;
            // The next build output received will apply to the new build, so set the flag.
            clear_output = true;
            // See comments above -- avoid double loads and indicate that the is a programmatic reload.
            is_user_navigation = false;
            // Exit for now; the callbacks above will continue this function's operation.
        } else if (result.get_result_type === GetResultType.build) {
            // Omit this logging, since it's usually obvious from the lines below.
            ///console.log("CodeChat Client: received build output.");
            if (clear_output) {
                // This is the start of a new build.
                status_message.innerHTML = "Building...";
                build_progress.style.display = "inline";
                build_progress.removeAttribute("value");
                build_div.textContent = result.text;
                errors_div.textContent = "";
                status_errors_div.innerHTML = "";

                // Save the current splitter state.
                splitter_size[errors_or_warnings] = get_splitter().percent;

                // _`class building`: Show that the current output HTML is old.
                outputElement.classList.add("building");

                clear_output = false;
            } else {
                build_div.textContent += result.text;
            }
            // Look for a percentage, to update the progress bar.
            const percent_matches = result.text.match(percent_regex);
            if (percent_matches !== null) {
                // Update the progress bar with the percentage from the last match.
                build_progress.value = parseFloat(
                    percent_matches[percent_matches.length - 1]
                );
            }
            // Scroll to the bottom, to show the content just added.
            scroll_to_bottom(build_contents);
        } else if (result.get_result_type === GetResultType.errors) {
            console.log("CodeChat Client: error output received.");
            if (clear_output) {
                // There was no build output, so just update the errors.
                build_div.textContent = "";
                errors_div.textContent = result.text;
                // Save the current splitter state.
                splitter_size[errors_or_warnings] = get_splitter().percent;
                clear_output = false;
            } else {
                errors_div.textContent += result.text;
            }
            // Scroll to the bottom, to show the content just added.
            scroll_to_bottom(build_contents);

            // Update the errors/warnings and splitter position.
            [
                errors_div.innerHTML,
                status_errors_div.innerHTML,
                errors_or_warnings,
            ] = parse_for_errors(errors_div.innerHTML);
            set_splitter_percent(splitter_size[errors_or_warnings]);
        } else if (result.get_result_type === GetResultType.command) {
            console.log(`CodeChat Client: command ${result.text} received.`);
            if (result.text === "shutdown") {
                // Close this window -- see https://stackoverflow.com/a/54787080. See `close the window`_.
                outputElement.srcdoc =
                    "<html><body><p>The CodeChat Client was shut down. Please close this window.</p></body></html>";
                build_div.textContent = "";
                errors_div.textContent = "";
                status_message.innerHTML = "Client shut down.";
                window.open("", "_self").close();
                // Stop asking for results.
                ws.close();
                console.log("CodeChat Client: shutdown complete.");
            } else if (result.text.startsWith("error: unknown client ")) {
                // _`Close the window` -- there's no point in asking for more commands. Note: there are some cases where this fails, although I've only seen this once. From the Chrome console, ``Scripts may close only the windows that were opened by them.`` In this case, leave a message asking the user to close the window.
                outputElement.srcdoc =
                    "<html><body><p>CodeChat Client error: lost connection to the CodeChat Server. Close this window and restart the editor plug-in.</p></body></html>";
                build_div.textContent = "";
                errors_div.textContent = "";
                status_message.innerHTML = "Server disconnected";
                window.open("", "_self").close();
                // Stop asking for results.
                ws.close();
                console.log(
                    `CodeChat Client: shutdown complete due to unknown client; saw ${result.text}.`
                );
            } else {
                console.log(`CodeChat Client: Unknown command ${result.text}.`);
            }
        } else {
            console.log(
                `CodeChat Client: Unknown GetResultType: ${result.get_result_type}.`
            );
        }
    };

    // Provide utility functions for use by the core functions above
    // -------------------------------------------------------------

    // Return the X and Y coordinates of the scrollbar of the output iframe if possible.
    function getScroll() {
        try {
            // This is only allowed for same-domain origins -- for example, if the user clicks on a link in the docs that goes to an external website, then the following lines will raise an exception.
            return [
                outputElement.contentWindow.scrollX,
                outputElement.contentWindow.scrollY,
            ];
        } catch (err) {
            return [undefined, undefined];
        }
    }

    // Send a message to the CodeChat server.
    function send_to_codechat_server(
        // A string, identifying the type of message.
        msg,
        // Message-specific data to send. Must be JSON-encodable.
        data
    ) {
        ws.send(JSON.stringify([msg, data]));
    }

    // These functions define _`messages sent by the CodeChat Client`, which are handled by `read_websocket_handler <read_websocket_handler>`. Defining them this way makes them accessible to the iframe and globally (to functions called outside this function). See below.
    //
    // Save data to the filesystem. Right now, only used for pretext editing.
    save_file = function (xml_node, file_contents) {
        send_to_codechat_server("save_file", {
            xml_node: xml_node,
            file_contents: file_contents,
        });
    };

    // The ``var`` statement below makes some of these accessible globally.
    navigate_to_error = function (file_path, line) {
        send_to_codechat_server("navigate_to_error", {
            file_path: file_path,
            line: line,
        });
    };

    browser_navigation = function (pathname) {
        send_to_codechat_server("browser_navigation", {
            pathname: pathname,
        });
    };
}

// Globally-accessible functions (see above). These must be declared as ``var`` (not ``let``) due to (I assume) scoping rules I don't understand.
var navigate_to_error, save_file, browser_navigation;

// Utilities
// =========
// Get the splitter element.
function get_splitter() {
    return document.getElementById("splitter");
}

// Set the splitter percentage
function set_splitter_percent(percent) {
    const splitter = get_splitter();
    splitter.percent = percent;
    splitMe.update(splitter);
}

// Scroll an element to the bottom
function scroll_to_bottom(element) {
    element.scrollTop = element.scrollHeight - element.clientHeight;
}

// This regex parses the error string to determine get the number of warnings and errors.
//
// prettier-ignore
const error_regex = new RegExp(
    // Don't capture this group (the ``?:``).
    "(?:" +
        // Common docutils error messages read:
        //
        // .. code:: none
        //  :number-lines:
        //
        //  <string>:1589: (ERROR/3) Unknown interpreted text role "ref".
        //  X:\ode.py:docstring of sympy:5: (ERROR/3) Unexpected indentation.
        //
        // Common Sphinx errors read:
        //
        // .. code:: none
        //  :number-lines:
        //
        //  X:\SVM_train.m.rst:2: SEVERE: Title overline & underline mismatch.
        //  X:\index.rst:None: WARNING: image file not readable: a.jpg
        //  X:\conf.py.rst:: WARNING: document isn't included in any toctree
        //  # In Sphinx 1.6.1:
        //  X:\file.rst: WARNING: document isn't included in any toctree
        //
        // The CodeChat renderer also produces `error messages <checkModificationTime>`_ formatted in a similar way so they'll be identified by the same regex:
        //
        // .. code:: none
        //  :number-lines:
        //
        //  X:\ode.py:: ERROR: CodeChat renderer - source file older than the html file X:\_build\html\ode.py.
        //
        // Each error/warning occupies one line. The following `regular
        // expression <https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Regular_Expressions>`_ is designed to find the error position (1589/None) and message type (ERROR/WARNING/SEVERE). Extra spaces are added to show which parts of the example string it matches.
        //
        // Examining the following expression one element at a time:
        //
        // .. code::
        //  :number-lines:
        //
        //   <string>:1589:        (ERROR/3)Unknown interpreted text role "ref".
        //
        // The filename is anything up to the colon. Windows filenames may begin with a drive letter followed by a colon -- don't capture this (the leading ``?:``).
        "^((?:\\w:)?[^:]*)" +
            // Find the first occurrence of a pair of colons, or just a single colon. Between them there can be numbers or "None" or nothing. For example, this expression matches the string ":1589:" or string ":None:" or the string "::" or the string ":".
            ":(\\d*|None):? " +
            // Next match the error type, which can only be "WARNING", "ERROR" or "SEVERE". Before this error type the message may optionally contain one left parenthesis.
            "\\(?(WARNING|ERROR|SEVERE)" +
            // Since one error message occupies one line, a ``*`` quantifier is used along with end-of-line ``$`` to make sure only the first match is used in each line.
            ".*$" +
    // Start another non-capturing group (the ``?:``).
    ")|(?:" +
        // PreText CLI messages are very simple:
        //
        // .. code:: none
        //  :number-lines:
        //
        //  critical: StartTag: invalid element name, line 8, column 6
        //  error: stuff stuff
        //  warning: Using CLI version 2.3.0 but project's `requirements.txt`
        "^(critical: |error: |warning: )" +
    ")",
    // The message usually contains multiple lines; search each line for errors and warnings.
    "m" +
    // The global flag must be present to find all occurrences.
    "g"
);

// Parse the error output for errors and warnings.
function parse_for_errors(errors_html) {
    let errNum = 0;
    let warningNum = 0;
    // The replacement function is called with the match text then each matched group.
    errors_html = errors_html.replace(
        error_regex,
        function (
            match_text,
            file_path,
            line,
            error_string,
            pretext_error_string
        ) {
            if (
                error_string === "ERROR" ||
                error_string === "SEVERE" ||
                pretext_error_string === "critical: " ||
                pretext_error_string === "error: "
            ) {
                ++errNum;
            } else if (
                error_string === "WARNING" ||
                pretext_error_string === "warning: "
            ) {
                ++warningNum;
            }

            // Unsanitize the file name.
            const div = document.createElement("div");
            div.innerHTML = file_path;
            file_path = div.textContent;
            // Make an unspecified filename empty.
            if (file_path === "<string>") {
                file_path = "";
            }

            // Clean up the line.
            if (line === "None" || line === "") {
                line = -1;
            }

            // Create a hyperlink to navigate to the error.
            return `<a href='javascript:navigate_to_error(${JSON.stringify(
                file_path
            )}, ${line})' class="error_link">${match_text}</a>`;
        }
    );

    // Report these results to the user.
    let span_class;
    if (errNum) {
        span_class = "have_errors";
    } else if (warningNum) {
        span_class = "have_warnings";
    } else {
        span_class = "no_errors_or_warnings";
    }
    return [
        errors_html,
        `<span class="${span_class}">Error(s): ${errNum}, warning(s): ${warningNum}</span>`,
        errNum + warningNum > 0,
    ];
}
