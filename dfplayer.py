from machine import UART, Pin
import asyncio


class DFPlayer:
    """DFPlayer Mini control via UART1 (GP4=TX, GP5=RX)."""

    # Sound file mapping (SD card: /01/001.mp3 ~ /01/NNN.mp3)
    SOUND_P1 = 1
    SOUND_P2 = 2
    SOUND_P3 = 3
    SOUND_P4 = 4
    SOUND_P5 = 5
    SOUND_P6 = 6
    SOUND_P7 = 7
    SOUND_P8 = 8
    SOUND_CORRECT = 9
    SOUND_INCORRECT = 10
    SOUND_JINGLE = 11
    SOUND_COUNTDOWN = 12
    SOUND_COUNTDOWN_END = 13
    SOUND_BATCH_CORRECT = 14

    def __init__(self):
        self.uart = UART(1, baudrate=9600, tx=Pin(4), rx=Pin(5))
        self.volume = 20  # 0-30
        self._init_done = False
        self.enabled = True

    async def init(self):
        """Initialize DFPlayer (call after power-up delay)."""
        await asyncio.sleep(1)  # Wait for DFPlayer boot
        self.set_volume(self.volume)
        await asyncio.sleep(0.1)
        self._init_done = True
        print("DFPlayer: initialized")

    def _send_cmd(self, cmd, param1=0, param2=0):
        """Send command to DFPlayer."""
        # Protocol: 7E FF 06 CMD 00 PAR1 PAR2 EF
        buf = bytearray(8)
        buf[0] = 0x7E  # Start
        buf[1] = 0xFF  # Version
        buf[2] = 0x06  # Length
        buf[3] = cmd
        buf[4] = 0x00  # No feedback
        buf[5] = param1
        buf[6] = param2
        buf[7] = 0xEF  # End
        self.uart.write(buf)

    def play(self, folder, track):
        """Play track N from folder F. Folder=1-99, Track=1-255."""
        self._send_cmd(0x0F, folder, track)

    def play_sound(self, sound_id):
        """Play a sound by ID (folder 1)."""
        self.play(1, sound_id)

    def play_player(self, player_id):
        """Play player-specific sound (0-indexed)."""
        self.play_sound(self.SOUND_P1 + player_id)

    def stop(self):
        """Stop playback."""
        self._send_cmd(0x16)

    def set_volume(self, vol):
        """Set volume (0-30)."""
        self.volume = max(0, min(30, vol))
        self._send_cmd(0x06, 0, self.volume)

    def is_ready(self):
        return self._init_done and self.enabled
