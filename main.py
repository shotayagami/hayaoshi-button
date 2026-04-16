import json
import asyncio
import os
import socket
import ssl
import wifi
import protocol
from microdot import Microdot
from microdot.microdot import Request
from microdot.websocket import with_websocket
from buttons import ButtonManager
from game import GameEngine
from ws_manager import WSManager
from dfplayer import DFPlayer

Request.max_content_length = 200 * 1024  # 200KB
# max_body_length stays at 16KB - larger files use streaming


CONTENT_TYPES = {
    "html": "text/html",
    "css": "text/css",
    "js": "application/javascript",
    "mp3": "audio/mpeg",
}


def load_config():
    with open("config.json", "r") as f:
        return json.load(f)


def save_config(cfg):
    with open("config.json", "w") as f:
        json.dump(cfg, f)


def serve_file(filepath, content_type):
    import gc
    try:
        stat = os.stat(filepath)
        size = stat[6]
    except OSError:
        return "Not Found", 404

    if size <= 8192:
        # Small files: read into memory
        with open(filepath, "rb") as f:
            content = f.read()
        return content, 200, {"Content-Type": content_type}

    # Large files: stream in chunks
    def file_stream():
        gc.collect()
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(2048)
                if not chunk:
                    break
                yield chunk
        gc.collect()

    return file_stream(), 200, {
        "Content-Type": content_type,
        "Content-Length": str(size),
    }


# Load config and connect Wi-Fi
config = load_config()
wlan, wifi_mode = wifi.auto_connect(config)
ip = wifi.get_ip(wlan)
print(f"Mode: {wifi_mode.upper()}")
print(f"Admin:   http://{ip}/admin")
print(f"Display: http://{ip}/")

# Notify IP via Discord webhook (STA mode only)
def notify_discord(ip_addr):
    if wifi_mode != "sta":
        return
    webhook_url = config.get("discord_webhook", "")
    if not webhook_url:
        return
    try:
        _, _, host_path = webhook_url.split("/", 2)
        host, path = host_path.split("/", 1)
        path = "/" + path
        body_bytes = json.dumps({
            "content": f"Hayaoshi started! ({wifi_mode})\nAdmin: http://{ip_addr}/admin\nDisplay: http://{ip_addr}/"
        }).encode()
        s = socket.socket()
        s.settimeout(5)
        ai = socket.getaddrinfo(host, 443)[0]
        s.connect(ai[-1])
        ss = ssl.wrap_socket(s)
        header = (
            f"POST {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(body_bytes)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )
        ss.write(header.encode())
        ss.write(body_bytes)
        resp = ss.read(128)
        print(f"Discord notify: {resp[:50]}")
        ss.close()
        s.close()
    except Exception as e:
        print(f"Discord notify failed: {e}")

notify_discord(ip)

# Initialize components
num_players = config.get("num_players", 8)
buttons = ButtonManager(num_players=num_players)
ws_mgr = WSManager()
game = GameEngine(
    num_players=num_players,
    points_correct=config.get("points_correct", 10),
    points_incorrect=config.get("points_incorrect", -5),
)
dfp = DFPlayer()
game.set_broadcast(ws_mgr.broadcast)
game.set_buttons(buttons)
game.set_dfplayer(dfp)
buttons.set_player_callback(game.on_player_press)
buttons.set_host_callback(game.on_host_press)

# Restore saved settings
if "colors" in config:
    game.colors = config["colors"]
if "revival" in config:
    game.revival = config["revival"]
if "max_accepts" in config:
    game.max_accepts = config["max_accepts"]
if "jingle_auto_arm" in config:
    game.jingle_auto_arm = config["jingle_auto_arm"]
if "countdown_auto_stop" in config:
    game.countdown_auto_stop = config["countdown_auto_stop"]
if "penalty_rounds" in config:
    game.penalty_rounds = config["penalty_rounds"]
if "batch_mode" in config:
    game.batch_mode = config["batch_mode"]
if "batch_use_order" in config:
    game.batch_use_order = config["batch_use_order"]
if "batch_points" in config:
    game.batch_points = config["batch_points"]

# Config save callback
def on_save_config(key, value):
    config[key] = value
    save_config(config)

game.set_save_config(on_save_config)

# Create app
app = Microdot()

@app.route("/")
async def index(req):
    return serve_file("www/display.html", "text/html")

@app.route("/admin")
async def admin(req):
    return serve_file("www/admin.html", "text/html")

@app.route("/setup")
async def setup(req):
    return serve_file("www/setup.html", "text/html")

@app.route("/api/config", methods=["GET"])
async def get_config(req):
    safe = {
        "wifi_ssid": config.get("wifi_ssid", ""),
        "ap_ssid": config.get("ap_ssid", "HayaoshiButton"),
        "ap_password": config.get("ap_password", "hayaoshi1234"),
        "wifi_mode": wifi_mode,
        "ip": ip,
    }
    return json.dumps(safe), 200, {"Content-Type": "application/json"}

@app.route("/api/config", methods=["POST"])
async def post_config(req):
    try:
        body = json.loads(req.body.decode())
        if "wifi_ssid" in body:
            config["wifi_ssid"] = body["wifi_ssid"]
        if "wifi_password" in body:
            config["wifi_password"] = body["wifi_password"]
        if "ap_ssid" in body:
            config["ap_ssid"] = body["ap_ssid"]
        if "ap_password" in body:
            config["ap_password"] = body["ap_password"]
        save_config(config)
        return json.dumps({"status": "ok", "message": "Saved. Reboot to apply."}), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}), 400, {"Content-Type": "application/json"}

