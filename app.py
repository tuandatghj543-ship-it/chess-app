import json
import math
import os
import random
import chess
from flask import Flask, Response, jsonify, render_template, request

app = Flask(__name__)

SAVE_FILE = "save_game.json"
MUSIC_FOLDER = "/storage/emulated/0/music"

board = chess.Board()
ai_difficulty = "easy"
user_side_setting = "white"
actual_user_color = chess.WHITE
control_mode = "click"  # "click" hoặc "text"

user_coins = 0
unlocked_themes = ["default"]
current_theme = "default"
has_double_coins = False
has_editor_unlocked = False
reward_claimed = False

# Thống kê & Thành tựu
total_wins = 0
wins_easy = 0
wins_medium = 0
wins_hard = 0
unlocked_achievements = []  # Danh sách ID thành tựu đã đạt được

board_history_states = []

PIECE_SYMBOLS = {
    "P": "♙", "N": "♘", "B": "♗", "R": "♖", "Q": "♕", "K": "♔",
    "p": "♟", "n": "♞", "b": "♝", "r": "♜", "q": "♛", "k": "♚",
}

PIECE_MATERIAL_VALUES = {
    chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
    chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0
}

PIECE_VALUES_AI = {
    chess.PAWN: 10, chess.KNIGHT: 30, chess.BISHOP: 30,
    chess.ROOK: 50, chess.QUEEN: 90, chess.KING: 900
}

POSITION_BONUS = [
    1,  1,  1,  1,  1,  1,  1,  1,
    2,  3,  3,  3,  3,  3,  3,  2,
    2,  3,  5,  5,  5,  5,  3,  2,
    2,  3,  5,  8,  8,  5,  3,  2,
    2,  3,  5,  8,  8,  5,  3,  2,
    2,  3,  5,  5,  5,  5,  3,  2,
    2,  3,  3,  3,  3,  3,  3,  2,
    1,  1,  1,  1,  1,  1,  1,  1
]

BOOK_MOVES = {
    "e2e4", "e7e5", "d2d4", "d7d5", "g1f3", "b8c6", "c2c4", "c7c6", "e7e6",
    "c7c5", "g8f6", "b1c3", "f2f4", "g2g3", "f1c4", "f1b5", "d2d3", "d7d6"
}

ACHIEVEMENT_DEFINITIONS = {
    "pawn_killer": {"name": "Sát Thủ Tốt", "desc": "Chiếu hết bằng quân Tốt"},
    "knight_killer": {"name": "Sát Thủ Mã", "desc": "Chiếu hết bằng quân Mã"},
    "bishop_killer": {"name": "Sát Thủ Tượng", "desc": "Chiếu hết bằng quân Tượng"},
    "rook_killer": {"name": "Sát Thủ Xe", "desc": "Chiếu hết bằng quân Xe"},
    "queen_killer": {"name": "Sát Thủ Hậu", "desc": "Chiếu hết bằng quân Hậu"},
    "king_killer": {"name": "Sát Thủ Vua", "desc": "Chiếu hết bằng quân Vua"},
    "novice": {"name": "Người mới chơi", "desc": "Thắng 1 ván đấu"},
    "passionate": {"name": "Đam mê", "desc": "Thắng tổng cộng 10 ván đấu"},
    "chicken": {"name": "Gà", "desc": "Đánh bại cấp độ Dễ"},
    "master": {"name": "Bậc Thầy", "desc": "Đánh bại cấp độ Bình thường"},
    "legend": {"name": "Huyền Thoại", "desc": "Đánh bại cấp độ Khó"}
}

last_evaluation_comment = "Bắt đầu ván đấu mới! Chúc bạn chơi vui vẻ 🐧"
last_move_target = None
last_move_badge = ""
move_history_san = []
last_unlocked_notification = None


def format_custom_san(san_str):
    if not san_str:
        return ""
    if "O-O" in san_str or "o-o" in san_str.lower():
        if "O-O-O" in san_str or "o-o-o" in san_str.lower() or san_str.count('O') >= 3 or san_str.count('o') >= 3:
            return "O-O-O"
        return "O-O"

    formatted = ""
    i = 0
    length = len(san_str)
    while i < length:
        char = san_str[i]
        if char in ['K', 'Q', 'R', 'B', 'N', 'k', 'q', 'r', 'b', 'n']:
            formatted += char.upper()
        elif char in ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', '1', '2', '3', '4', '5', '6', '7', '8']:
            formatted += char.lower()
        else:
            formatted += char
        i += 1
    return formatted


def get_playlist_files():
    if not os.path.exists(MUSIC_FOLDER):
        return ["music_chess1.mp3"]
    files = []
    i = 1
    while True:
        filename = f"music_chess{i}.mp3"
        path = os.path.join(MUSIC_FOLDER, filename)
        if os.path.exists(path):
            files.append(filename)
            i += 1
        else:
            break
    if not files:
        if os.path.exists(os.path.join(MUSIC_FOLDER, "music_chess.mp3")):
            return ["music_chess.mp3"]
        return ["music_chess1.mp3"]
    return files


def get_board_state_dict_for_fen(fen_str):
    temp_board = chess.Board(fen_str)
    squares_data = {}
    for square in chess.SQUARES:
        square_name = chess.square_name(square)
        piece = temp_board.piece_at(square)
        squares_data[square_name] = {
            "piece": PIECE_SYMBOLS[piece.symbol()] if piece else "",
            "color": "w" if piece and piece.color == chess.WHITE else ("b" if piece else "")
        }
    return squares_data


def save_board_state_to_history():
    global board_history_states
    board_history_states.append({
        "fen": board.fen(),
        "eval": last_evaluation_comment,
        "last_target": last_move_target,
        "last_badge": last_move_badge,
        "pgn": list(move_history_san)
    })


def start_new_game():
    global board, last_evaluation_comment, actual_user_color, last_move_target, last_move_badge, move_history_san, reward_claimed, board_history_states
    board = chess.Board()
    last_evaluation_comment = "Bắt đầu ván mới! Chúc bạn chơi vui vẻ 🐧"
    last_move_target = None
    last_move_badge = ""
    move_history_san = []
    reward_claimed = False
    board_history_states = []
    
    save_board_state_to_history()
    
    if user_side_setting == "white":
        actual_user_color = chess.WHITE
    elif user_side_setting == "black":
        actual_user_color = chess.BLACK
    else:
        actual_user_color = random.choice([chess.WHITE, chess.BLACK])


def get_captured_and_material():
    initial_counts = {
        chess.WHITE: {chess.PAWN: 8, chess.KNIGHT: 2, chess.BISHOP: 2, chess.ROOK: 2, chess.QUEEN: 1},
        chess.BLACK: {chess.PAWN: 8, chess.KNIGHT: 2, chess.BISHOP: 2, chess.ROOK: 2, chess.QUEEN: 1}
    }
    current_counts = {
        chess.WHITE: {chess.PAWN: 0, chess.KNIGHT: 0, chess.BISHOP: 0, chess.ROOK: 0, chess.QUEEN: 0},
        chess.BLACK: {chess.PAWN: 0, chess.KNIGHT: 0, chess.BISHOP: 0, chess.ROOK: 0, chess.QUEEN: 0}
    }

    white_material, black_material = 0, 0
    for square in chess.SQUARES:
        piece = board.piece_at(square)
        if piece and piece.piece_type != chess.KING:
            current_counts[piece.color][piece.piece_type] += 1
            val = PIECE_MATERIAL_VALUES[piece.piece_type]
            if piece.color == chess.WHITE:
                white_material += val
            else:
                black_material += val

    white_captured, black_captured = [], []
    piece_order = [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN]

    for p_type in piece_order:
        missing_black = initial_counts[chess.BLACK][p_type] - current_counts[chess.BLACK][p_type]
        for _ in range(missing_black):
            white_captured.append(PIECE_SYMBOLS[chess.Piece(p_type, chess.BLACK).symbol()])

        missing_white = initial_counts[chess.WHITE][p_type] - current_counts[chess.WHITE][p_type]
        for _ in range(missing_white):
            black_captured.append(PIECE_SYMBOLS[chess.Piece(p_type, chess.WHITE).symbol()])

    diff = white_material - black_material

    return {
        "white_captured": white_captured,
        "black_captured": black_captured,
        "white_lead": max(0, diff),
        "black_lead": max(0, -diff)
    }


def get_board_state_dict():
    squares_data = {}
    losing_king_sq, winning_king_sq = None, None
    if board.is_checkmate():
        losing_king_sq = board.king(board.turn)
        winning_king_sq = board.king(not board.turn)

    for square in chess.SQUARES:
        square_name = chess.square_name(square)
        piece = board.piece_at(square)
        badge = ""
        if square == losing_king_sq:
            badge = "🏳"
        elif square == winning_king_sq:
            badge = "🏅"

        squares_data[square_name] = {
            "piece": PIECE_SYMBOLS[piece.symbol()] if piece else "",
            "color": "w" if piece and piece.color == chess.WHITE else ("b" if piece else ""),
            "king_badge": badge
        }
    return squares_data


