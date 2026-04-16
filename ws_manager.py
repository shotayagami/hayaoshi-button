import asyncio
import protocol


# Max time to wait for a single ws.send() before assuming the client is dead.
# Prevents button polling from hanging on half-dead TCP connections.
SEND_TIMEOUT_S = 2.0


class WSManager:
    def __init__(self):
        self.clients = {}  # ws -> {"type": "admin"|"display"}

    def add(self, ws, client_type=None):
        self.clients[ws] = {"type": client_type}

    def remove(self, ws):
        self.clients.pop(ws, None)

    def set_type(self, ws, client_type):
        if ws in self.clients:
            self.clients[ws]["type"] = client_type

    async def broadcast(self, msg_dict):
        data = protocol.encode(msg_dict)
        dead = []
        # Snapshot to avoid mutation during iteration
        for ws in list(self.clients):
            try:
                await asyncio.wait_for(ws.send(data), SEND_TIMEOUT_S)
            except Exception as e:
                print(f"WS: broadcast drop ({type(e).__name__})")
                dead.append(ws)
        for ws in dead:
            self.remove(ws)

    async def send_to(self, ws, msg_dict):
        try:
            await asyncio.wait_for(ws.send(protocol.encode(msg_dict)), SEND_TIMEOUT_S)
        except Exception:
            self.remove(ws)