@app.route("/api/reboot", methods=["POST"])
async def reboot(req):
    import machine
    machine.reset()

@app.route("/ws")
@with_websocket
async def websocket_handler(req, ws):
    print("WS: connected")
    ws_mgr.add(ws)
    try:
        await ws_mgr.send_to(ws, game.get_state_msg())
        while True:
            data = await ws.receive()
            if data is None:
                break
            msg = protocol.decode(data)
            msg_type = msg.get("type")

            if msg_type == "register":
                ws_mgr.set_type(ws, msg.get("client_type"))
            elif msg_type == "set_name":
                await game.set_player_name(msg["player_id"], msg["name"])
            elif msg_type == "set_score":
                await game.set_player_score(msg["player_id"], msg["score"])
            elif msg_type == "arm":
                await game.arm()
            elif msg_type == "stop":
                await game.stop()
            elif msg_type == "judge":
                await game.judge(msg["result"])
            elif msg_type == "batch_judge":
                await game.batch_judge(
                    msg.get("correct_ids", []),
                    sound=msg.get("sound", "correct"),
                )
            elif msg_type == "reset":
                await game.reset()
            elif msg_type == "clear_penalty":
                await game.clear_penalty()
            elif msg_type == "reset_scores":
                await game.reset_scores()
            elif msg_type == "reset_round":
                await game.reset_round()
            elif msg_type == "set_round":
                await game.set_round(int(msg.get("value", 0)))
            elif msg_type == "settings":
                await game.update_settings(msg)
            elif msg_type == "jingle":
                if dfp.is_ready():
                    dfp.play_sound(dfp.SOUND_JINGLE)
                await ws_mgr.broadcast({"type": "jingle"})
                if game.jingle_auto_arm:
                    await game.arm()
            elif msg_type == "countdown":
                if dfp.is_ready():
                    dfp.play_sound(dfp.SOUND_COUNTDOWN)
                await game.start_countdown()
            elif msg_type == "set_colors":
                await game.set_colors(msg["colors"])
            elif msg_type == "audio_mode":
                dfp.enabled = msg.get("dfplayer", True)
                await ws_mgr.broadcast({"type": "audio_mode", "display": msg.get("display", False)})
    except Exception as e:
        print(f"WS: error: {e}")
    finally:
        ws_mgr.remove(ws)
        print("WS: disconnected")

@app.route("/api/upload/<path:filename>", methods=["POST"])
async def upload_sound(req, filename):
    import gc
    gc.collect()
    try:
        filepath = f"www/sounds/{filename}"
        cl = req.content_length or 0
        if cl == 0:
            return json.dumps({"status": "error", "message": "Empty file"}), 400, {"Content-Type": "application/json"}

        written = 0
        with open(filepath, "wb") as f:
            if req.body and len(req.body) > 0:
                # Small file: body already buffered
                f.write(req.body)
                written = len(req.body)
            else:
                # Large file: read from stream in chunks
                stream = req.stream
                remaining = cl
                while remaining > 0:
                    chunk = await stream.read(min(remaining, 2048))
                    if not chunk:
                        break
                    f.write(chunk)
                    written += len(chunk)
                    remaining -= len(chunk)

        gc.collect()
        print(f"Uploaded: {filepath} ({written} bytes)")
        return json.dumps({"status": "ok", "message": f"Saved ({written}B)"}), 200, {"Content-Type": "application/json"}
    except Exception as e:
        print(f"Upload error: {e}")
        return json.dumps({"status": "error", "message": str(e)}), 500, {"Content-Type": "application/json"}

@app.route("/<path:path>")
async def static_files(req, path):
    ext = path.rsplit(".", 1)[-1] if "." in path else ""
    content_type = CONTENT_TYPES.get(ext, "application/octet-stream")
    return serve_file(f"www/{path}", content_type)

async def run():
    await dfp.init()
    asyncio.create_task(buttons.poll_loop())
    print("Button polling started.")
    print("System ready.")
    await app.start_server(host="0.0.0.0", port=80, debug=True)

asyncio.run(run())