def get_pgn_text():
    pgn_str = ""
    for i in range(0, len(move_history_san), 2):
        move_num = (i // 2) + 1
        white_move = move_history_san[i]
        black_move = move_history_san[i+1] if (i + 1) < len(move_history_san) else ""
        pgn_str += f"{move_num}. {white_move} {black_move}  "
    return pgn_str.strip()


def check_material_imbalance():
    w_mat, b_mat = 0, 0
    w_queens, b_queens = 0, 0
    for sq in chess.SQUARES:
        p = board.piece_at(sq)
        if p:
            val = PIECE_MATERIAL_VALUES.get(p.piece_type, 0)
            if p.color == chess.WHITE:
                w_mat += val
                if p.piece_type == chess.QUEEN: w_queens += 1
            else:
                b_mat += val
                if p.piece_type == chess.QUEEN: b_queens += 1
    
    if w_queens > 2 or b_queens > 2 or abs(w_mat - b_mat) > 30:
        return True
    return False


def check_and_award_points_and_achievements(last_move_piece_type):
    global user_coins, reward_claimed, total_wins, wins_easy, wins_medium, wins_hard, unlocked_achievements, last_unlocked_notification
    if reward_claimed or not board.is_game_over():
        return 0

    reward_claimed = True
    is_imbalanced = check_material_imbalance()

    base_points = {
        "easy":   {"win": 2,  "draw": 1, "loss": 0},
        "medium": {"win": 4,  "draw": 2, "loss": 0},
        "hard":   {"win": 10, "draw": 5, "loss": 0}
    }

    current_rules = base_points.get(ai_difficulty, base_points["easy"])

    if board.is_checkmate():
        winner_color = chess.BLACK if board.turn == chess.WHITE else chess.WHITE
        result = "win" if winner_color == actual_user_color else "loss"
    else:
        result = "draw"

    earned_coins = current_rules[result] if not is_imbalanced else 0

    if control_mode == "text" and not is_imbalanced:
        earned_coins *= 3

    if has_double_coins and not is_imbalanced:
        if result == "loss":
            earned_coins = 1 if earned_coins == 0 else earned_coins
        else:
            earned_coins *= 2

    user_coins += earned_coins

    if not is_imbalanced and result == "win":
        total_wins += 1
        if ai_difficulty == "easy": wins_easy += 1
        elif ai_difficulty == "medium": wins_medium += 1
        elif ai_difficulty == "hard": wins_hard += 1

        newly_unlocked = []

        def unlock(ach_id):
            if ach_id not in unlocked_achievements:
                unlocked_achievements.append(ach_id)
                newly_unlocked.append(ACHIEVEMENT_DEFINITIONS[ach_id]["name"])

        if total_wins >= 1: unlock("novice")
        if total_wins >= 10: unlock("passionate")
        if ai_difficulty == "easy": unlock("chicken")
        elif ai_difficulty == "medium": unlock("master")
        elif ai_difficulty == "hard": unlock("legend")

        if last_move_piece_type == chess.PAWN: unlock("pawn_killer")
        elif last_move_piece_type == chess.KNIGHT: unlock("knight_killer")
        elif last_move_piece_type == chess.BISHOP: unlock("bishop_killer")
        elif last_move_piece_type == chess.ROOK: unlock("rook_killer")
        elif last_move_piece_type == chess.QUEEN: unlock("queen_killer")
        elif last_move_piece_type == chess.KING: unlock("king_killer")

        if newly_unlocked:
            last_unlocked_notification = ", ".join(newly_unlocked)

    return earned_coins


def get_game_status(last_move_piece_type=None):
    earned = check_and_award_points_and_achievements(last_move_piece_type)
    is_imbalanced = check_material_imbalance()
    
    bonus_desc = []
    if control_mode == "text": bonus_desc.append("Ký tự x3")
    if has_double_coins: bonus_desc.append("Thẻ x2")
    if is_imbalanced: bonus_desc.append("Bàn cờ tùy chỉnh: 0đ")
    bonus_str = f" ({', '.join(bonus_desc)})" if bonus_desc else ""
    global last_unlocked_notification    
    notif = last_unlocked_notification
    last_unlocked_notification = None

    ach_msg = f" | 🏆 Mở khóa: {notif}" if notif else ""

    if board.is_checkmate():
        winner_color = chess.BLACK if board.turn == chess.WHITE else chess.WHITE
        if winner_color == actual_user_color:
            return {"is_over": True, "title": "🏆 CHIẾN THẮNG RỰC RỠ!", "message": f"Bạn đã chiếu hết AI! (+{earned} Điểm{bonus_str}){ach_msg} 🎉", "achievement": notif}
        else:
            return {"is_over": True, "title": "💀 BẠN ĐÃ THUA!", "message": f"AI đã chiếu hết bạn! (+{earned} Điểm{bonus_str})", "achievement": None}
    elif board.is_stalemate() or board.is_insufficient_material() or board.is_game_over():
        return {"is_over": True, "title": "🤝 HÒA CỜ", "message": f"Ván đấu kết thúc Hòa! (+{earned} Điểm{bonus_str})", "achievement": None}
    return {"is_over": False, "title": "", "message": "", "achievement": None}


def evaluate_board_score(current_board, side_color):
    if current_board.is_checkmate():
        return -99999 if current_board.turn == side_color else 99999
    if current_board.is_game_over():
        return 0

    score = 0
    for square in chess.SQUARES:
        piece = current_board.piece_at(square)
        if piece:
            val = PIECE_VALUES_AI[piece.piece_type] + POSITION_BONUS[square]
            score += val if piece.color == side_color else -val
    return score


def minimax(current_board, depth, alpha, beta, is_maximizing, ai_color):
    if depth == 0 or current_board.is_game_over():
        return evaluate_board_score(current_board, ai_color), None

    legal_moves = list(current_board.legal_moves)
    best_move = None

    if is_maximizing:
        max_eval = -999999
        for move in legal_moves:
            current_board.push(move)
            eval_score, _ = minimax(current_board, depth - 1, alpha, beta, False, ai_color)
            current_board.pop()
            if eval_score > max_eval:
                max_eval = eval_score
                best_move = move
            alpha = max(alpha, eval_score)
            if beta <= alpha:
                break
        return max_eval, best_move
    else:
        min_eval = 999999
        for move in legal_moves:
            current_board.push(move)
            eval_score, _ = minimax(current_board, depth - 1, alpha, beta, True, ai_color)
            current_board.pop()
            if eval_score < min_eval:
                min_eval = eval_score
                best_move = move
            beta = min(beta, eval_score)
            if beta <= alpha:
                break
        return min_eval, best_move


def evaluate_move(board_before, move):
    global last_evaluation_comment, last_move_target, last_move_badge
    uci_str = move.uci()
    last_move_target = uci_str[2:4]
    
    try:
        raw_san = board_before.san(move)
        formatted_san = format_custom_san(raw_san)
        move_history_san.append(formatted_san)
    except:
        move_history_san.append(uci_str.lower())

    mover_color = board_before.turn
    score_before = evaluate_board_score(board_before, mover_color)

    board_after = board_before.copy()
    board_after.push(move)

    score_after = evaluate_board_score(board_after, mover_color)
    drop_in_score = score_before - score_after

    is_check = board_after.is_check()
    is_capture = board_before.is_capture(move)

    if board_after.is_checkmate():
        last_evaluation_comment = f"🏆 CHIẾU HẾT! ({uci_str})"
        last_move_badge = "🏆"
    elif drop_in_score >= 80:
        last_evaluation_comment = f"?? Đại thảm họa ({uci_str})"
        last_move_badge = "??"
    elif drop_in_score >= 30:
        last_evaluation_comment = f"? Nước đi sai lầm ({uci_str})"
        last_move_badge = "?"
    elif uci_str in BOOK_MOVES and board_before.fullmove_number <= 4:
        last_evaluation_comment = f"📖 Khai cuộc ({uci_str})"
        last_move_badge = "📖"
    elif is_check and is_capture:
        last_evaluation_comment = f"!! Thiên tài ({uci_str})"
        last_move_badge = "!!"
    elif is_check:
        last_evaluation_comment = f"! Nước chiếu hiểm hóc ({uci_str})"
        last_move_badge = "!"
    elif is_capture:
        last_evaluation_comment = f"⭐ Nước đi tốt ({uci_str})"
        last_move_badge = "⭐"
    else:
        last_evaluation_comment = f"✔ Nước đi ổn ({uci_str})"
        last_move_badge = "✔"


@app.route("/get-playlist", methods=["GET"])
def get_playlist():
    files = get_playlist_files()
    return jsonify({"playlist": files})


@app.route("/play-music/<path:filename>", methods=["GET"])
def play_music(filename):
    song_path = os.path.join(MUSIC_FOLDER, filename)
    if not os.path.exists(song_path):
        return "Không tìm thấy file nhạc!", 404

    def generate():
        with open(song_path, "rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk

    return Response(generate(), mimetype="audio/mpeg")


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en" translate="no">
<head>
    <meta charset="UTF-8">
    <meta name="google" content="notranslate">
    <title>Chess vs AI & Chill 🐧</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
    <style>
        * { box-sizing: border-box; }
        body { font-family: sans-serif; text-align: center; background: #1e1e1e; color: #fff; padding: 5px; margin: 0; overflow-x: hidden; }
        
        .game-wrapper { transition: filter 0.3s ease, opacity 0.3s ease; }
        .game-wrapper.hidden-board { filter: blur(14px); opacity: 0.02; pointer-events: none; }

        .header-box { display: flex; justify-content: space-between; align-items: center; width: 100%; max-width: 360px; margin: 4px auto; padding: 0 4px; }
        .coins-display { background: #ff9800; color: #000; font-weight: bold; padding: 4px 10px; border-radius: 12px; font-size: 13px; display: flex; align-items: center; gap: 4px; }

        .menu-btn { background: #7b61ff; color: white; border: none; padding: 6px 10px; font-size: 13px; font-weight: bold; border-radius: 6px; cursor: pointer; }
        .shop-btn { background: #e91e63; color: white; border: none; padding: 6px 10px; font-size: 13px; font-weight: bold; border-radius: 6px; cursor: pointer; }
        .save-btn { background: #2196f3; color: white; border: none; padding: 6px 10px; font-size: 13px; font-weight: bold; border-radius: 6px; cursor: pointer; }
        .tools-btn { background: #00bcd4; color: #000; border: none; padding: 6px 12px; font-size: 13px; font-weight: bold; border-radius: 6px; cursor: pointer; border: 2px solid #ffeb3b; }

        .eval-box { background: #2c2c2c; border: 2px dashed #7b61ff; padding: 6px 10px; border-radius: 6px; margin: 6px auto; width: 100%; max-width: 360px; font-size: 14px; font-weight: bold; color: #ffeb3b; min-height: 22px; }

        .board-container { display: inline-block; background: #2c2c2c; padding: 6px 4px; border-radius: 8px; box-shadow: 0 6px 12px rgba(0,0,0,0.5); margin: 2px auto; width: 100%; max-width: 360px; }
        
        .captured-box { display: flex; align-items: center; justify-content: space-between; background: #181818; padding: 4px 8px; border-radius: 6px; margin: 4px 0; min-height: 28px; font-size: 16px; text-align: left; }
        .captured-pieces { display: flex; flex-wrap: wrap; gap: 2px; align-items: center; letter-spacing: -2px; }
        .captured-score { font-size: 12px; font-weight: bold; color: #00e676; background: rgba(0,230,118,0.15); padding: 2px 6px; border-radius: 10px; letter-spacing: normal; }

        .board-with-files { display: flex; align-items: center; width: 100%; position: relative; }

        .chessboard { display: grid; grid-template-columns: repeat(8, 1fr); grid-template-rows: repeat(8, 1fr); border: 2px solid #444; width: 100%; aspect-ratio: 1 / 1; position: relative; }
        .square { display: flex; align-items: center; justify-content: center; font-size: calc(100vw / 11); max-font-size: 26px; cursor: pointer; user-select: none; position: relative; }
        @media (min-width: 360px) { .square { font-size: 26px; } }

        .theme-default .light { background-color: #f0d9b5; color: #000; }
        .theme-default .dark { background-color: #b58863; color: #000; }
        .theme-classic .light { background-color: #ffffff; color: #000; }
        .theme-classic .dark { background-color: #444444; color: #fff; }
        .theme-red .light { background-color: #fce4ec; color: #000; }
        .theme-red .dark { background-color: #d32f2f; color: #fff; }
        .theme-neon .light { background-color: #00f5d4; color: #000; }
        .theme-neon .dark { background-color: #0f172a; color: #fff; }

        .selected { background-color: #7b61ff !important; }
        .hint-source { outline: 4px solid #00e676 !important; outline-offset: -4px; z-index: 8; border-radius: 50%; }

        .piece-element { position: absolute; width: 12.5%; height: 12.5%; display: flex; align-items: center; justify-content: center; font-size: calc(100vw / 11); max-font-size: 26px; pointer-events: none; z-index: 10; transition: transform 0.25s cubic-bezier(0.25, 1, 0.5, 1); }
        @media (min-width: 360px) { .piece-element { font-size: 26px; } }

        .dot { position: absolute; width: 30%; height: 30%; background-color: rgba(0, 0, 0, 0.35); border-radius: 50%; z-index: 4; }
        .eval-badge { position: absolute; top: 1px; right: 2px; font-size: 11px; font-weight: bold; background: rgba(0,0,0,0.85); color: #00e676; padding: 1px 3px; border-radius: 4px; pointer-events: none; z-index: 15; }
        .king-status-badge { position: absolute; bottom: 1px; left: 2px; font-size: 12px; background: rgba(0, 0, 0, 0.7); border-radius: 50%; width: 16px; height: 16px; display: flex; align-items: center; justify-content: center; pointer-events: none; z-index: 16; }

        #arrow-canvas { position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 20; }

        .coords-row { display: grid; grid-template-columns: repeat(8, 1fr); color: #aaa; font-size: 12px; font-weight: bold; padding: 4px 0; margin-left: 24px; margin-right: 24px; text-align: center; }
        .coords-col { display: flex; flex-direction: column; justify-content: space-around; color: #aaa; font-size: 12px; font-weight: bold; width: 24px; align-items: center; aspect-ratio: 1 / 1; }

        .text-move-box { display: flex; gap: 6px; width: 100%; max-width: 360px; margin: 6px auto; }
        .text-move-input { flex: 1; padding: 8px 12px; font-size: 14px; font-weight: bold; border: 2px solid #7b61ff; border-radius: 6px; background: #222; color: #fff; outline: none; }
        .text-move-btn { background: #00e676; color: #000; border: none; padding: 8px 16px; font-weight: bold; font-size: 14px; border-radius: 6px; cursor: pointer; }

        .pgn-container { background: #252525; border: 1px solid #444; border-radius: 6px; padding: 8px; margin: 8px auto; max-width: 360px; text-align: left; font-size: 12px; max-height: 65px; overflow-y: auto; color: #ddd; font-family: monospace; cursor: pointer; }
        .btn-reset { color: #ff5555; background: none; border: none; font-weight: bold; font-size: 15px; cursor: pointer; text-decoration: underline; margin-top: 2px; display: block; margin-left: auto; margin-right: auto; }
        .btn-exit-game { color: #ff9800; background: none; border: none; font-weight: bold; font-size: 14px; cursor: pointer; text-decoration: underline; margin-top: 4px; display: block; margin-left: auto; margin-right: auto; }

        .modal-overlay { display: flex; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0, 0, 0, 0.96); z-index: 1000; justify-content: center; align-items: center; }
        .modal-content { position: relative; background: #2b2b2b; border: 3px solid #7b61ff; border-radius: 14px; padding: 18px; width: 92%; max-width: 340px; box-shadow: 0 0 25px rgba(123, 97, 255, 0.7); animation: popup 0.25s ease-out; max-height: 90vh; overflow-y: auto; }
        .close-x-btn { position: absolute; top: 8px; right: 12px; font-size: 20px; font-weight: bold; color: #aaa; cursor: pointer; user-select: none; }

        @keyframes popup { from { transform: scale(0.8); opacity: 0; } to { transform: scale(1); opacity: 1; } }
        .modal-title { font-size: 20px; font-weight: bold; color: #ffeb3b; margin-bottom: 10px; }
        .modal-msg { font-size: 14px; color: #ddd; margin-bottom: 12px; line-height: 1.4; }

        .opt-btn { display: block; width: 100%; padding: 8px; margin: 4px 0; background: #3a3a3a; color: white; border: 2px solid #555; border-radius: 8px; font-size: 13px; font-weight: bold; cursor: pointer; }
        .opt-btn.active { background: #7b61ff; border-color: #ffeb3b; }
        .opt-btn:disabled { opacity: 0.4; cursor: not-allowed; }

        .play-btn { background: #00e676; color: #000; border: none; width: 100%; padding: 10px; font-size: 16px; font-weight: bold; border-radius: 8px; cursor: pointer; margin-top: 10px; }
        .load-btn-menu { background: #ff9800; color: #000; border: none; width: 100%; padding: 9px; font-size: 14px; font-weight: bold; border-radius: 8px; cursor: pointer; margin-top: 6px; }
        .ach-btn-menu { background: #e91e63; color: #fff; border: none; width: 100%; padding: 9px; font-size: 14px; font-weight: bold; border-radius: 8px; cursor: pointer; margin-top: 6px; }

        .shop-item { background: #1e1e1e; border: 1px solid #444; padding: 8px; border-radius: 8px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; }
        .shop-item-btn { background: #2196F3; color: white; border: none; padding: 5px 10px; font-size: 12px; font-weight: bold; border-radius: 6px; cursor: pointer; }
        .shop-item-btn.used { background: #4caf50; cursor: default; }

        .promotion-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 12px; }
        .promo-btn { background: #3a3a3a; border: 2px solid #7b61ff; border-radius: 8px; font-size: 28px; padding: 10px 0; cursor: pointer; color: #fff; }

        .music-box { background: #1a1a1a; border: 1px solid #444; padding: 8px; border-radius: 8px; margin: 8px 0; text-align: left; }
        .music-controls { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 6px; }
        .m-btn { background: #333; color: white; border: 1px solid #666; padding: 4px 8px; font-size: 11px; font-weight: bold; border-radius: 4px; cursor: pointer; flex: 1; min-width: 80px; }
        .m-btn.active { background: #00e676; color: #000; border-color: #00e676; }

        .setting-row { display: flex; justify-content: space-between; align-items: center; margin: 6px 0; font-size: 13px; font-weight: bold; }
        .modal-actions { display: flex; gap: 8px; justify-content: space-between; }
        .modal-btn-menu { flex: 1; background: #3a3a3a; color: #fff; border: 2px solid #666; padding: 8px 10px; font-size: 13px; font-weight: bold; border-radius: 6px; cursor: pointer; }
        .modal-btn-reset { flex: 1; background: #7b61ff; color: white; border: none; padding: 8px 10px; font-size: 13px; font-weight: bold; border-radius: 6px; cursor: pointer; }

        .tools-tab-header { display: flex; gap: 4px; margin-bottom: 10px; }
        .tools-tab-btn { flex: 1; background: #3a3a3a; color: #fff; border: 2px solid #555; padding: 6px; border-radius: 6px; font-size: 12px; font-weight: bold; cursor: pointer; }
        .tools-tab-btn.active { background: #00bcd4; color: #000; border-color: #ffeb3b; }
        .tools-tab-pane { display: none; text-align: left; }
        .tools-tab-pane.active { display: block; }

        .mini-chessboard { display: grid; grid-template-columns: repeat(8, 1fr); grid-template-rows: repeat(8, 1fr); border: 2px solid #444; width: 100%; aspect-ratio: 1 / 1; position: relative; margin: 4px 0; background: #222; }
        .mini-square { display: flex; align-items: center; justify-content: center; font-size: 16px; position: relative; user-select: none; }
        .mini-piece { position: absolute; width: 12.5%; height: 12.5%; display: flex; align-items: center; justify-content: center; font-size: 16px; pointer-events: none; z-index: 5; }

        .achievement-card { background: #222; border: 1px solid #444; border-radius: 8px; padding: 8px; margin-bottom: 6px; display: flex; align-items: center; gap: 10px; text-align: left; }
        .achievement-card.unlocked { border-color: #00e676; background: rgba(0,230,118,0.08); }
        .achievement-icon { font-size: 22px; min-width: 30px; text-align: center; }

        #achievement-popup { position: fixed; top: 20px; left: 50%; transform: translateX(-50%) scale(0.8); background: linear-gradient(135deg, #ffeb3b, #ff9800); color: #000; padding: 12px 20px; border-radius: 12px; font-weight: bold; font-size: 15px; z-index: 2000; box-shadow: 0 0 20px rgba(255,235,59,0.9); opacity: 0; pointer-events: none; transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275); }
        #achievement-popup.show { transform: translateX(-50%) scale(1); opacity: 1; }
    </style>
</head>
<body>
    <div id="achievement-popup">🏆 Đạt Thành Tựu Mới!</div>

    <div class="game-wrapper hidden-board" id="game-wrapper">
        <div class="header-box">
            <div class="coins-display">
                🪙 <span id="coins-count">0</span> điểm
                <span id="mode-bonus-badge" style="display:none; color:#00e676; font-size:11px;">(Ký tự x3)</span>
                <span id="double-badge" style="display:none; color:#ffeb3b; font-size:11px;">(x2)</span>
            </div>
            <div>
                <button class="tools-btn" onclick="openToolsModal()">🧰 Công cụ</button>
                <button class="save-btn" onclick="saveGame()">💾 Lưu</button>
                <button class="shop-btn" onclick="openShop()">🛍️ Shop</button>
                <button class="menu-btn" onclick="openMenu()">🏠 Menu</button>
            </div>
        </div>

        <audio id="bg-music" onended="handleSongEnded()"></audio>

        <div class="eval-box" id="eval-text">Bắt đầu ván đấu mới! Chúc bạn chơi vui vẻ 🐧</div>

        <div class="board-container">
            <div class="captured-box" id="top-captured-box">
                 <div class="captured-pieces" id="top-captured-list"></div>
                <div class="captured-score" id="top-captured-score" style="display:none;"></div>
            </div>

            <div class="coords-row" id="top-coords"></div>
            <div class="board-with-files">
                <div class="coords-col" id="left-coords"></div>
                <div style="position: relative; width: 100%;">
                    <div class="chessboard theme-default" id="board"></div>
                    <canvas id="arrow-canvas"></canvas>
                </div>
                <div class="coords-col" id="right-coords"></div>
            </div>
            <div class="coords-row" id="bot-coords"></div>

            <div class="captured-box" id="bot-captured-box">
                <div class="captured-pieces" id="bot-captured-list"></div>
                <div class="captured-score" id="bot-captured-score" style="display:none;"></div>
            </div>
        </div>

        <div class="text-move-box" id="text-move-container" style="display: none;">
            <input type="text" id="text-move-input" class="text-move-input" placeholder="Ví dụ: e4, Qh3, O-O..." onkeydown="if(event.key==='Enter') submitTextMove()">
            <button class="text-move-btn" onclick="submitTextMove()">Gửi ♟️</button>
        </div>

        <div class="pgn-container" onclick="copyMainPGN()" title="Bấm để sao chép PGN">
            <span style="color: #ffeb3b; font-weight: bold;">📜 PGN (Bấm để copy):</span><br>
            <span id="pgn-text">Chưa có nước đi</span>
        </div>

        <p style="margin: 4px 0; font-size: 14px;">Phe bạn: <b id="side-text" style="color: #00e676;">...</b> | Lượt: <b id="turn-text">...</b></p>
        <button class="btn-reset" onclick="resetGame()">🔄 Chơi lại ván mới</button>
        <button class="btn-exit-game" onclick="exitGameToMenu()">🚪 Thoát ván cờ</button>
    </div>

    <!-- CÔNG CỤ MODAL -->
    <div class="modal-overlay" id="tools-modal" style="display: none;">
        <div class="modal-content">
            <span class="close-x-btn" onclick="closeModal('tools-modal')">✕</span>
            <div class="modal-title">🧰 CÔNG CỤ HỖ TRỢ</div>
            
            <div class="tools-tab-header">
                <button class="tools-tab-btn active" id="tab-btn-hint" onclick="switchToolTab('hint')">💡 Gợi Ý</button>
                <button class="tools-tab-btn" id="tab-btn-replay" onclick="switchToolTab('replay')">⏳ Tua Nước</button>
                <button class="tools-tab-btn" id="tab-btn-editor" onclick="switchToolTab('editor')" style="display:none;">🛠️ Sửa Bàn Cờ</button>
            </div>

            <div class="tools-tab-pane active" id="pane-hint">
                <p style="font-size: 13px; color: #ddd; margin-bottom: 12px;">Xem trước nước đi tốt nhất cho lượt hiện tại của bạn.</p>
                <button class="play-btn" onclick="getHint(); closeModal('tools-modal');" style="margin-top:0;">💡 Lấy Gợi Ý (-1 Điểm)</button>
            </div>

            <div class="tools-tab-pane" id="pane-replay">
                <p style="font-size: 12px; color: #aaa; margin: 0 0 4px 0;">Xem minh họa & tua ngược nước đi (<b style="color: #ff9800;">2 đ</b>):</p>
                <div style="position: relative; width: 200px; margin: 4px auto;">
                    <div class="mini-chessboard" id="replay-mini-board"></div>
                </div>
                <div style="display: flex; gap: 6px; align-items: center; justify-content: center; margin: 6px 0;">
                    <button class="shop-item-btn" style="padding: 6px 12px; font-size: 14px;" onclick="stepReplay(-1)">&lt;</button>
                    <span id="replay-step-indicator" style="font-weight: bold; font-size: 13px; color: #ffeb3b; min-width: 80px; text-align: center;">1 / 1</span>
                    <button class="shop-item-btn" style="padding: 6px 12px; font-size: 14px;" onclick="stepReplay(1)">&gt;</button>
                </div>
                <div style="background: #1e1e1e; padding: 6px; border-radius: 6px; font-size: 11px; color: #aaa; margin-bottom: 8px; text-align: center;" id="replay-info-box">Nước: Khởi đầu</div>
                <button class="play-btn" onclick="applyReplayState()" style="background: #00bcd4; color: #000; padding: 8px; font-size: 14px;">• Đặt làm nước này & đi tiếp</button>
            </div>

            <div class="tools-tab-pane" id="pane-editor">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                    <span style="font-size: 12px; color: #ffeb3b; font-weight: bold;">🛠️ Chỉnh Sửa Bàn Cờ</span>
                    <button class="shop-item-btn" style="background: #d32f2f; padding: 3px 8px; font-size: 11px;" onclick="resetEditorBoardDefault()">🔄 Đặt lại bàn cờ</button>
                </div>
                <div style="font-size: 11px; color: #ccc; margin-bottom: 6px; line-height: 1.3;">
                    • Chọn quân dưới rồi bấm ô trên bàn cờ để đặt.<br>
                    • Chạm ô có quân để xóa hoặc thay thế.<br>
                    • Lưu ý: Bật chế độ này sẽ vô hiệu hóa nhận điểm và thành tựu!
                </div>
                
                <div style="position: relative; width: 200px; margin: 2px auto;">
                    <div class="mini-chessboard" id="editor-mini-board"></div>
                </div>

                <div style="display: flex; justify-content: center; gap: 3px; margin: 6px 0 3px 0;">
                    <button class="promo-btn" style="font-size: 18px; padding: 3px;" onclick="setEditorPiece('P')">♙</button>
                    <button class="promo-btn" style="font-size: 18px; padding: 3px;" onclick="setEditorPiece('N')">♘</button>
                    <button class="promo-btn" style="font-size: 18px; padding: 3px;" onclick="setEditorPiece('B')">♗</button>
                    <button class="promo-btn" style="font-size: 18px; padding: 3px;" onclick="setEditorPiece('R')">♖</button>
                    <button class="promo-btn" style="font-size: 18px; padding: 3px;" onclick="setEditorPiece('Q')">♕</button>
                    <button class="promo-btn" style="font-size: 18px; padding: 3px;" onclick="setEditorPiece('K')">♔</button>
                </div>
                <div style="display: flex; justify-content: center; gap: 3px; margin-bottom: 6px;">
                    <button class="promo-btn" style="font-size: 18px; padding: 3px;" onclick="setEditorPiece('p')">♟</button>
                    <button class="promo-btn" style="font-size: 18px; padding: 3px;" onclick="setEditorPiece('n')">♞</button>
                    <button class="promo-btn" style="font-size: 18px; padding: 3px;" onclick="setEditorPiece('b')">♝</button>
                    <button class="promo-btn" style="font-size: 18px; padding: 3px;" onclick="setEditorPiece('r')">♜</button>
                    <button class="promo-btn" style="font-size: 18px; padding: 3px;" onclick="setEditorPiece('q')">♛</button>
                    <button class="promo-btn" style="font-size: 18px; padding: 3px;" onclick="setEditorPiece('k')">♚</button>
                    <button class="promo-btn" style="font-size: 14px; padding: 3px; background: #d32f2f;" onclick="setEditorPiece('del')">🗑️</button>
                </div>
                <div style="font-size: 11px; color: #00e676; text-align: center; margin-bottom: 6px;" id="editor-selected-info">Đang chọn: ♙ Tốt trắng</div>
                <button class="play-btn" onclick="saveEditorChanges()" style="background: #ff9800; color: #000; padding: 7px; font-size: 13px;">💾 Lưu & Áp dụng bàn cờ</button>
            </div>
        </div>
    </div>

    <!-- MENU CHÍNH -->
    <div class="modal-overlay" id="menu-modal">
        <div class="modal-content">
            <span class="close-x-btn" id="menu-close-x" style="display: none;" onclick="closeModal('menu-modal')">✕</span>

            <div class="modal-title">🎮 MENU CHÍNH</div>
            
            <p style="text-align: left; font-size: 12px; color: #aaa; margin: 4px 0 2px 0;">1. Cách chơi:</p>
            <div style="display: flex; gap: 4px;">
                <button class="opt-btn" id="btn-mode-click" onclick="setControlMode('click')">🖱️ Click Bàn Cờ</button>
                <button class="opt-btn" id="btn-mode-text" onclick="setControlMode('text')">⌨️ Nhập Ký Tự (x3 Xu)</button>
            </div>

            <p style="text-align: left; font-size: 12px; color: #aaa; margin: 6px 0 2px 0;">2. Chọn phe chơi:</p>
            <div style="display: flex; gap: 4px;">
                <button class="opt-btn" id="btn-side-white" onclick="setSide('white')">⚪ Trắng</button>
                <button class="opt-btn" id="btn-side-black" onclick="setSide('black')">⬛ Đen</button>
                <button class="opt-btn" id="btn-side-random" onclick="setSide('random')">🎲 Random</button>
            </div>

            <p style="text-align: left; font-size: 12px; color: #aaa; margin: 6px 0 2px 0;">3. Chọn độ khó AI:</p>
            <button class="opt-btn" id="btn-easy" onclick="setDifficulty('easy')">🐣 Dễ (Thắng +2đ | Hòa +1đ)</button>
            <button class="opt-btn" id="btn-medium" onclick="setDifficulty('medium')">⚖️ Vừa (Thắng +4đ | Hòa +2đ)</button>
            <button class="opt-btn" id="btn-hard" onclick="setDifficulty('hard')">👹 Khó (Thắng +10đ | Hòa +5đ)</button>

            <div class="music-box">
                <div class="setting-row" style="margin:0;">
                    <span>🎵 Nhạc nền Chill:</span>
                    <button class="menu-btn" id="music-toggle-btn" onclick="toggleMusic()" style="background: #555;">Tắt 🔇</button>
                </div>
                <div style="font-size: 11px; color: #ffeb3b; margin-top: 4px;" id="current-song-display">Bài: music_chess1.mp3</div>
                <div class="music-controls">
                    <button class="m-btn" id="btn-loop-one" onclick="toggleLoopSingle()">🔁 Lặp 1 bài: TẮT</button>
                    <button class="m-btn" onclick="nextSong()">⏭️ Bài tiếp</button>
                </div>
            </div>

            <button class="play-btn" onclick="startGame()">▶️ TIẾP TỤC / VÁN MỚI</button>
            <button class="load-btn-menu" id="load-save-btn" onclick="loadSavedGame()" style="display:none;">📂 TẢI GAME ĐÃ LƯU</button>
            <button class="ach-btn-menu" onclick="openAchievementsModal()">🏆 THÀNH TỰU</button>
            
            <div style="display: flex; gap: 6px; margin-top: 6px;">
                <button class="shop-item-btn" style="flex:1; background:#d32f2f; padding:8px;" onclick="confirmClearData()">🗑️ Xóa Dữ Liệu</button>
            </div>
        </div>
    </div>

    <!-- THÀNH TỰU MODAL -->
    <div class="modal-overlay" id="achievements-modal" style="display: none;">
        <div class="modal-content">
            <span class="close-x-btn" onclick="closeModal('achievements-modal')">✕</span>
            <div class="modal-title">🏆 BẢNG THÀNH TỰU</div>
            <p style="font-size: 11px; color: #aaa; margin-top: -6px;">Hoàn thành thử thách trong ván đấu thường để mở khóa.</p>
            <div id="achievements-list-container" style="max-height: 280px; overflow-y: auto;"></div>
            <button class="shop-item-btn" style="background: #d32f2f; width: 100%; margin-top: 10px; padding: 8px;" onclick="confirmClearAchievements()">🗑️ Xóa Thành Tựu</button>
        </div>
    </div>

    <!-- XÁC NHẬN XÓA DỮ LIỆU MODAL -->
    <div class="modal-overlay" id="confirm-modal" style="display: none;">
        <div class="modal-content" style="border-color: #d32f2f;">
            <div class="modal-title" style="color: #ff5555;">⚠️ XÁC NHẬN XÓA</div>
            <div class="modal-msg" id="confirm-msg">Bạn có chắc chắn muốn xóa toàn bộ dữ liệu game? Thao tác này không thể hoàn tác!</div>
            <div class="modal-actions">
                <button class="modal-btn-menu" onclick="closeModal('confirm-modal')">Hủy</button>
                <button class="modal-btn-reset" style="background: #d32f2f;" id="confirm-action-btn" onclick="executeClearData()">Đồng Ý Xóa</button>
            </div>
        </div>
    </div>

    <!-- PROMOTION MODAL -->
    <div class="modal-overlay" id="promotion-modal" style="display: none;">
        <div class="modal-content">
            <div class="modal-title">⭐ PHONG CẤP TỐT</div>
            <div class="modal-msg">Chọn 1 trong 4 quân cờ bạn muốn phong:<br><span style="font-size: 11px; color: #aaa;">(Tốt phong cấp khi đến hàng cuối cùng)</span></div>
            <div class="promotion-grid">
                <button class="promo-btn" onclick="selectPromotion('Q')">♕</button>
                <button class="promo-btn" onclick="selectPromotion('R')">♖</button>
                <button class="promo-btn" onclick="selectPromotion('B')">♗</button>
                <button class="promo-btn" onclick="selectPromotion('N')">♘</button>
            </div>
        </div>
    </div>

    <!-- SHOP MODAL -->
    <div class="modal-overlay" id="shop-modal" style="display: none;">
        <div class="modal-content">
            <span class="close-x-btn" onclick="closeModal('shop-modal')">✕</span>
            <div class="modal-title">🛍️ CỬA HÀNG BÀN CỜ</div>
            <p style="font-size: 11px; color: #aaa; margin-top: -6px;">Tích lũy xu từ các ván đấu để mua vật phẩm.</p>
            <div id="shop-items-container"></div>
        </div>
    </div>

    <!-- GAME OVER MODAL -->
    <div class="modal-overlay" id="game-modal" style="display: none;">
        <div class="modal-content">
            <span class="close-x-btn" onclick="closeModal('game-modal')">✕</span>
            <div class="modal-title" id="modal-title">THÔNG BÁO</div>
            <div class="modal-msg" id="modal-msg">Nội dung...</div>
            <div class="modal-actions">
                <button class="modal-btn-menu" onclick="closeModal('game-modal'); openMenu();">🎮 Menu</button>
                <button class="modal-btn-reset" onclick="resetGame(); closeModal('game-modal');">🔄 Ván Mới</button>
            </div>
        </div>
    </div>

    <script>
        let boardData = {};
        let legalMoves = [];
        let currentTurn = "w";
        let userColor = "w";
        let userSideSetting = "white";
        let currentDifficulty = "easy";
        let currentControlMode = "click";
        let statusInfo = {is_over: false};
        let lastTarget = null;
        let lastBadge = "";
        let currentPgn = "";
        let capturedData = { white_captured: [], black_captured: [], white_lead: 0, black_lead: 0 };
        
        let selectedSquare = null;
        let validTargets = [];
        let hintMove = null;
        let isAiThinking = false;
        let isGameStarted = false;
        let isModalShown = false;
        let pendingPromotionMove = null;

        let replayStatesList = [];
        let currentReplayIndex = 0;
        let editorSelectedPiece = 'P';
        let editorBoardFenMap = {};

        let playlist = ["music_chess1.mp3"];
        let currentTrackIndex = 0;
        let isLoopSingle = false;
        let isMusicPlaying = false;
        const musicAudio = document.getElementById('bg-music');

        async function fetchPlaylist() {
            try {
                let res = await fetch('/get-playlist');
                let data = await res.json();
                if (data.playlist && data.playlist.length > 0) playlist = data.playlist;
            } catch (e) { console.log(e); }
            updateMusicUI();
        }

        function playCurrentTrack() {
            if (!playlist || playlist.length === 0) return;
            let filename = playlist[currentTrackIndex];
            musicAudio.src = '/play-music/' + encodeURIComponent(filename);
            if (isMusicPlaying) musicAudio.play().catch(e => console.log(e));
            updateMusicUI();
        }

        function handleSongEnded() {
            if (isLoopSingle) {
                musicAudio.currentTime = 0;
                musicAudio.play().catch(e => console.log(e));
            } else {
                currentTrackIndex = (currentTrackIndex + 1) % playlist.length;
                playCurrentTrack();
            }
        }

        function nextSong() {
            currentTrackIndex = (currentTrackIndex + 1) % playlist.length;
            playCurrentTrack();
        }

        function toggleLoopSingle() {
            isLoopSingle = !isLoopSingle;
            updateMusicUI();
        }

        function toggleMusic() {
            let btn = document.getElementById('music-toggle-btn');
            if (isMusicPlaying) {
                musicAudio.pause();
                btn.innerText = "Tắt 🔇";
                btn.style.background = "#555";
                isMusicPlaying = false;
            } else {
                if (!musicAudio.src) playCurrentTrack();
                else {
                    musicAudio.play().then(() => {
                        btn.innerText = "Bật 🔊";
                        btn.style.background = "#7b61ff";
                        isMusicPlaying = true;
                    }).catch(e => console.log("Audio error:", e));
                }
            }
        }

        function updateMusicUI() {
            let loopBtn = document.getElementById('btn-loop-one');
            if (isLoopSingle) {
                loopBtn.innerText = "🔁 Lặp 1 bài: BẬT";
                loopBtn.classList.add('active');
            } else {
                loopBtn.innerText = "🔁 Lặp 1 bài: TẮT";
                loopBtn.classList.remove('active');
            }
            let songDisplay = document.getElementById('current-song-display');
            if (playlist.length > 0) {
                songDisplay.innerText = "Bài (" + (currentTrackIndex + 1) + "/" + playlist.length + "): " + playlist[currentTrackIndex];
            } else {
                songDisplay.innerText = "Chưa có nhạc";
            }
        }

        async function setControlMode(mode) {
            if (isGameStarted) return;
            currentControlMode = mode;
            updateMenuUI();
            await fetch('/set-settings', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ side_setting: userSideSetting, difficulty: currentDifficulty, mode: currentControlMode })
            });
        }

        async function setSide(side) {
            if (isGameStarted) return;
            userSideSetting = side;
            updateMenuUI();
            let res = await fetch('/set-settings', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ side_setting: side, difficulty: currentDifficulty, mode: currentControlMode })
            });
            let data = await res.json();
            syncBoardData(data);
        }

        async function setDifficulty(level) {
            if (isGameStarted) return;
            currentDifficulty = level;
            updateMenuUI();
            await fetch('/set-settings', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ side_setting: userSideSetting, difficulty: level, mode: currentControlMode })
            });
        }

        function updateMenuUI() {
            let btnClick = document.getElementById('btn-mode-click');
            let btnText = document.getElementById('btn-mode-text');
            btnClick.classList.remove('active');
            btnText.classList.remove('active');

            if (currentControlMode === 'click') btnClick.classList.add('active');
            else btnText.classList.add('active');

            document.getElementById('btn-side-white').classList.remove('active');
            document.getElementById('btn-side-black').classList.remove('active');
            document.getElementById('btn-side-random').classList.remove('active');
            document.getElementById('btn-side-' + userSideSetting).classList.add('active');

            document.getElementById('btn-easy').classList.remove('active');
            document.getElementById('btn-medium').classList.remove('active');
            document.getElementById('btn-hard').classList.remove('active');
            document.getElementById('btn-' + currentDifficulty).classList.add('active');

            let settingButtons = [
                'btn-mode-click', 'btn-mode-text', 
                'btn-side-white', 'btn-side-black', 'btn-side-random', 
                'btn-easy', 'btn-medium', 'btn-hard'
            ];
            settingButtons.forEach(id => {
                let el = document.getElementById(id);
                if (el) el.disabled = isGameStarted;
            });

            document.getElementById('side-text').innerText = (userColor === 'w') ? 'Trắng (♔)' : 'Đen (♚)';
            document.getElementById('mode-bonus-badge').style.display = (currentControlMode === 'text') ? 'inline' : 'none';
            document.getElementById('text-move-container').style.display = (currentControlMode === 'text') ? 'flex' : 'none';

            updateMusicUI();
        }

        async function openMenu() {
            let closeBtn = document.getElementById('menu-close-x');
            closeBtn.style.display = isGameStarted ? 'block' : 'none';
            document.getElementById('game-wrapper').classList.add('hidden-board');
            
            let res = await fetch('/check-save');
            let data = await res.json();
            document.getElementById('load-save-btn').style.display = data.has_save ? 'block' : 'none';

            updateMenuUI();
            document.getElementById('menu-modal').style.display = 'flex';
        }

        function exitGameToMenu() {
            isGameStarted = false;
            let closeBtn = document.getElementById('menu-close-x');
            closeBtn.style.display = 'none';
            document.getElementById('game-wrapper').classList.add('hidden-board');
            updateMenuUI();
            document.getElementById('menu-modal').style.display = 'flex';
        }

        async function openShop() {
            fetchShopData();
            document.getElementById('shop-modal').style.display = 'flex';
        }

        async function openAchievementsModal() {
            let res = await fetch('/achievements-data');
            let data = await res.json();
            
            let container = document.getElementById('achievements-list-container');
            container.innerHTML = '';
            
            for (let id in data.definitions) {
                let def = data.definitions[id];
                let isUnlocked = data.unlocked.includes(id);
                let div = document.createElement('div');
                div.className = 'achievement-card ' + (isUnlocked ? 'unlocked' : '');
                div.innerHTML = `
                    <div class="achievement-icon">${isUnlocked ? '🏆' : '🔒'}</div>
                    <div>
                        <div style="font-weight: bold; font-size: 13px; color: ${isUnlocked ? '#00e676' : '#ccc'}">${def.name}</div>
                        <div style="font-size: 11px; color: #aaa;">${def.desc}</div>
                    </div>
                `;
                container.appendChild(div);
            }
            document.getElementById('achievements-modal').style.display = 'flex';
        }

        function confirmClearData() {
            document.getElementById('confirm-msg').innerText = "Bạn có chắc chắn muốn xóa toàn bộ dữ liệu game (Điểm, Cửa hàng, Thành tựu, Lưu game)? Thao tác này không thể hoàn tác!";
            document.getElementById('confirm-action-btn').onclick = executeClearData;
            document.getElementById('confirm-modal').style.display = 'flex';
        }

        function confirmClearAchievements() {
            document.getElementById('confirm-msg').innerText = "Bạn có chắc chắn muốn xóa tất cả thành tựu đã đạt được?";
            document.getElementById('confirm-action-btn').onclick = executeClearAchievements;
            document.getElementById('confirm-modal').style.display = 'flex';
        }

        async function executeClearData() {
            let res = await fetch('/clear-all-data', { method: 'POST' });
            let data = await res.json();
            if (data.success) {
                closeModal('confirm-modal');
                closeModal('menu-modal');
                alert("🗑️ Đã xóa sạch dữ liệu!");
                window.location.reload();
            }
        }

        async function executeClearAchievements() {
            let res = await fetch('/clear-achievements', { method: 'POST' });
            let data = await res.json();
            if (data.success) {
                closeModal('confirm-modal');
                closeModal('achievements-modal');
                alert("🗑️ Đã xóa toàn bộ thành tựu!");
            }
        }

        async function openToolsModal() {
            if (!isGameStarted || (statusInfo && statusInfo.is_over)) return;
            
            let res = await fetch('/shop-data');
            let data = await res.json();
            let hasEditor = data.has_editor;
            
            let editorHeaderBtn = document.getElementById('tab-btn-editor');
            if (hasEditor) {
                editorHeaderBtn.style.display = 'block';
            } else {
                editorHeaderBtn.style.display = 'none';
            }

            fetchReplayData();
            document.getElementById('tools-modal').style.display = 'flex';
        }

        function switchToolTab(tabName) {
            let btnHint = document.getElementById('tab-btn-hint');
            let btnReplay = document.getElementById('tab-btn-replay');
            let btnEditor = document.getElementById('tab-btn-editor');
            let paneHint = document.getElementById('pane-hint');
            let paneReplay = document.getElementById('pane-replay');
            let paneEditor = document.getElementById('pane-editor');

            btnHint.classList.remove('active');
            btnReplay.classList.remove('active');
            btnEditor.classList.remove('active');
            paneHint.classList.remove('active');
            paneReplay.classList.remove('active');
            paneEditor.classList.remove('active');

            if (tabName === 'hint') {
                btnHint.classList.add('active');
                paneHint.classList.add('active');
            } else if (tabName === 'replay') {
                btnReplay.classList.add('active');
                paneReplay.classList.add('active');
            } else if (tabName === 'editor') {
                btnEditor.classList.add('active');
                paneEditor.classList.add('active');
                fetchEditorData();
            }
        }

        async function fetchReplayData() {
            let res = await fetch('/get-replay-states');
            let data = await res.json();
            if (data.success) {
                replayStatesList = data.states;
                currentReplayIndex = replayStatesList.length - 1;
                updateReplayUI();
            }
        }

        function stepReplay(direction) {
            if (!replayStatesList.length) return;
            currentReplayIndex += direction;
            if (currentReplayIndex < 0) currentReplayIndex = 0;
            if (currentReplayIndex >= replayStatesList.length) currentReplayIndex = replayStatesList.length - 1;
            updateReplayUI();
        }

        function updateReplayUI() {
            let indicator = document.getElementById('replay-step-indicator');
            let infoBox = document.getElementById('replay-info-box');
            let miniBoard = document.getElementById('replay-mini-board');
            
            indicator.innerText = `${currentReplayIndex + 1} / ${replayStatesList.length}`;
            
            if (replayStatesList.length > 0) {
                let st = replayStatesList[currentReplayIndex];
                let lastMoveStr = st.pgn.length > 0 ? st.pgn[st.pgn.length - 1] : "Khởi đầu";
                infoBox.innerHTML = `Nước thứ ${currentReplayIndex} | Gần nhất: <b style="color:#00e676">${lastMoveStr}</b>`;
                
                miniBoard.innerHTML = '';
                const files = (userColor === 'w') ? ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'] : ['h', 'g', 'f', 'e', 'd', 'c', 'b', 'a'];
                const ranks = (userColor === 'w') ? ['8', '7', '6', '5', '4', '3', '2', '1'] : ['1', '2', '3', '4', '5', '6', '7', '8'];

                for (let r = 0; r < 8; r++) {
                    for (let c = 0; c < 8; c++) {
                        let isDark = (r + c) % 2 === 1;
                        let sqDiv = document.createElement('div');
                        sqDiv.className = 'mini-square';
                        sqDiv.style.backgroundColor = isDark ? '#b58863' : '#f0d9b5';
                        miniBoard.appendChild(sqDiv);
                    }
                }

                for (let r = 0; r < 8; r++) {
                    for (let c = 0; c < 8; c++) {
                        let sqName = files[c] + ranks[r];
                        let sqInfo = st.board[sqName];
                        if (sqInfo && sqInfo.piece) {
                            let pDiv = document.createElement('div');
                            pDiv.className = 'mini-piece';
                            pDiv.innerText = sqInfo.piece;
                            pDiv.style.transform = `translate(${c * 100}%, ${r * 100}%)`;
                            miniBoard.appendChild(pDiv);
                        }
                    }
                }
            }
        }

        async function applyReplayState() {
            if (!replayStatesList.length) return;
            let targetState = replayStatesList[currentReplayIndex];

            let res = await fetch('/apply-replay', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ fen: targetState.fen, step_index: currentReplayIndex })
            });
            let data = await res.json();
            if (data.success) {
                syncBoardData(data);
                renderBoard();
                closeModal('tools-modal');
                alert("⏳ Đã tua nước đi thành công! (-2 Điểm)");
            } else {
                alert(data.message);
            }
        }

        async function fetchEditorData() {
            let res = await fetch('/get-editor-board');
            let data = await res.json();
            if (data.success) {
                editorBoardFenMap = data.board;
                renderEditorMiniBoard();
            }
        }

        async function resetEditorBoardDefault() {
            let res = await fetch('/get-default-editor-board');
            let data = await res.json();
            if (data.success) {
                editorBoardFenMap = data.board;
                renderEditorMiniBoard();
            }
        }

        function setEditorPiece(pieceKey) {
            editorSelectedPiece = pieceKey;
            let names = {
                'P': '♙ Tốt trắng', 'N': '♘ Mã trắng', 'B': '♗ Tượng trắng', 'R': '♖ Xe trắng', 'Q': '♕ Hậu trắng', 'K': '♔ Vua trắng',
                'p': '♟ Tốt đen', 'n': '♞ Mã đen', 'b': '♝ Tượng đen', 'r': '♜ Xe đen', 'q': '♛ Hậu đen', 'k': '♚ Vua đen', 'del': '🗑️ Xóa quân'
            };
            document.getElementById('editor-selected-info').innerText = "Đang chọn: " + (names[pieceKey] || pieceKey);
        }

        function renderEditorMiniBoard() {
            let miniBoard = document.getElementById('editor-mini-board');
            miniBoard.innerHTML = '';
            
            const files = (userColor === 'w') ? ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'] : ['h', 'g', 'f', 'e', 'd', 'c', 'b', 'a'];
            const ranks = (userColor === 'w') ? ['8', '7', '6', '5', '4', '3', '2', '1'] : ['1', '2', '3', '4', '5', '6', '7', '8'];

            for (let r = 0; r < 8; r++) {
                for (let c = 0; c < 8; c++) {
                    let isDark = (r + c) % 2 === 1;
                    let sqName = files[c] + ranks[r];
                    let sqDiv = document.createElement('div');
                    sqDiv.className = 'mini-square';
                    sqDiv.style.backgroundColor = isDark ? '#b58863' : '#f0d9b5';
                    sqDiv.style.cursor = 'pointer';
                    sqDiv.onclick = () => handleEditorSquareClick(sqName);
                    miniBoard.appendChild(sqDiv);
                }
            }

            for (let r = 0; r < 8; r++) {
                for (let c = 0; c < 8; c++) {
                    let sqName = files[c] + ranks[r];
                    let sqInfo = editorBoardFenMap[sqName];
                    if (sqInfo && sqInfo.piece) {
                        let pDiv = document.createElement('div');
                        pDiv.className = 'mini-piece';
                        pDiv.innerText = sqInfo.piece;
                        pDiv.style.transform = `translate(${c * 100}%, ${r * 100}%)`;
                        miniBoard.appendChild(pDiv);
                    }
                }
            }
        }

        function handleEditorSquareClick(sqName) {
            if (editorSelectedPiece === 'del') {
                editorBoardFenMap[sqName] = {piece: "", color: ""};
            } else {
                let symbolMap = {
                    'P': '♙', 'N': '♘', 'B': '♗', 'R': '♖', 'Q': '♕', 'K': '♔',
                    'p': '♟', 'n': '♞', 'b': '♝', 'r': '♜', 'q': '♛', 'k': '♚'
                };
                let colorChar = editorSelectedPiece === editorSelectedPiece.toUpperCase() ? 'w' : 'b';
                editorBoardFenMap[sqName] = {
                    piece: symbolMap[editorSelectedPiece],
                    color: colorChar
                };
            }
            renderEditorMiniBoard();
        }

        async function saveEditorChanges() {
            let res = await fetch('/apply-editor-board', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ board_map: editorBoardFenMap })
            });
            let data = await res.json();
            if (data.success) {
                syncBoardData(data);
                renderBoard();
                closeModal('tools-modal');
                alert("🛠️ Đã cập nhật bàn cờ tùy chỉnh thành công! (Chế độ tùy chỉnh đã bật)");
            } else {
                alert(data.message);
            }
        }

        function closeModal(id) { 
            document.getElementById(id).style.display = 'none'; 
            if (['menu-modal', 'shop-modal', 'tools-modal', 'achievements-modal'].includes(id) && isGameStarted) {
                document.getElementById('game-wrapper').classList.remove('hidden-board');
            }
        }

        async function startGame() {
            closeModal('menu-modal');
            isGameStarted = true;
            document.getElementById('game-wrapper').classList.remove('hidden-board');
            renderBoard();
            
            if (currentTurn !== userColor && !statusInfo.is_over && !isAiThinking) {
                isAiThinking = true;
                renderBoard();
                setTimeout(triggerAiMove, 400);
            }
        }

        async function saveGame() {
            let res = await fetch('/save-game', { method: 'POST' });
            let data = await res.json();
            if (data.success) alert('💾 Đã lưu game thành công!');
            else alert('Lỗi lưu game: ' + data.message);
        }

        async function loadSavedGame() {
            let res = await fetch('/load-game', { method: 'POST' });
            let data = await res.json();
            if (data.success) {
                closeModal('menu-modal');
                isGameStarted = true;
                document.getElementById('game-wrapper').classList.remove('hidden-board');
                syncBoardData(data);
                applyTheme(data.current_theme);
                renderBoard();
                alert('📂 Tải lại game thành công!');

                if (currentTurn !== userColor && !statusInfo.is_over) {
                    isAiThinking = true;
                    renderBoard();
                    setTimeout(triggerAiMove, 400);
                }
            } else alert('Không tìm thấy bản lưu cũ!');
        }

        async function getHint() {
            if (!isGameStarted || currentTurn !== userColor || isAiThinking || (statusInfo && statusInfo.is_over)) return;
            let res = await fetch('/get-hint', { method: 'POST' });
            let data = await res.json();
            if (!data.success) {
                alert(data.message);
                return;
            }
            document.getElementById('coins-count').innerText = data.coins;
            hintMove = data.hint_move;
            renderBoard();
        }

        async function resetGame() {
            let res = await fetch('/reset', { method: 'POST' });
            let data = await res.json();
            isModalShown = false;
            hintMove = null;
            syncBoardData(data);
            selectedSquare = null;
            validTargets = [];
            closeModal('game-modal');
            isGameStarted = true;
            document.getElementById('game-wrapper').classList.remove('hidden-board');
            renderBoard();

            if (currentTurn !== userColor && !statusInfo.is_over) {
                isAiThinking = true;
                renderBoard();
                setTimeout(triggerAiMove, 400);
            }
        }

        function showAchievementPopup(achName) {
            let popup = document.getElementById('achievement-popup');
            popup.innerText = `🏆 Mở khóa Thành Tựu: ${achName}!`;
            popup.classList.add('show');
            setTimeout(() => {
                popup.classList.remove('show');
            }, 3500);
        }

        function syncBoardData(data) {
            boardData = data.board;
            legalMoves = data.legal_moves;
            currentTurn = data.turn;
            userColor = data.user_color;
            statusInfo = data.status;
            lastTarget = data.last_target;
            lastBadge = data.last_badge;
            currentPgn = data.pgn || "Chưa có nước đi";
            if (data.captured) capturedData = data.captured;
            if (data.difficulty) currentDifficulty = data.difficulty;
            if (data.user_side_setting) userSideSetting = data.user_side_setting;
            if (data.control_mode) currentControlMode = data.control_mode;

            document.getElementById('eval-text').innerText = data.eval;
            document.getElementById('pgn-text').innerText = currentPgn;
            document.getElementById('coins-count').innerText = data.coins;
            document.getElementById('double-badge').style.display = data.has_double ? 'inline' : 'none';
            updateMenuUI();

            if (statusInfo && statusInfo.is_over && !isModalShown) {
                isModalShown = true;
                if (statusInfo.achievement) {
                    showAchievementPopup(statusInfo.achievement);
                }
                setTimeout(() => {
                    document.getElementById('modal-title').innerText = statusInfo.title;
                    document.getElementById('modal-msg').innerText = statusInfo.message;
                    document.getElementById('game-modal').style.display = 'flex';
                }, 300);
            }
        }

        async function fetchShopData() {
            let res = await fetch('/shop-data');
            let data = await res.json();
            document.getElementById('coins-count').innerText = data.coins;
            
            let container = document.getElementById('shop-items-container');
            container.innerHTML = '';

            let dblDiv = document.createElement('div');
            dblDiv.className = 'shop-item';
            let dblBtn = data.has_double 
                ? `<button class="shop-item-btn used">Đã sở hữu</button>`
                : `<button class="shop-item-btn" style="background:#ff9800;" onclick="buyDoubleCoins()">Mua (20đ)</button>`;
            dblDiv.innerHTML = `
                <div style="text-align: left;">
                    <div style="font-weight: bold; font-size: 14px; color:#ffeb3b;">⚡ Thẻ x2 Điểm Thưởng</div>
                    <div style="font-size: 11px; color: #aaa;">Nhân đôi điểm Thắng/Hòa | Thua +1đ</div>
                </div>
                <div>${dblBtn}</div>
            `;
            container.appendChild(dblDiv);

            let editorDiv = document.createElement('div');
            editorDiv.className = 'shop-item';
            let editorBtn = data.has_editor
                ? `<button class="shop-item-btn used">Đã sở hữu</button>`
                : `<button class="shop-item-btn" style="background:#00bcd4; color:#000;" onclick="buyEditor()">Mua (35đ)</button>`;
            editorDiv.innerHTML = `
                <div style="text-align: left;">
                    <div style="font-weight: bold; font-size: 14px; color:#00bcd4;">🛠️ Mở khóa Chỉnh Sửa Bàn Cờ</div>
                    <div style="font-size: 11px; color: #aaa;">Sửa thế cờ, đặt tùy ý quân cờ</div>
                </div>
                <div>${editorBtn}</div>
            `;
            container.appendChild(editorDiv);

            data.themes.forEach(item => {
                let div = document.createElement('div');
                div.className = 'shop-item';
                let isUnlocked = data.unlocked.includes(item.id);
                let isCurrent = (data.current === item.id);

                let btnHtml = '';
                if (isCurrent) btnHtml = `<button class="shop-item-btn used">Đang dùng</button>`;
                else if (isUnlocked) btnHtml = `<button class="shop-item-btn" onclick="useTheme('${item.id}')">Dùng</button>`;
                else btnHtml = `<button class="shop-item-btn" style="background:#ff9800;" onclick="buyTheme('${item.id}')">Mua (${item.cost}đ)</button>`;

                div.innerHTML = `
                    <div style="text-align: left;">
                        <div style="font-weight: bold; font-size: 14px;">${item.name}</div>
                        <div style="font-size: 11px; color: #aaa;">${item.desc}</div>
                    </div>
                    <div>${btnHtml}</div>
                `;
                container.appendChild(div);
            });
        }

        async function buyDoubleCoins() {
            let res = await fetch('/buy-double-coins', { method: 'POST' });
            let data = await res.json();
            if (data.success) {
                document.getElementById('double-badge').style.display = 'inline';
                fetchShopData();
            } else alert(data.message);
        }

        async function buyEditor() {
            let res = await fetch('/buy-editor', { method: 'POST' });
            let data = await res.json();
            if (data.success) {
                fetchShopData();
                alert("🛠️ Mở khóa tính năng Chỉnh sửa bàn cờ thành công!");
            } else alert(data.message);
        }

        async function buyTheme(themeId) {
            let res = await fetch('/buy-theme', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ theme_id: themeId })
            });
            let data = await res.json();
            if (data.success) {
                applyTheme(data.current);
                fetchShopData();
            } else alert(data.message);
        }

        async function useTheme(themeId) {
            let res = await fetch('/use-theme', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ theme_id: themeId })
            });
            let data = await res.json();
            if (data.success) {
                applyTheme(data.current);
                fetchShopData();
            }
        }

        function applyTheme(themeId) {
            let boardDiv = document.getElementById('board');
            boardDiv.className = 'chessboard theme-' + themeId;
        }

        function renderCoords(files, ranks) {
            document.getElementById('top-coords').innerHTML = files.map(f => `<span>${f}</span>`).join('');
            document.getElementById('bot-coords').innerHTML = files.map(f => `<span>${f}</span>`).join('');
            document.getElementById('left-coords').innerHTML = ranks.map(r => `<span>${r}</span>`).join('');
            document.getElementById('right-coords').innerHTML = ranks.map(r => `<span>${r}</span>`).join('');
        }

        function renderCapturedPieces() {
            let topList = document.getElementById('top-captured-list');
            let botList = document.getElementById('bot-captured-list');
            let topScore = document.getElementById('top-captured-score');
            let botScore = document.getElementById('bot-captured-score');

            topList.innerHTML = '';
            botList.innerHTML = '';

            let userCaptured = (userColor === 'w') ? capturedData.white_captured : capturedData.black_captured;
            let aiCaptured = (userColor === 'w') ? capturedData.black_captured : capturedData.white_captured;
            let userLead = (userColor === 'w') ? capturedData.white_lead : capturedData.black_lead;
            let aiLead = (userColor === 'w') ? capturedData.black_lead : capturedData.white_lead;

            aiCaptured.forEach(symbol => {
                let span = document.createElement('span');
                span.innerText = symbol;
                topList.appendChild(span);
            });
            if (aiLead > 0) {
                topScore.innerText = `+${aiLead}`;
                topScore.style.display = 'inline-block';
            } else topScore.style.display = 'none';

            userCaptured.forEach(symbol => {
                let span = document.createElement('span');
                span.innerText = symbol;
                botList.appendChild(span);
            });
            if (userLead > 0) {
                botScore.innerText = `+${userLead}`;
                botScore.style.display = 'inline-block';
            } else botScore.style.display = 'none';
        }

        function drawHintArrow(fromSq, toSq, files, ranks) {
            let canvas = document.getElementById('arrow-canvas');
            let boardDiv = document.getElementById('board');
            if (!boardDiv || !canvas) return;

            let rect = boardDiv.getBoundingClientRect();
            canvas.width = rect.width;
            canvas.height = rect.height;

            let ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            if (!fromSq || !toSq) return;

            let fromC = files.indexOf(fromSq[0]);
            let fromR = ranks.indexOf(fromSq[1]);
            let toC = files.indexOf(toSq[0]);
            let toR = ranks.indexOf(toSq[1]);

            if (fromC === -1 || fromR === -1 || toC === -1 || toR === -1) return;

            let sqSize = canvas.width / 8;
            let fromX = (fromC + 0.5) * sqSize;
            let fromY = (fromR + 0.5) * sqSize;
            let toX = (toC + 0.5) * sqSize;
            let toY = (toR + 0.5) * sqSize;

            let headlen = 16;
            let angle = Math.atan2(toY - fromY, toX - fromX);

            ctx.strokeStyle = '#00e676';
            ctx.fillStyle = '#00e676';
            ctx.lineWidth = 6;
            ctx.lineCap = 'round';

            ctx.beginPath();
            ctx.moveTo(fromX, fromY);
            ctx.lineTo(toX, toY);
            ctx.stroke();

            ctx.beginPath();
            ctx.moveTo(toX, toY);
            ctx.lineTo(toX - headlen * Math.cos(angle - Math.PI / 6), toY - headlen * Math.sin(angle - Math.PI / 6));
            ctx.lineTo(toX - headlen * Math.cos(angle + Math.PI / 6), toY - headlen * Math.sin(angle + Math.PI / 6));
            ctx.lineTo(toX, toY);
            ctx.fill();
        }

        function renderBoard() {
            renderCapturedPieces();
            let boardDiv = document.getElementById('board');
            boardDiv.innerHTML = '';
            
            const files = (userColor === 'w') ? ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'] : ['h', 'g', 'f', 'e', 'd', 'c', 'b', 'a'];
            const ranks = (userColor === 'w') ? ['8', '7', '6', '5', '4', '3', '2', '1'] : ['1', '2', '3', '4', '5', '6', '7', '8'];

            renderCoords(files, ranks);

            if (isAiThinking) {
                document.getElementById('turn-text').innerText = '🤖 AI đang tính...';
            } else {
                let isUserTurn = (currentTurn === userColor);
                document.getElementById('turn-text').innerText = isUserTurn ? '👉 Lượt BẠN' : '⏳ Lượt AI';
            }

            let hintFrom = hintMove ? hintMove.substring(0, 2) : null;
            let hintTo = hintMove ? hintMove.substring(2, 4) : null;

            for (let r = 0; r < 8; r++) {
                for (let c = 0; c < 8; c++) {
                    let sqName = files[c] + ranks[r];
                    let sqInfo = boardData[sqName];
                    let isDark = (r + c) % 2 === 1;

                    let sqDiv = document.createElement('div');
                    sqDiv.className = 'square ' + (isDark ? 'dark' : 'light');
                    if (sqName === selectedSquare) sqDiv.classList.add('selected');
                    if (sqName === hintFrom) sqDiv.classList.add('hint-source');

                    if (validTargets.includes(sqName)) {
                        let dot = document.createElement('div');
                        dot.className = 'dot';
                        sqDiv.appendChild(dot);
                    }

                    if (sqName === lastTarget && lastBadge) {
                        let badgeDiv = document.createElement('div');
                        badgeDiv.className = 'eval-badge';
                        if (['?', '??'].includes(lastBadge)) badgeDiv.style.color = '#ff3333';
                        badgeDiv.innerText = lastBadge;
                        sqDiv.appendChild(badgeDiv);
                    }

                    if (sqInfo && sqInfo.king_badge) {
                        let kingBadge = document.createElement('div');
                        kingBadge.className = 'king-status-badge';
                        kingBadge.innerText = sqInfo.king_badge;
                        sqDiv.appendChild(kingBadge);
                    }

                    sqDiv.onclick = () => handleSquareClick(sqName, sqInfo);
                    boardDiv.appendChild(sqDiv);
                }
            }

            for (let r = 0; r < 8; r++) {
                for (let c = 0; c < 8; c++) {
                    let sqName = files[c] + ranks[r];
                    let sqInfo = boardData[sqName];
                    if (sqInfo && sqInfo.piece) {
                        let pDiv = document.createElement('div');
                        pDiv.className = 'piece-element';
                        pDiv.innerText = sqInfo.piece;
                        pDiv.style.transform = `translate(${c * 100}%, ${r * 100}%)`;
                        boardDiv.appendChild(pDiv);
                    }
                }
            }

            setTimeout(() => drawHintArrow(hintFrom, hintTo, files, ranks), 100);
        }

        function handleSquareClick(sqName, sqInfo) {
            if (currentControlMode === 'text') return;
            if (!isGameStarted || currentTurn !== userColor || isAiThinking || (statusInfo && statusInfo.is_over)) return;

            hintMove = null;

            if (selectedSquare === null) {
                if (sqInfo && sqInfo.color === currentTurn) {
                    selectedSquare = sqName;
                    validTargets = legalMoves
                        .filter(m => m.startsWith(sqName))
                        .map(m => m.substring(2, 4));
                    renderBoard();
                }
            } else {
                if (validTargets.includes(sqName)) {
                    let moveUci = selectedSquare + sqName;
                    let piece = boardData[selectedSquare].piece;
                    let isPawn = (piece === '♙' || piece === '♟');
                    let isTargetEndRank = (sqName.endsWith('8') || sqName.endsWith('1'));

                    if (isPawn && isTargetEndRank) {
                        pendingPromotionMove = moveUci;
                        document.getElementById('promotion-modal').style.display = 'flex';
                        selectedSquare = null;
                        validTargets = [];
                        renderBoard();
                        return;
                    }

                    sendUserMove(moveUci);
                    selectedSquare = null;
                    validTargets = [];
                } else if (sqInfo && sqInfo.color === currentTurn) {
                    selectedSquare = sqName;
                    validTargets = legalMoves
                        .filter(m => m.startsWith(sqName))
                        .map(m => m.substring(2, 4));
                    renderBoard();
                } else {
                    selectedSquare = null;
                    validTargets = [];
                    renderBoard();
                }
            }
        }

        async function submitTextMove() {
            let input = document.getElementById('text-move-input');
            let textVal = input.value.trim();
            if (!textVal) return;
            if (!isGameStarted || currentTurn !== userColor || isAiThinking || (statusInfo && statusInfo.is_over)) return;

            let res = await fetch('/move-text', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ text_move: textVal })
            });
            let data = await res.json();
            if (!data.success) {
                alert(data.message);
                return;
            }

            input.value = '';
            syncBoardData(data);
            renderBoard();

            if (currentTurn !== userColor && !statusInfo.is_over) {
                isAiThinking = true;
                renderBoard();
                setTimeout(triggerAiMove, 300);
            }
        }

        function selectPromotion(pieceChar) {
            document.getElementById('promotion-modal').style.display = 'none';
            if (pendingPromotionMove) {
                let finalMove = pendingPromotionMove + pieceChar.toLowerCase();
                pendingPromotionMove = null;
                sendUserMove(finalMove);
            }
        }

        async function sendUserMove(uci) {
            try {
                hintMove = null;
                let res = await fetch('/move', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ uci: uci })
                });
                let data = await res.json();
                syncBoardData(data);
                renderBoard();

                if (currentTurn !== userColor && !statusInfo.is_over) {
                    isAiThinking = true;
                    renderBoard();
                    setTimeout(triggerAiMove, 300);
                }
            } catch (err) {
                isAiThinking = false;
                renderBoard();
            }
        }

        async function triggerAiMove() {
            try {
                let res = await fetch('/ai-move', { method: 'POST' });
                let data = await res.json();
                syncBoardData(data);
            } catch (err) {
                console.error(err);
            } finally {
                isAiThinking = false;
                renderBoard();
            }
        }

        async function copyMainPGN() {
            if (!currentPgn || currentPgn === "Chưa có nước đi") return;
            try {
                await navigator.clipboard.writeText(currentPgn);
                alert("📋 Đã sao chép chuỗi PGN!");
            } catch (err) { console.log(err); }
        }

        async function initGame() {
            await fetchPlaylist();
            let res = await fetch('/init-data');
            let data = await res.json();
            syncBoardData(data);
            renderBoard();
            openMenu();
        }

        window.onresize = () => renderBoard();
        initGame();
    </script>
</body>
</html>
"""


@app.route("/", methods=["GET"])
def index():
       return render_template("index.html")


@app.route("/init-data", methods=["GET"])
def init_data():
    return jsonify({
        "board": get_board_state_dict(),
        "legal_moves": [m.uci() for m in board.legal_moves],
        "turn": "w" if board.turn == chess.WHITE else "b",
        "user_color": "w" if actual_user_color == chess.WHITE else "b",
        "eval": last_evaluation_comment,
        "status": get_game_status(),
        "last_target": last_move_target,
        "last_badge": last_move_badge,
        "pgn": get_pgn_text(),
        "coins": user_coins,
        "has_double": has_double_coins,
        "control_mode": control_mode,
        "captured": get_captured_and_material()
    })


@app.route("/move", methods=["POST"])
def move_piece():
    global board, last_evaluation_comment
    data = request.get_json(silent=True) or {}
    uci_str = data.get("uci", "").strip()

    try:
        move = chess.Move.from_uci(uci_str)
    except Exception:
        return jsonify({"success": False, "message": "Nước đi UCI không hợp lệ!"})

    if move not in board.legal_moves:
        return jsonify({"success": False, "message": "Nước đi không hợp lệ!"})

    moved_piece = board.piece_at(move.from_square)
    moved_piece_type = moved_piece.piece_type if moved_piece else None

    evaluate_move(board, move)
    board.push(move)
    save_board_state_to_history()

    status = get_game_status(moved_piece_type)

    return jsonify({
        "success": True,
        "board": get_board_state_dict(),
        "legal_moves": [m.uci() for m in board.legal_moves],
        "turn": "w" if board.turn == chess.WHITE else "b",
        "user_color": "w" if actual_user_color == chess.WHITE else "b",
        "eval": last_evaluation_comment,
        "status": status,
        "last_target": last_move_target,
        "last_badge": last_move_badge,
        "pgn": get_pgn_text(),
        "coins": user_coins,
        "has_double": has_double_coins,
        "control_mode": control_mode,
        "captured": get_captured_and_material()
    })


@app.route("/ai-move", methods=["POST"])
def ai_move():
    global board, last_evaluation_comment
    if board.is_game_over():
        return jsonify({
            "success": False,
            "board": get_board_state_dict(),
            "legal_moves": [],
            "turn": "w" if board.turn == chess.WHITE else "b",
            "user_color": "w" if actual_user_color == chess.WHITE else "b",
            "eval": last_evaluation_comment,
            "status": get_game_status(),
            "last_target": last_move_target,
            "last_badge": last_move_badge,
            "pgn": get_pgn_text(),
            "coins": user_coins,
            "has_double": has_double_coins,
            "control_mode": control_mode,
            "captured": get_captured_and_material()
        })

    legal_moves = list(board.legal_moves)
    if not legal_moves:
        return jsonify({
            "success": False,
            "board": get_board_state_dict(),
            "legal_moves": [],
            "turn": "w" if board.turn == chess.WHITE else "b",
            "user_color": "w" if actual_user_color == chess.WHITE else "b",
            "eval": last_evaluation_comment,
            "status": get_game_status(),
            "last_target": last_move_target,
            "last_badge": last_move_badge,
            "pgn": get_pgn_text(),
            "coins": user_coins,
            "has_double": has_double_coins,
            "control_mode": control_mode,
            "captured": get_captured_and_material()
        })

    # Đã bớt/nerf chế độ dễ bằng cách tăng tỷ lệ AI chọn nước ngẫu nhiên thay vì chỉ dùng minimax thuần túy
    if ai_difficulty == "easy":
        if random.random() < 0.65:  # 65% tỷ lệ AI chơi ngẫu nhiên ở cấp dễ
            best_move = random.choice(legal_moves)
        else:
            depth = 1
            ai_color = board.turn
            _, best_move = minimax(board, depth, -999999, 999999, True, ai_color)
            if not best_move:
                best_move = random.choice(legal_moves)
    else:
        depth = 1
        if ai_difficulty == "medium":
            depth = 2
        elif ai_difficulty == "hard":
            depth = 3

        ai_color = board.turn
        _, best_move = minimax(board, depth, -999999, 999999, True, ai_color)

        if not best_move:
            best_move = random.choice(legal_moves)

    moved_piece = board.piece_at(best_move.from_square)
    moved_piece_type = moved_piece.piece_type if moved_piece else None

    evaluate_move(board, best_move)
    board.push(best_move)
    save_board_state_to_history()

    status = get_game_status(moved_piece_type)

    return jsonify({
        "success": True,
        "board": get_board_state_dict(),
        "legal_moves": [m.uci() for m in board.legal_moves],
        "turn": "w" if board.turn == chess.WHITE else "b",
        "user_color": "w" if actual_user_color == chess.WHITE else "b",
        "eval": last_evaluation_comment,
        "status": status,
        "last_target": last_move_target,
        "last_badge": last_move_badge,
        "pgn": get_pgn_text(),
        "coins": user_coins,
        "has_double": has_double_coins,
        "control_mode": control_mode,
        "captured": get_captured_and_material()
    })


@app.route("/move-text", methods=["POST"])
def move_text():
    global board, last_evaluation_comment
    data = request.get_json(silent=True) or {}
    text_input = data.get("text_move", "").strip()

    if not text_input:
        return jsonify({"success": False, "message": "Vui lòng nhập nước đi!"})

    parsed_move = None
    try:
        parsed_move = board.parse_san(text_input)
    except Exception:
        pass

    if not parsed_move:
        try:
            parsed_move = chess.Move.from_uci(text_input)
            if parsed_move not in board.legal_moves:
                parsed_move = None
        except Exception:
            parsed_move = None

    if not parsed_move or parsed_move not in board.legal_moves:
        return jsonify({"success": False, "message": f"Nước đi '{text_input}' không hợp lệ hoặc sai định dạng!"})

    moved_piece = board.piece_at(parsed_move.from_square)
    moved_piece_type = moved_piece.piece_type if moved_piece else None

    evaluate_move(board, parsed_move)
    board.push(parsed_move)
    save_board_state_to_history()

    status = get_game_status(moved_piece_type)

    return jsonify({
        "success": True,
        "board": get_board_state_dict(),
        "legal_moves": [m.uci() for m in board.legal_moves],
        "turn": "w" if board.turn == chess.WHITE else "b",
        "user_color": "w" if actual_user_color == chess.WHITE else "b",
        "eval": last_evaluation_comment,
        "status": status,
        "last_target": last_move_target,
        "last_badge": last_move_badge,
        "pgn": get_pgn_text(),
        "coins": user_coins,
        "has_double": has_double_coins,
        "control_mode": control_mode,
        "captured": get_captured_and_material()
    })


@app.route("/get-hint", methods=["POST"])
def get_hint():
    global user_coins
    if user_coins < 1:
        return jsonify({"success": False, "message": "Bạn không đủ 1đ để dùng Gợi ý!"})

    if board.is_game_over() or board.turn != actual_user_color:
        return jsonify({"success": False, "message": "Không phải lượt của bạn!"})

    user_coins -= 1
    legal_moves = list(board.legal_moves)
    if not legal_moves:
        return jsonify({"success": False, "message": "Không có nước đi hợp lệ!"})

    _, best_move = minimax(board, 3, -999999, 999999, True, actual_user_color)
    if not best_move:
        best_move = random.choice(legal_moves)

    return jsonify({
        "success": True,
        "coins": user_coins,
        "hint_move": best_move.uci()
    })


@app.route("/get-replay-states", methods=["GET"])
def get_replay_states():
    enriched_states = []
    for st in board_history_states:
        enriched_states.append({
            "fen": st["fen"],
            "eval": st["eval"],
            "last_target": st["last_target"],
            "last_badge": st["last_badge"],
            "pgn": st["pgn"],
            "board": get_board_state_dict_for_fen(st["fen"])
        })
    return jsonify({
        "success": True,
        "states": enriched_states
    })


@app.route("/apply-replay", methods=["POST"])
def apply_replay():
    global board, last_evaluation_comment, last_move_target, last_move_badge, move_history_san, board_history_states, user_coins
    if user_coins < 2:
        return jsonify({"success": False, "message": "Bạn cần ít nhất 2 điểm để sử dụng tính năng Tua nước đi!"})

    data = request.get_json(silent=True) or {}
    fen = data.get("fen")
    step_index = data.get("step_index")

    if not fen or step_index is None:
        return jsonify({"success": False, "message": "Dữ liệu tua nước đi không hợp lệ!"})

    try:
        user_coins -= 2
        board = chess.Board(fen)
        target_state = board_history_states[step_index]
        
        last_evaluation_comment = target_state["eval"]
        last_move_target = target_state["last_target"]
        last_move_badge = target_state["last_badge"]
        move_history_san = list(target_state["pgn"])

        board_history_states = board_history_states[:step_index + 1]

        return jsonify({
            "success": True,
            "board": get_board_state_dict(),
            "legal_moves": [m.uci() for m in board.legal_moves],
            "turn": "w" if board.turn == chess.WHITE else "b",
            "user_color": "w" if actual_user_color == chess.WHITE else "b",
            "eval": last_evaluation_comment,
            "status": get_game_status(),
            "last_target": last_move_target,
            "last_badge": last_move_badge,
            "pgn": get_pgn_text(),
            "coins": user_coins,
            "has_double": has_double_coins,
            "control_mode": control_mode,
            "captured": get_captured_and_material()
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.route("/get-editor-board", methods=["GET"])
def get_editor_board():
    return jsonify({
        "success": True,
        "board": get_board_state_dict()
    })


@app.route("/get-default-editor-board", methods=["GET"])
def get_default_editor_board():
    default_board = chess.Board()
    squares_data = {}
    for square in chess.SQUARES:
        square_name = chess.square_name(square)
        piece = default_board.piece_at(square)
        squares_data[square_name] = {
            "piece": PIECE_SYMBOLS[piece.symbol()] if piece else "",
            "color": "w" if piece and piece.color == chess.WHITE else ("b" if piece else "")
        }
    return jsonify({
        "success": True,
        "board": squares_data
    })


@app.route("/apply-editor-board", methods=["POST"])
def apply_editor_board():
    global board, last_evaluation_comment
    data = request.get_json(silent=True) or {}
    board_map = data.get("board_map")
    if not board_map:
        return jsonify({"success": False, "message": "Dữ liệu bàn cờ trống!"})

    try:
        new_board = chess.Board("8/8/8/8 w - - 0 1")
        new_board.clear() # Đảm bảo xóa sạch các quân cờ mặc định
        
        # Ánh xạ ngược từ ký tự Unicode sang chữ cái cho thư viện python-chess
        reverse_symbols = {v: k for k, v in PIECE_SYMBOLS.items()}
        
        for sq_name, info in board_map.items():
            if info and info.get("piece"):
                symbol = reverse_symbols.get(info["piece"])
                if symbol:
                    piece = chess.Piece.from_symbol(symbol)
                    sq_index = chess.parse_square(sq_name)
                    new_board.set_piece_at(sq_index, piece)
        
        board = new_board
        last_evaluation_comment = "🛠️ Đã áp dụng bàn cờ tùy chỉnh!"
        
        return jsonify({
            "success": True,
            "board": get_board_state_dict(),
            "legal_moves": [m.uci() for m in board.legal_moves],
            "turn": "w" if board.turn == chess.WHITE else "b",
            "user_color": "w" if actual_user_color == chess.WHITE else "b",
            "eval": last_evaluation_comment,
            "status": get_game_status(),
            "last_target": None,
            "last_badge": "",
            "pgn": "",
            "coins": user_coins,
            "has_double": has_double_coins,
            "control_mode": control_mode,
            "captured": get_captured_and_material()
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Lỗi khi áp dụng bàn cờ: {str(e)}"})


@app.route("/set-settings", methods=["POST"])
def set_settings():
    global user_side_setting, ai_difficulty, control_mode, actual_user_color
    data = request.get_json(silent=True) or {}
    
    if "side_setting" in data:
        user_side_setting = data["side_setting"]
        if user_side_setting == "white":
            actual_user_color = chess.WHITE
        elif user_side_setting == "black":
            actual_user_color = chess.BLACK
        else:
            actual_user_color = random.choice([chess.WHITE, chess.BLACK])
            
    if "difficulty" in data:
        ai_difficulty = data["difficulty"]
        
    if "mode" in data:
        control_mode = data["mode"]
        
    return jsonify({"success": True})


@app.route("/check-save", methods=["GET"])
def check_save():
    return jsonify({"has_save": os.path.exists(SAVE_FILE)})


@app.route("/save-game", methods=["POST"])
def save_game():
    try:
        data = {
            "fen": board.fen(),
            "coins": user_coins,
            "unlocked_themes": unlocked_themes,
            "current_theme": current_theme,
            "has_double_coins": has_double_coins,
            "has_editor_unlocked": has_editor_unlocked,
            "total_wins": total_wins,
            "wins_easy": wins_easy,
            "wins_medium": wins_medium,
            "wins_hard": wins_hard,
            "unlocked_achievements": unlocked_achievements,
            "ai_difficulty": ai_difficulty,
            "user_side_setting": user_side_setting,
            "control_mode": control_mode
        }
        with open(SAVE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.route("/load-game", methods=["POST"])
def load_game():
    global board, user_coins, unlocked_themes, current_theme, has_double_coins, has_editor_unlocked
    global total_wins, wins_easy, wins_medium, wins_hard, unlocked_achievements
    global ai_difficulty, user_side_setting, control_mode, actual_user_color, last_evaluation_comment
    
    if not os.path.exists(SAVE_FILE):
        return jsonify({"success": False, "message": "Không tìm thấy file lưu."})
        
    try:
        with open(SAVE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        board = chess.Board(data.get("fen", chess.STARTING_FEN))
        user_coins = data.get("coins", 0)
        unlocked_themes = data.get("unlocked_themes", ["default"])
        current_theme = data.get("current_theme", "default")
        has_double_coins = data.get("has_double_coins", False)
        has_editor_unlocked = data.get("has_editor_unlocked", False)
        total_wins = data.get("total_wins", 0)
        wins_easy = data.get("wins_easy", 0)
        wins_medium = data.get("wins_medium", 0)
        wins_hard = data.get("wins_hard", 0)
        unlocked_achievements = data.get("unlocked_achievements", [])
        ai_difficulty = data.get("ai_difficulty", "easy")
        user_side_setting = data.get("user_side_setting", "white")
        control_mode = data.get("control_mode", "click")
        
        if user_side_setting == "white":
            actual_user_color = chess.WHITE
        elif user_side_setting == "black":
            actual_user_color = chess.BLACK
        else:
            actual_user_color = random.choice([chess.WHITE, chess.BLACK])
            
        last_evaluation_comment = "📂 Đã tải game thành công!"
        
        return jsonify({
            "success": True,
            "board": get_board_state_dict(),
            "legal_moves": [m.uci() for m in board.legal_moves],
            "turn": "w" if board.turn == chess.WHITE else "b",
            "user_color": "w" if actual_user_color == chess.WHITE else "b",
            "eval": last_evaluation_comment,
            "status": get_game_status(),
            "last_target": None,
            "last_badge": "",
            "pgn": get_pgn_text(),
            "coins": user_coins,
            "has_double": has_double_coins,
            "control_mode": control_mode,
            "captured": get_captured_and_material(),
            "current_theme": current_theme
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.route("/achievements-data", methods=["GET"])
def achievements_data():
    return jsonify({
        "definitions": ACHIEVEMENT_DEFINITIONS,
        "unlocked": unlocked_achievements
    })


@app.route("/shop-data", methods=["GET"])
def shop_data():
    themes = [
        {"id": "default", "name": "Gỗ Cổ Điển", "desc": "Giao diện mặc định", "cost": 0},
        {"id": "classic", "name": "Tối Giản", "desc": "Đen trắng đơn giản", "cost": 10},
        {"id": "red", "name": "Máu Lửa", "desc": "Tông màu đỏ nổi bật", "cost": 20},
        {"id": "neon", "name": "Cyberpunk Neon", "desc": "Đẹp mắt trong bóng tối", "cost": 50}
    ]
    return jsonify({
        "coins": user_coins,
        "has_double": has_double_coins,
        "has_editor": has_editor_unlocked,
        "themes": themes,
        "unlocked": unlocked_themes,
        "current": current_theme
    })


@app.route("/buy-double-coins", methods=["POST"])
def buy_double_coins():
    global user_coins, has_double_coins
    if has_double_coins:
        return jsonify({"success": False, "message": "Bạn đã sở hữu vật phẩm này!"})
    if user_coins < 20:
        return jsonify({"success": False, "message": "Không đủ điểm!"})
        
    user_coins -= 20
    has_double_coins = True
    return jsonify({"success": True})


@app.route("/buy-editor", methods=["POST"])
def buy_editor():
    global user_coins, has_editor_unlocked
    if has_editor_unlocked:
        return jsonify({"success": False, "message": "Bạn đã sở hữu vật phẩm này!"})
    if user_coins < 35:
        return jsonify({"success": False, "message": "Không đủ điểm!"})
        
    user_coins -= 35
    has_editor_unlocked = True
    return jsonify({"success": True})


@app.route("/buy-theme", methods=["POST"])
def buy_theme():
    global user_coins, unlocked_themes, current_theme
    data = request.get_json(silent=True) or {}
    theme_id = data.get("theme_id")
    
    cost_map = {"classic": 10, "red": 20, "neon": 50}
    
    if theme_id in unlocked_themes:
        return jsonify({"success": False, "message": "Đã sở hữu giao diện này!"})
        
    cost = cost_map.get(theme_id, 999)
    if user_coins < cost:
        return jsonify({"success": False, "message": "Không đủ điểm!"})
        
    user_coins -= cost
    unlocked_themes.append(theme_id)
    current_theme = theme_id
    return jsonify({"success": True, "current": current_theme})


@app.route("/use-theme", methods=["POST"])
def use_theme():
    global current_theme
    data = request.get_json(silent=True) or {}
    theme_id = data.get("theme_id")
    if theme_id in unlocked_themes:
        current_theme = theme_id
        return jsonify({"success": True, "current": current_theme})
    return jsonify({"success": False})


@app.route("/clear-all-data", methods=["POST"])
def clear_all_data():
    global user_coins, unlocked_themes, current_theme, has_double_coins, has_editor_unlocked
    global total_wins, wins_easy, wins_medium, wins_hard, unlocked_achievements
    
    user_coins = 0
    unlocked_themes = ["default"]
    current_theme = "default"
    has_double_coins = False
    has_editor_unlocked = False
    total_wins = 0
    wins_easy = 0
    wins_medium = 0
    wins_hard = 0
    unlocked_achievements = []
    
    if os.path.exists(SAVE_FILE):
        os.remove(SAVE_FILE)
        
    return jsonify({"success": True})


@app.route("/clear-achievements", methods=["POST"])
def clear_achievements_route():
    global unlocked_achievements
    unlocked_achievements = []
    return jsonify({"success": True})


@app.route("/reset", methods=["POST"])
def reset_game_route():
    start_new_game()
    return jsonify({
        "board": get_board_state_dict(),
        "legal_moves": [m.uci() for m in board.legal_moves],
        "turn": "w" if board.turn == chess.WHITE else "b",
        "user_color": "w" if actual_user_color == chess.WHITE else "b",
        "eval": last_evaluation_comment,
        "status": get_game_status(),
        "last_target": last_move_target,
        "last_badge": last_move_badge,
        "pgn": get_pgn_text(),
        "coins": user_coins,
        "has_double": has_double_coins,
        "control_mode": control_mode,
        "captured": get_captured_and_material()
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

