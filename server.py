from microdot import Microdot
from microdot.websocket import with_websocket
import protocol


CONTENT_TYPES = {
    "html": "text/html",
    "css": "text/css",
    "js": "application/javascript",
    "mp3": "audio/mpeg",
    "png": "image/png",
    "ico": "image/x-icon",
}


def create_app(game, ws_mgr):
    app = Microdot()

    # Serve static files from www/
    @app.route("/")
    async def index(request):
        return await _serve_file("www/display.html", "text/html")

    @app.route("/admin")
    async def admin(request):
        return await _serve_file("www/admin.html", "text/html")

    # WebSocket endpoint (must be before catch-all)
    @app.route("/ws")
    @with_websocket
    async def websocket_handler(request, ws):
        print("WS: client connected")
        ws_mgr.add(ws)
        try:
            state_msg = game.get_state_msg()
            print(f"WS: sending state: {state_msg}")
            await ws_mgr.send_to(ws, state_msg)
            print("WS: state sent OK")

            while True:
                data = await ws.receive()
                if data is None:
                    break
                print(f"WS: recv: {data}")
                msg = protocol.decode(data)
                await _handle_message(ws, msg, game, ws_mgr)
                print(f"WS: handled {msg.get('type')}")
        except Exception as e:
            print(f"WS: error: {e}")
        finally:
            ws_mgr.remove(ws)
            print("WS: client disconnected")

    # Static files (catch-all, must be last)
    @app.route("/<path:path>")
    async def static_files(request, path):
        ext = path.rsplit(".", 1)[-1] if "." in path else ""
        content_type = CONTENT_TYPES.get(ext, "application/octet-stream")
        return await _serve_file(f"www/{path}", content_type)

    return app


async def _serve_file(filepath, content_type):
    try:
        with open(filepath, "rb") as f:
            content = f.read()
        return content, 200, {"Content-Type": content_type}
    except OSError:
        return "Not Found", 404


async def _handle_message(ws, msg, game, ws_mgr):
    msg_type = msg.get("type")

    if msg_type == protocol.MSG_REGISTER:
        ws_mgr.set_type(ws, msg.get("client_type"))

    elif msg_type == protocol.MSG_SET_NAME:
        await game.set_player_name(msg["player_id"], msg["name"])

    elif msg_type == protocol.MSG_SET_SCORE:
        await game.set_player_score(msg["player_id"], msg["score"])

    elif msg_type == protocol.MSG_ARM:
        await game.arm()

    elif msg_type == protocol.MSG_JUDGE:
        await game.judge(msg["result"])

    elif msg_type == protocol.MSG_C2S_RESET:
        await game.reset()

    elif msg_type == protocol.MSG_SETTINGS:
        await game.update_settings(msg)
