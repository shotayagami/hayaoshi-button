import json

# Game states
STATE_IDLE = "idle"
STATE_ARMED = "armed"
# STATE_LOCKED removed - presses accepted until judged
STATE_JUDGING = "judging"
STATE_SHOWING_RESULT = "showing_result"

# S2C message types
MSG_STATE = "state"
MSG_PRESS = "press"
MSG_JUDGMENT = "judgment"
MSG_RESET = "reset"
MSG_PLAYER_UPDATE = "player_update"

# C2S message types
MSG_REGISTER = "register"
MSG_SET_NAME = "set_name"
MSG_SET_SCORE = "set_score"
MSG_ARM = "arm"
MSG_JUDGE = "judge"
MSG_C2S_RESET = "reset"
MSG_SETTINGS = "settings"

# Client types
CLIENT_ADMIN = "admin"
CLIENT_DISPLAY = "display"

# Judgment results
RESULT_CORRECT = "correct"
RESULT_INCORRECT = "incorrect"


def encode(msg_dict):
    return json.dumps(msg_dict)


def decode(msg_str):
    return json.loads(msg_str)


def make_state_msg(game_state, players, press_order, round_num, points_correct, points_incorrect):
    return {
        "type": MSG_STATE,
        "game_state": game_state,
        "players": players,
        "press_order": [
            {"player_id": pid, "order": i + 1, "timestamp_us": ts}
            for i, (pid, ts) in enumerate(press_order)
        ],
        "round": round_num,
        "points_correct": points_correct,
        "points_incorrect": points_incorrect,
    }


def make_press_msg(player_id, order, timestamp_us, is_first):
    return {
        "type": MSG_PRESS,
        "player_id": player_id,
        "order": order,
        "timestamp_us": timestamp_us,
        "is_first": is_first,
    }


def make_judgment_msg(result, player_id, new_score, points_delta):
    return {
        "type": MSG_JUDGMENT,
        "result": result,
        "player_id": player_id,
        "new_score": new_score,
        "points_delta": points_delta,
    }


def make_reset_msg(game_state):
    return {
        "type": MSG_RESET,
        "game_state": game_state,
    }


def make_player_update_msg(player_id, name, score):
    return {
        "type": MSG_PLAYER_UPDATE,
        "player_id": player_id,
        "name": name,
        "score": score,
    }
