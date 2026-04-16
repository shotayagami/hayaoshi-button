import protocol


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
        for ws in self.clients:
            try:
                await ws.send(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.remove(ws)

    async def send_to(self, ws, msg_dict):
        try:
            await ws.send(protocol.encode(msg_dict))
        except Exception:
            self.remove(ws)
