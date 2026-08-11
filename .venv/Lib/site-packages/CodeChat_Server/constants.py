# *********************
# |docname| - Constants
# *********************

from .gen_py.CodeChat_Services.constants import THRIFT_PORT

# The port used for an HTTP connection from the CodeChat Client to the CodeChat Server.
HTTP_PORT = THRIFT_PORT + 1

# The port used by a websocket connection between the CodeChat Server and the CodeChat Client.
WEBSOCKET_PORT = HTTP_PORT + 1

# The network address used by all servers in the CodeChat Server.
LOCALHOST = "127.0.0.1"
