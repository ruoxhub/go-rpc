# Python版本的Rpc的client
import json
from uuid import uuid4

from tornado import ioloop, iostream

from .Common import _CommonRes, _RpcPacket, AbsRpcConn


def _encode_rpc_fast_json(common_res: _CommonRes) -> bytes:
    msg_part = common_res.message.encode("utf-8") if common_res.message is not None else None
    msg_part_len = (len(msg_part) if msg_part is not None else 0)

    json_part = json.dumps(common_res.data, ensure_ascii=False).encode("utf-8") if common_res.data is not None else None
    json_part_len = len(json_part) if json_part is not None else 0

    result = common_res.status.to_bytes(length=4, byteorder="big", signed=True) + msg_part_len.to_bytes(length=4,
                                                                                                        byteorder="big")
    if msg_part_len > 0:
        result += msg_part
    result += json_part_len.to_bytes(length=4, byteorder="big")
    if json_part_len > 0:
        result += json_part

    return result


class RpcResponse:
    def __init__(self, stream: iostream, seq: int, io_loop: ioloop.IOLoop):
        self._stream = stream
        self._respond = False
        self._seq = seq
        self.io_loop = io_loop

    def success(self, data):
        """
        请注意，data必须可以被json序列化，如果是复合对象，你需要自行转换成dict、list等基础结构，垃圾python
        """
        self._response(_CommonRes().ok(data))

    def failed(self, message: str):
        self._response(_CommonRes().failed(message))

    def _response(self, common_res: _CommonRes):
        if self._respond:
            return
        self._respond = True
        response_pkg = _RpcPacket()
        response_pkg.seq = self._seq
        response_pkg.message_type = 0x11
        response_pkg.add_header("PAYLOAD_CONTENT_TYPE", "CONTENT_TYPE_SEKIRO_FAST_JSON")
        response_pkg.data = _encode_rpc_fast_json(common_res)
        self.io_loop.call_later(0, lambda: response_pkg.write_to(self._stream))

        message = "{\"status\":" + str(common_res.status) + ",\"message\":" + json.dumps(
            common_res.message, ensure_ascii=False) + ",\"data\":" + json.dumps(common_res.data,
                                                                                ensure_ascii=False) + "}"

        print("rpc response: ", message)


class RpcHandler:
    """
    the user handlr
    """

    def handle(self, request: json, response: RpcResponse):
        pass


class RpcClient(AbsRpcConn):
    def __init__(self, group, host="rpc.iinti.cn", port=5612, client_id=None):
        super().__init__(host, port)
        self._group = group
        self._client_id = client_id if client_id is not None else str(uuid4())
        self._handlers = {}
        print("""       welcome to use rpc framework
for more support please visit our website: https://iinti.cn""")

    def _get_handler(self, action: str) -> RpcHandler:
        return self._handlers.get(action)

    def register_action(self, action: str, rpc_handler: RpcHandler):
        self._handlers[action] = rpc_handler

    def make_register_pkg(self) -> _RpcPacket:
        register_cmd = _RpcPacket()
        register_cmd.message_type = 0x10
        register_cmd.seq = -1
        register_cmd.add_header("SEKIRO_GROUP", self._group)
        register_cmd.add_header("SEKIRO_CLIENT_ID", self._client_id)
        return register_cmd

    def handle_packet(self, rpc_packet: _RpcPacket, stream: iostream):
        if rpc_packet.message_type != 0x20:
            print("unknown server msg:%d", rpc_packet.message_type)
            return
        rpc_response = RpcResponse(stream, rpc_packet.seq, self.io_loop)
        if rpc_packet.data is None:
            rpc_response.failed("rpc system error, no request payload present!!")
            return
        request_str = rpc_packet.data.decode("utf-8")
        print("rpc receive request: ", request_str)
        request: dict = json.loads(request_str)
        action = request.get("action")
        if action is None:
            rpc_response.failed("the param: {action} not presented!!")
            return
        handler = self._get_handler(action)
        if handler is None:
            rpc_response.failed("rpc no handler for this action")
            return
        try:
            handler.handle(request, rpc_response)
        except Exception as e:
            print("Error", e)
            rpc_response.failed("failed: " + str(e))
