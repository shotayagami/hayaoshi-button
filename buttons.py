from machine import Pin, PWM
import time
import asyncio


class ButtonManager:
    DEBOUNCE_US = 20_000  # 20ms
    PWM_FREQ = 1000
    BRIGHTNESS_FULL = 65535
    BRIGHTNESS_DIM = 6500
    BRIGHTNESS_OFF = 0

    # Lamp modes
    MODE_OFF = 0
    MODE_DIM = 1
    MODE_FULL = 2
    MODE_BLINK_DIM = 3
    MODE_BLINK_FULL = 4

    BLINK_INTERVAL_MS = 300

    def __init__(self, num_players=8):
        self.num_players = num_players

        # Player buttons (active LOW with pull-up)
        # GP0-GP3, GP26, GP27, GP6, GP7 (GP4/GP5 reserved for UART1/DFPlayer)
        PLAYER_GPIOS = [0, 1, 2, 3, 26, 27, 6, 7]
        self.player_pins = [
            Pin(PLAYER_GPIOS[i], Pin.IN, Pin.PULL_UP) for i in range(num_players)
        ]

        # Player lamps: GP8-GP15 (PWM output)
        self.lamp_pwms = []
        for i in range(num_players):
            pwm = PWM(Pin(i + 8))
            pwm.freq(self.PWM_FREQ)
            pwm.duty_u16(0)
            self.lamp_pwms.append(pwm)

        # Host buttons
        self.host_pins = {
            "correct": Pin(16, Pin.IN, Pin.PULL_UP),
            "incorrect": Pin(17, Pin.IN, Pin.PULL_UP),
            "reset": Pin(18, Pin.IN, Pin.PULL_UP),
            "arm": Pin(19, Pin.IN, Pin.PULL_UP),
            "stop": Pin(20, Pin.IN, Pin.PULL_UP),
            "jingle": Pin(21, Pin.IN, Pin.PULL_UP),
            "countdown": Pin(22, Pin.IN, Pin.PULL_UP),
        }

        # Debounce tracking
        self._player_last_us = [0] * num_players
        self._player_prev = [1] * num_players  # Previous state (1=released)
        self._host_last_us = {k: 0 for k in self.host_pins}
        self._host_prev = {k: 1 for k in self.host_pins}

        # Per-player lamp mode
        self._lamp_mode = [self.MODE_OFF] * num_players

        # Blink task
        self._blink_task = None
        self._blink_on = True  # Current blink phase

        # Flash task tracking
        self._flash_task = None

        # Callbacks
        self._on_player_press = None
        self._on_host_press = None

    def set_player_callback(self, callback):
        """callback(player_id: int, timestamp_us: int)"""
        self._on_player_press = callback

    def set_host_callback(self, callback):
        """callback(button_name: str)"""
        self._on_host_press = callback

    # --- Lamp mode setters ---

    def lamp_full(self, player_id):
        if 0 <= player_id < self.num_players:
            self._lamp_mode[player_id] = self.MODE_FULL
            self.lamp_pwms[player_id].duty_u16(self.BRIGHTNESS_FULL)

    def lamp_dim(self, player_id):
        if 0 <= player_id < self.num_players:
            self._lamp_mode[player_id] = self.MODE_DIM
            self.lamp_pwms[player_id].duty_u16(self.BRIGHTNESS_DIM)

    def lamp_off(self, player_id):
        if 0 <= player_id < self.num_players:
            self._lamp_mode[player_id] = self.MODE_OFF
            self.lamp_pwms[player_id].duty_u16(self.BRIGHTNESS_OFF)

    def lamp_blink_full(self, player_id):
        if 0 <= player_id < self.num_players:
            self._lamp_mode[player_id] = self.MODE_BLINK_FULL
            self.lamp_pwms[player_id].duty_u16(self.BRIGHTNESS_FULL)
            self._ensure_blink_task()

    def lamp_blink_dim(self, player_id):
        if 0 <= player_id < self.num_players:
            self._lamp_mode[player_id] = self.MODE_BLINK_DIM
            self.lamp_pwms[player_id].duty_u16(self.BRIGHTNESS_DIM)
            self._ensure_blink_task()

    def all_lamps_off(self):
        for i in range(self.num_players):
            self._lamp_mode[i] = self.MODE_OFF
            self.lamp_pwms[i].duty_u16(self.BRIGHTNESS_OFF)
        self._stop_blink_task()

    def stop_blink(self):
        """Stop all blinking, keep non-blink modes unchanged."""
        for i in range(self.num_players):
            if self._lamp_mode[i] in (self.MODE_BLINK_FULL, self.MODE_BLINK_DIM):
                self._lamp_mode[i] = self.MODE_OFF
                self.lamp_pwms[i].duty_u16(self.BRIGHTNESS_OFF)
        self._stop_blink_task()

    # Backward compatibility
    def lamp_on(self, player_id):
        self.lamp_full(player_id)

    def start_blink(self, player_id, interval_ms=300):
        self.lamp_blink_full(player_id)

    # --- Blink loop ---

    def _ensure_blink_task(self):
        if self._blink_task is None:
            self._blink_task = asyncio.create_task(self._blink_loop())

    def _stop_blink_task(self):
        if self._blink_task:
            self._blink_task.cancel()
            self._blink_task = None
            self._blink_on = True

    async def _blink_loop(self):
        try:
            while True:
                await asyncio.sleep(self.BLINK_INTERVAL_MS / 1000)
                self._blink_on = not self._blink_on
                has_blinkers = False
                for i in range(self.num_players):
                    mode = self._lamp_mode[i]
                    if mode == self.MODE_BLINK_FULL:
                        has_blinkers = True
                        brightness = self.BRIGHTNESS_FULL if self._blink_on else self.BRIGHTNESS_OFF
                        self.lamp_pwms[i].duty_u16(brightness)
                    elif mode == self.MODE_BLINK_DIM:
                        has_blinkers = True
                        brightness = self.BRIGHTNESS_DIM if self._blink_on else self.BRIGHTNESS_OFF
                        self.lamp_pwms[i].duty_u16(brightness)
                if not has_blinkers:
                    break
        except asyncio.CancelledError:
            pass
        self._blink_task = None

    # --- Flash (celebration) ---

    async def flash_lamp(self, player_id, times=3, interval_ms=200):
        for _ in range(times):
            self.lamp_pwms[player_id].duty_u16(self.BRIGHTNESS_FULL)
            await asyncio.sleep(0.001 * interval_ms)
            self.lamp_pwms[player_id].duty_u16(self.BRIGHTNESS_OFF)
            await asyncio.sleep(0.001 * interval_ms)

    # --- Polling loop ---

    async def poll_loop(self):
        # Handlers are dispatched as fire-and-forget tasks so polling never
        # blocks on network I/O (e.g., a half-dead WebSocket client).
        while True:
            now = time.ticks_us()

            # Poll player buttons (edge detection)
            for i in range(self.num_players):
                val = self.player_pins[i].value()
                prev = self._player_prev[i]
                self._player_prev[i] = val
                if val == 0 and prev == 1:  # falling edge
                    if time.ticks_diff(now, self._player_last_us[i]) > self.DEBOUNCE_US:
                        self._player_last_us[i] = now
                        if self._on_player_press:
                            asyncio.create_task(self._on_player_press(i, now))

            # Poll host buttons (edge detection: trigger once on press)
            for name, pin in self.host_pins.items():
                val = pin.value()
                prev = self._host_prev[name]
                self._host_prev[name] = val
                if val == 0 and prev == 1:  # falling edge: just pressed
                    if time.ticks_diff(now, self._host_last_us[name]) > self.DEBOUNCE_US:
                        self._host_last_us[name] = now
                        if self._on_host_press:
                            asyncio.create_task(self._on_host_press(name))

            await asyncio.sleep(0.001)
