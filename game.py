import asyncio
import protocol


class GameEngine:

    def __init__(self, num_players=8, points_correct=10, points_incorrect=-5):
        self.num_players = num_players
        self.points_correct = points_correct
        self.points_incorrect = points_incorrect
        self.revival = False
        self.max_accepts = 0  # 0=unlimited, N=max N simultaneous presses
        self.jingle_auto_arm = False
        self.countdown_auto_stop = False
        self.penalty_rounds = 0  # N問休み (0=無効)
        self.batch_mode = False
        self.batch_use_order = True
        self.batch_points = [10, 8, 6, 4, 3, 2, 1, 1]
        self._countdown_task = None
        self._countdown_value = 0
        self.round = 0

        self.players = [
            {"id": i, "name": f"Player {i + 1}", "score": 0, "penalty": 0}
            for i in range(num_players)
        ]

        self.colors = [
            "#e63946", "#457b9d", "#2a9d8f", "#e9c46a",
            "#f4a261", "#264653", "#6a4c93", "#1982c4"
        ]

        self.state = protocol.STATE_IDLE
        self.press_order = []  # [(player_id, timestamp_us), ...]
        self._first_press_us = 0
        self._pressed_set = set()

        self._answerer_idx = 0  # Index in press_order of current answerer
        self._last_wrong_id = -1  # Previous wrong answerer (for revival)

        # Callback for broadcasting messages
        self._broadcast = None
        # Callback for lamp control
        self._buttons = None
        # Callback for saving config
        self._save_config = None
        # DFPlayer
        self._dfp = None

    def set_broadcast(self, callback):
        self._broadcast = callback

    def set_buttons(self, buttons):
        self._buttons = buttons

    def set_dfplayer(self, dfp):
        self._dfp = dfp

    def set_save_config(self, callback):
        """callback(key, value) - saves to config.json"""
        self._save_config = callback

    def get_current_answerer(self):
        if self._answerer_idx < len(self.press_order):
            return self.press_order[self._answerer_idx][0]
        return -1

    def _active_press_count(self):
        # Presses still in the queue (current answerer + waiting). Judged-past presses don't occupy a slot.
        return max(0, len(self.press_order) - self._answerer_idx)

    def get_state_msg(self):
        msg = protocol.make_state_msg(
            self.state,
            self.players,
            self.press_order,
            self.round,
            self.points_correct,
            self.points_incorrect,
        )
        msg["answerer_id"] = self.get_current_answerer()
        msg["answerer_idx"] = self._answerer_idx
        msg["colors"] = self.colors
        msg["revival"] = self.revival
        msg["max_accepts"] = self.max_accepts
        msg["jingle_auto_arm"] = self.jingle_auto_arm
        msg["countdown_auto_stop"] = self.countdown_auto_stop
        msg["penalty_rounds"] = self.penalty_rounds
        msg["batch_mode"] = self.batch_mode
        msg["batch_use_order"] = self.batch_use_order
        msg["batch_points"] = self.batch_points
        return msg

    async def _broadcast_msg(self, msg):
        if self._broadcast:
            await self._broadcast(msg)

    def _update_lamps(self):
        if not self._buttons:
            return

        if self.state == protocol.STATE_ARMED:
            can_accept = self.max_accepts == 0 or self._active_press_count() < self.max_accepts
            for i in range(len(self.players)):
                if self.players[i]["penalty"] > 0:
                    self._buttons.lamp_off(i)
                elif i in self._pressed_set:
                    self._buttons.lamp_off(i)
                elif can_accept:
                    self._buttons.lamp_dim(i)
                else:
                    self._buttons.lamp_off(i)
            return

        if self.state != protocol.STATE_JUDGING:
            self._buttons.all_lamps_off()
            return

        # JUDGING: set each player explicitly (no all_lamps_off to preserve blink task)
        # answerer=full(100%), waiting-in-queue=blink_dim(20% blink), can-press=dim(20%)
        answerer = self.get_current_answerer()
        assigned = set()
        for i, (pid, _) in enumerate(self.press_order):
            assigned.add(pid)
            if pid == answerer:
                self._buttons.lamp_full(pid)
            elif i > self._answerer_idx:
                self._buttons.lamp_blink_dim(pid)
            elif self.revival and pid not in self._pressed_set:
                # Revived: can press again
                self._buttons.lamp_dim(pid)
            else:
                self._buttons.lamp_off(pid)

        # Everyone else: can they still press?
        can_accept = self.max_accepts == 0 or self._active_press_count() < self.max_accepts
        for i in range(len(self.players)):
            if i not in assigned:
                if can_accept and self.players[i]["penalty"] <= 0:
                    self._buttons.lamp_dim(i)
                else:
                    self._buttons.lamp_off(i)

    # Button event handlers

    async def on_player_press(self, player_id, timestamp_us):
        if self.state not in (protocol.STATE_ARMED, protocol.STATE_JUDGING):
            return

        if player_id in self._pressed_set:
            return

        # Penalty: player is sitting out
        if player_id < len(self.players) and self.players[player_id]["penalty"] > 0:
            print(f"Player {player_id+1}: penalty {self.players[player_id]['penalty']}, rejected")
            return

        # Max accepts limit — count only presses still in the queue (judged-past don't occupy a slot)
        if self.max_accepts > 0 and self._active_press_count() >= self.max_accepts:
            return

        self._pressed_set.add(player_id)
        order = len(self.press_order) + 1
        is_first = order == 1
        self.press_order.append((player_id, timestamp_us))

        if is_first:
            self._first_press_us = timestamp_us
            self._answerer_idx = 0
            self.state = protocol.STATE_JUDGING
            self.stop_countdown()

        # Play player sound via DFPlayer
        if self._dfp and self._dfp.is_ready():
            self._dfp.play_player(player_id)

        # Update lamp state
        self._update_lamps()

        await self._broadcast_msg(
            protocol.make_press_msg(player_id, order, timestamp_us, is_first)
        )

    async def on_host_press(self, button_name):
        print(f"Host: {button_name}")
        if button_name == "correct":
            await self.judge(protocol.RESULT_CORRECT)
        elif button_name == "incorrect":
            await self.judge(protocol.RESULT_INCORRECT)
        elif button_name == "reset":
            await self._broadcast_msg({"type": "show_reset_dialog"})
        elif button_name == "arm":
            await self.arm()
        elif button_name == "stop":
            await self.stop()
        elif button_name == "jingle":
            if self._dfp and self._dfp.is_ready():
                self._dfp.play_sound(self._dfp.SOUND_JINGLE)
            await self._broadcast_msg({"type": "jingle"})
            if self.jingle_auto_arm:
                await self.arm()
        elif button_name == "countdown":
            if self._dfp and self._dfp.is_ready():
                self._dfp.play_sound(self._dfp.SOUND_COUNTDOWN)
            await self.start_countdown()

    async def judge(self, result):
        if self.state != protocol.STATE_JUDGING:
            return

        if self._answerer_idx >= len(self.press_order):
            return

        answerer_id = self.press_order[self._answerer_idx][0]
        player = self.players[answerer_id]

        if result == protocol.RESULT_CORRECT:
            delta = self.points_correct
            player["score"] += delta
            self.state = protocol.STATE_SHOWING_RESULT

            if self._dfp and self._dfp.is_ready():
                self._dfp.play_sound(self._dfp.SOUND_CORRECT)

            # All off, then flash for celebration
            if self._buttons:
                self._buttons.all_lamps_off()
                asyncio.create_task(
                    self._buttons.flash_lamp(answerer_id, times=20, interval_ms=75)
                )

            await self._broadcast_msg(
                protocol.make_judgment_msg(result, answerer_id, player["score"], delta)
            )

        else:
            delta = self.points_incorrect
            player["score"] += delta

            if self._dfp and self._dfp.is_ready():
                self._dfp.play_sound(self._dfp.SOUND_INCORRECT)

            # Apply penalty (+1 because ARM decrements immediately)
            if self.penalty_rounds > 0:
                player["penalty"] = self.penalty_rounds + 1
                print(f"Penalty: Player {answerer_id+1} = {self.penalty_rounds} rounds")

            # Revival: previous wrong answerer can now re-press
            if self.revival and self._last_wrong_id >= 0:
                self._pressed_set.discard(self._last_wrong_id)
            self._last_wrong_id = answerer_id

            await self._broadcast_msg(
                protocol.make_judgment_msg(result, answerer_id, player["score"], delta)
            )

            # Wait for animation before moving to next
            await asyncio.sleep(3)

            # Move to next answerer
            self._answerer_idx += 1

            if self._answerer_idx < len(self.press_order):
                # Next person in queue
                self._update_lamps()
                next_id = self.press_order[self._answerer_idx][0]
                await self._broadcast_msg({
                    "type": "next_answerer",
                    "player_id": next_id,
                    "answerer_idx": self._answerer_idx,
                })
            else:
                if self.revival:
                    # Slots freed: clear press_order, re-arm
                    self.press_order = []
                    self._answerer_idx = 0
                    self.state = protocol.STATE_ARMED
                    self._update_lamps()
                    await self._broadcast_msg({
                        "type": "no_answerer",
                        "revival": True,
                    })
                else:
                    # No one left, round over
                    self.state = protocol.STATE_SHOWING_RESULT
                    if self._buttons:
                        self._buttons.all_lamps_off()
                    await self._broadcast_msg({
                        "type": "no_answerer",
                    })

    async def start_countdown(self):
        self.stop_countdown()
        self._countdown_value = 10
        await self._broadcast_msg({"type": "countdown", "value": 10})
        self._countdown_task = asyncio.create_task(self._countdown_loop())

    def stop_countdown(self):
        if self._countdown_task:
            self._countdown_task.cancel()
            self._countdown_task = None
            if self._dfp and self._dfp.is_ready():
                self._dfp.stop()
        self._countdown_value = 0

    async def _countdown_loop(self):
        try:
            while self._countdown_value > 0:
                await asyncio.sleep(1)
                self._countdown_value -= 1
                await self._broadcast_msg({
                    "type": "countdown_tick",
                    "value": self._countdown_value,
                })
                if self._countdown_value <= 0:
                    if self._dfp and self._dfp.is_ready():
                        self._dfp.play_sound(self._dfp.SOUND_COUNTDOWN_END)
                    if self.countdown_auto_stop:
                        self._countdown_task = None
                        await self.stop()
                        return
        except asyncio.CancelledError:
            pass

    async def reset(self):
        self.stop_countdown()
        self.press_order = []
        self._pressed_set = set()
        self._first_press_us = 0
        self._answerer_idx = 0
        self._last_wrong_id = -1
        self.state = protocol.STATE_IDLE

        if self._buttons:
            self._buttons.all_lamps_off()

        await self._broadcast_msg(protocol.make_reset_msg(self.state))

    async def stop(self):
        self.stop_countdown()
        self.press_order = []
        self._pressed_set = set()
        self._first_press_us = 0
        self._answerer_idx = 0
        self._last_wrong_id = -1
        self.state = protocol.STATE_IDLE

        if self._buttons:
            self._buttons.all_lamps_off()

        await self._broadcast_msg(protocol.make_reset_msg(self.state))

    async def arm(self):
        self.press_order = []
        self._pressed_set = set()
        self._first_press_us = 0
        self._answerer_idx = 0
        self._last_wrong_id = -1

        self.round += 1
        self.state = protocol.STATE_ARMED

        # Decrement penalty counters
        for p in self.players:
            if p["penalty"] > 0:
                p["penalty"] -= 1

        self._update_lamps()

        await self._broadcast_msg(protocol.make_reset_msg(self.state))
        await self._broadcast_msg(self.get_state_msg())

    async def batch_judge(self, correct_ids, sound="correct"):
        if self.state not in (protocol.STATE_JUDGING, protocol.STATE_ARMED):
            return

        results = []
        processed = set()
        correct_rank = 0  # Rank among correct players

        # Process pressed players
        for i, (pid, ts) in enumerate(self.press_order):
            player = self.players[pid]
            processed.add(pid)
            if pid in correct_ids:
                if self.batch_use_order:
                    pts = self.batch_points[correct_rank] if correct_rank < len(self.batch_points) else self.batch_points[-1]
                else:
                    pts = self.points_correct
                correct_rank += 1
                player["score"] += pts
                results.append({
                    "player_id": pid, "result": "correct",
                    "delta": pts, "order": i + 1,
                    "new_score": player["score"],
                })
            else:
                delta = self.points_incorrect
                player["score"] += delta
                results.append({
                    "player_id": pid, "result": "incorrect",
                    "delta": delta, "order": i + 1,
                    "new_score": player["score"],
                })
                if self.penalty_rounds > 0:
                    player["penalty"] = self.penalty_rounds + 1

        # Process unpressed players
        for pid in range(len(self.players)):
            if pid in processed:
                continue
            player = self.players[pid]
            if pid in correct_ids:
                pts = self.points_correct
                player["score"] += pts
                results.append({
                    "player_id": pid, "result": "correct",
                    "delta": pts, "order": 0,
                    "new_score": player["score"],
                })
            else:
                delta = self.points_incorrect
                player["score"] += delta
                results.append({
                    "player_id": pid, "result": "incorrect",
                    "delta": delta, "order": 0,
                    "new_score": player["score"],
                })
                if self.penalty_rounds > 0:
                    player["penalty"] = self.penalty_rounds + 1

        self.state = protocol.STATE_SHOWING_RESULT

        if self._dfp and self._dfp.is_ready():
            if sound == "correct":
                self._dfp.play_sound(self._dfp.SOUND_BATCH_CORRECT)
            else:
                self._dfp.play_sound(self._dfp.SOUND_INCORRECT)

        if self._buttons:
            self._buttons.stop_blink()
            self._buttons.all_lamps_off()

        await self._broadcast_msg({
            "type": "batch_result",
            "results": results,
            "sound": sound,
        })

    async def clear_penalty(self):
        for p in self.players:
            p["penalty"] = 0
        await self._broadcast_msg(self.get_state_msg())

    async def reset_scores(self):
        for p in self.players:
            p["score"] = 0
        await self._broadcast_msg(self.get_state_msg())

    async def reset_round(self):
        self.round = 0
        await self._broadcast_msg(self.get_state_msg())

    async def set_round(self, value):
        self.round = max(0, value)
        await self._broadcast_msg(self.get_state_msg())

    # Admin actions

    async def set_player_name(self, player_id, name):
        if 0 <= player_id < self.num_players:
            self.players[player_id]["name"] = name
            await self._broadcast_msg(
                protocol.make_player_update_msg(
                    player_id, name, self.players[player_id]["score"]
                )
            )

    async def set_player_score(self, player_id, score):
        if 0 <= player_id < self.num_players:
            self.players[player_id]["score"] = score
            await self._broadcast_msg(
                protocol.make_player_update_msg(
                    player_id, self.players[player_id]["name"], score
                )
            )

    async def set_colors(self, colors):
        self.colors = colors
        if self._save_config:
            self._save_config("colors", colors)
        await self._broadcast_msg({"type": "colors_update", "colors": colors})

    async def update_settings(self, settings):
        if "points_correct" in settings:
            self.points_correct = settings["points_correct"]
            if self._save_config:
                self._save_config("points_correct", self.points_correct)
        if "points_incorrect" in settings:
            self.points_incorrect = settings["points_incorrect"]
            if self._save_config:
                self._save_config("points_incorrect", self.points_incorrect)
        if "num_players" in settings:
            new_num = min(settings["num_players"], 8)
            if new_num != self.num_players:
                self.num_players = new_num
                if self._save_config:
                    self._save_config("num_players", new_num)
                # Adjust player list
                while len(self.players) < new_num:
                    pid = len(self.players)
                    self.players.append({"id": pid, "name": f"Player {pid + 1}", "score": 0, "penalty": 0})
                while len(self.players) > new_num:
                    self.players.pop()
        if "revival" in settings:
            self.revival = bool(settings["revival"])
            if self._save_config:
                self._save_config("revival", self.revival)
        if "max_accepts" in settings:
            self.max_accepts = int(settings["max_accepts"])
            if self._save_config:
                self._save_config("max_accepts", self.max_accepts)
        if "jingle_auto_arm" in settings:
            self.jingle_auto_arm = bool(settings["jingle_auto_arm"])
            if self._save_config:
                self._save_config("jingle_auto_arm", self.jingle_auto_arm)
        if "countdown_auto_stop" in settings:
            self.countdown_auto_stop = bool(settings["countdown_auto_stop"])
            if self._save_config:
                self._save_config("countdown_auto_stop", self.countdown_auto_stop)
        if "penalty_rounds" in settings:
            self.penalty_rounds = int(settings["penalty_rounds"])
            if self._save_config:
                self._save_config("penalty_rounds", self.penalty_rounds)
        if "batch_mode" in settings:
            self.batch_mode = bool(settings["batch_mode"])
            if self._save_config:
                self._save_config("batch_mode", self.batch_mode)
        if "batch_use_order" in settings:
            self.batch_use_order = bool(settings["batch_use_order"])
            if self._save_config:
                self._save_config("batch_use_order", self.batch_use_order)
        if "batch_points" in settings:
            self.batch_points = settings["batch_points"]
            if self._save_config:
                self._save_config("batch_points", self.batch_points)
        await self._broadcast_msg(self.get_state_msg())
