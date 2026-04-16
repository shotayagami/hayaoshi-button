import asyncio
import protocol


# Per-message send timeout. If a client can't drain a message within this
# window we assume the TCP link is dead.
SEND_TIMEOUT_S = 5.0
# Queue cap per client. If we enqueue faster than the client drains (e.g.
# because the connection is half-dead), drop the client instead of growing
# memory without bound.
QUEUE_LIMIT = 50


class WSManager:
    """WebSocket client manager with per-client send queue and worker task.

    Broadcasts only enqueue (never block on network I/O), and each client has
    a dedicated worker task that drains its queue with a timeout. Dead clients
    are removed individually without stalling the rest.
    """

    def __init__(self):
        # ws -> {"type": ..., "queue": [bytes], "event": Event, "task": Task}
        self.clients = {}

    def add(self, ws, client_type=None):
        info = {
            "type": client_type,
            "queue": [],
            "event": asyncio.Event(),
        }
        self.clients[ws] = info
        info["task"] = asyncio.create_task(self._send_loop(ws))

    def remove(self, ws):
        info = self.clients.pop(ws, None)
        if info:
            task = info.get("task")
            if task:
                try:
                    task.cancel()
                except Exception:
                    pass

    def set_type(self, ws, client_type):
        if ws in self.clients:
            self.clients[ws]["type"] = client_type

    async def _send_loop(self, ws):
        """Dedicated send worker. Exits when the client is removed or a send fails."""
        info = self.clients.get(ws)
        if not info:
            return
        try:
            while ws in self.clients:
                queue = info["queue"]
                if not queue:
                    info["event"].clear()
                    await info["event"].wait()
                    continue
                data = queue.pop(0)
                try:
                    await asyncio.wait_for(ws.send(data), SEND_TIMEOUT_S)
                except Exception as e:
                    print("WS: send failed (%s), dropping client" % type(e).__name__)
                    # Self-remove; skip task.cancel since we're inside the task
                    self.clients.pop(ws, None)
                    return
        except asyncio.CancelledError:
            pass

    async def broadcast(self, msg_dict):
        """Enqueue a message for every connected client. Does not block on I/O."""
        data = protocol.encode(msg_dict)
        for ws in list(self.clients):
            info = self.clients.get(ws)
            if not info:
                continue
            if len(info["queue"]) >= QUEUE_LIMIT:
                print("WS: queue full (%d), dropping slow client" % QUEUE_LIMIT)
                self.clients.pop(ws, None)
                task = info.get("task")
                if task:
                    try:
                        task.cancel()
                    except Exception:
                        pass
                continue
            info["queue"].append(data)
            info["event"].set()

    async def send_to(self, ws, msg_dict):
        """Enqueue a message for a specific client."""
        info = self.clients.get(ws)
        if not info:
            return
        if len(info["queue"]) >= QUEUE_LIMIT:
            self.clients.pop(ws, None)
            task = info.get("task")
            if task:
                try:
                    task.cancel()
                except Exception:
                    pass
            return
        info["queue"].append(protocol.encode(msg_dict))
        info["event"].set()
