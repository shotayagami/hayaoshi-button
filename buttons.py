from machine import Pin, PWM
import time
import asyncio
import micropython

# Reserve space so exceptions raised in IRQ context can be reported.
micropython.alloc_emergency_exception_buf(100)


PLAYER_GPIOS = [0, 1, 2, 3, 26, 27, 6, 7]
HOST_GPIOS = {
    "correct": 16,
    "incorrect": 17,
    "reset": 18,
    "arm": 19,
    "stop": 20,
    "jingle": 21,
    "countdown": 22,
}
HOST_NAMES = list(HOST_GPIOS.keys())


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

    # Auto-recovery: if a pin reads 0 for this long without any edge, assume
    # prev got stuck and reset it so the next press can fire cleanly.
    STUCK_LOW_TIMEOUT_US = 10_000_000  # 10 seconds
    # Periodically re-initialize Pin objects to refresh pull-up config.
    REFRESH_PERIOD_S = 30

    def __init__(self, num_players=8):
        self.num_players = num_players

        # Player buttons (active LOW with pull-up)
        self.player_pins = []
        for i in range(num_players):
            pin = Pin(PLAYER_GPIOS[i], Pin.IN, Pin.PULL_UP)
            self.player_pins.append(pin)

        # Player lamps: GP8-GP15 (PWM output)
        self.lamp_pwms = []
        for i in range(num_players):
            pwm = PWM(Pin(i + 8))
            pwm.freq(self.PWM_FREQ)
            pwm.duty_u16(0)
            self.lamp_pwms.append(pwm)

        # Host buttons
        self.host_pins = {}
        for name, gp in HOST_GPIOS.items():
            self.host_pins[name] = Pin(gp, Pin.IN, Pin.PULL_UP)

        # Debounce / state tracking
        self._player_last_us = [0] * num_players
        self._player_prev = [1] * num_players
        self._player_low_since = [0] * num_players  # for stuck-low recovery
        self._host_last_us = {k: 0 for k in self.host_pins}
        self._host_prev = {k: 1 for k in self.host_pins}
        self._host_low_since = {k: 0 for k in self.host_pins}

        # Pre-allocated pending flags (set from ISR, consumed in scheduled ctx)
        self._player_press_pending = [False] * num_players
        self._player_press_ts = [0] * num_players
        self._host_press_pending = {k: False for k in self.host_pins}
        self._host_press_ts = {k: 0 for k in self.host_pins}

        # Per-player lamp mode
        self._lamp_mode = [self.MODE_OFF] * num_players

        # Blink task
        self._blink_task = None
        self._blink_on = True

        # Flash task tracking
        self._flash_task = None

        # Callbacks
        self._on_player_press = None
        self._on_host_press = None

        # Bound dispatch (re-used from micropython.schedule — must not allocate)
        self._dispatch_ref = self._dispatch_pending

        # Install IRQs
        self._install_irqs()

    def _install_irqs(self):
        for i in range(self.num_players):
            self.player_pins[i].irq(
                trigger=Pin.IRQ_FALLING,
                handler=self._make_player_irq(i),
            )
        for name in HOST_NAMES:
            self.host_pins[name].irq(
                trigger=Pin.IRQ_FALLING,
                handler=self._make_host_irq(name),
            )

    def _make_player_irq(self, idx):
        # Closure captures idx. Created once at setup; handler itself runs in ISR context.
        def handler(pin):
            now = time.ticks_us()
            # ticks_diff is signed; a negative value means ticks_us wrapped past
            # last_us (>~9 min gap on RP2). Treat only small positive diffs as
            # "too recent" (real debounce); everything else is a legitimate press.
            diff = time.ticks_diff(now, self._player_last_us[idx])
            if 0 < diff <= self.DEBOUNCE_US:
                return
            self._player_last_us[idx] = now
            self._player_press_ts[idx] = now
            self._player_press_pending[idx] = True
            try:
                micropython.schedule(self._dispatch_ref, 0)
            except RuntimeError:
                # Schedule queue full — next IRQ will retry, or poll fallback
                pass
        return handler

    def _make_host_irq(self, name):
        def handler(pin):
            now = time.ticks_us()
            diff = time.ticks_diff(now, self._host_last_us[name])
            if 0 < diff <= self.DEBOUNCE_US:
                return
            self._host_last_us[name] = now
            self._host_press_ts[name] = now
            self._host_press_pending[name] = True
            try:
                micropython.schedule(self._dispatch_ref, 0)
            except RuntimeError:
                pass
        return handler

    def _dispatch_pending(self, _):
        # Runs outside ISR (via micropython.schedule). Safe to allocate / spawn tasks.
        for i in range(self.num_players):
            if self._player_press_pending[i]:
                self._player_press_pending[i] = False
                ts = self._player_press_ts[i]
                print("P%d edge (irq)" % (i + 1))
                if self._on_player_press:
                    asyncio.create_task(self._on_player_press(i, ts))
        for name in HOST_NAMES:
            if self._host_press_pending[name]:
                self._host_press_pending[name] = False
                print("Host edge: %s (irq)" % name)
                if self._on_host_press:
                    asyncio.create_task(self._on_host_press(name))

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

    # --- Diagnostic / Recovery ---

    async def diagnostic_loop(self, period_s=10):
        """Periodically dump pin states."""
        import gc
        while True:
            await asyncio.sleep(period_s)
            try:
                pvals = [self.player_pins[i].value() for i in range(self.num_players)]
                hvals = {n: p.value() for n, p in self.host_pins.items()}
                print("DIAG player val=%s prev=%s" % (pvals, self._player_prev))
                print("DIAG host   val=%s prev=%s" % (hvals, self._host_prev))
                print("DIAG mem_free=%d" % gc.mem_free())
            except Exception as e:
                print("DIAG error: %s" % e)

    async def watchdog_loop(self):
        """Track state for release logging, stuck-low recovery, and periodic pin refresh.

        Press detection is handled by IRQs. This loop is a safety net:
        - Logs rising edges (releases) for observability
        - Detects pins stuck low for >STUCK_LOW_TIMEOUT_US and forces recovery
        - Periodically re-initializes Pin objects + IRQs to refresh config
        """
        last_refresh_ms = time.ticks_ms()
        while True:
            now = time.ticks_us()

            # --- Player button state tracking ---
            for i in range(self.num_players):
                val = self.player_pins[i].value()
                prev = self._player_prev[i]
                self._player_prev[i] = val
                if val == 1 and prev == 0:
                    # Release: clear stuck-low counter
                    self._player_low_since[i] = 0
                    print("P%d release" % (i + 1))
                elif val == 0:
                    if self._player_low_since[i] == 0:
                        self._player_low_since[i] = now
                    elif time.ticks_diff(now, self._player_low_since[i]) > self.STUCK_LOW_TIMEOUT_US:
                        # Stuck-low recovery: force next press to be edge-detectable
                        print("P%d stuck-low recovery" % (i + 1))
                        self._player_prev[i] = 1
                        self._player_low_since[i] = 0
                else:
                    self._player_low_since[i] = 0

            # --- Host button state tracking ---
            for name, pin in self.host_pins.items():
                val = pin.value()
                prev = self._host_prev[name]
                self._host_prev[name] = val
                if val == 1 and prev == 0:
                    self._host_low_since[name] = 0
                    print("Host release: %s" % name)
                elif val == 0:
                    if self._host_low_since[name] == 0:
                        self._host_low_since[name] = now
                    elif time.ticks_diff(now, self._host_low_since[name]) > self.STUCK_LOW_TIMEOUT_US:
                        print("Host stuck-low recovery: %s" % name)
                        self._host_prev[name] = 1
                        self._host_low_since[name] = 0
                else:
                    self._host_low_since[name] = 0

            # --- Periodic pin refresh ---
            if time.ticks_diff(time.ticks_ms(), last_refresh_ms) > self.REFRESH_PERIOD_S * 1000:
                last_refresh_ms = time.ticks_ms()
                self._refresh_pins()

            await asyncio.sleep(0.05)  # 50ms cadence is plenty for the watchdog

    def _refresh_pins(self):
        """Re-initialize Pin objects with PULL_UP and reinstall IRQs.

        Works around any internal state that could silently desensitize a pin.
        """
        # Disable old IRQs before re-creating Pin objects
        for i in range(self.num_players):
            try:
                self.player_pins[i].irq(handler=None)
            except Exception:
                pass
        for name in HOST_NAMES:
            try:
                self.host_pins[name].irq(handler=None)
            except Exception:
                pass

        for i in range(self.num_players):
            self.player_pins[i] = Pin(PLAYER_GPIOS[i], Pin.IN, Pin.PULL_UP)
        for name, gp in HOST_GPIOS.items():
            self.host_pins[name] = Pin(gp, Pin.IN, Pin.PULL_UP)

        self._install_irqs()
