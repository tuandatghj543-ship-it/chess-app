from datetime import datetime
import json
import io
import os
import random
import chess
import chess.pgn
from flask import Flask, Response, jsonify, render_template, request, send_from_directory

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAVE_FILE = os.path.join(BASE_DIR, "save_game.json")

# Danh sách các đường dẫn bộ nhớ máy có thể chứa thư mục Music
POSSIBLE_MUSIC_FOLDERS = [
    "/storage/emulated/Music",
]


def get_valid_music_folder():
    """Tự động quét và lấy đúng đường dẫn thư mục nhạc đang tồn tại trên thiết bị."""
    for folder_path in POSSIBLE_MUSIC_FOLDERS:
        if os.path.isdir(folder_path):
            return folder_path
    return None


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
custom_board_active = False

# Thống kê & Thành tựu & Lịch sử ván đấu
total_wins = 0
wins_easy = 0
wins_medium = 0
wins_hard = 0
unlocked_achievements = []

board_history_states = []
completed_games_history = []  # Lưu các ván đã kết thúc để phân tích

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
    return san_str


def get_playlist_files():
    folder = get_valid_music_folder()
    if not folder:
        return []
    files = [f for f in os.listdir(folder) if f.lower().endswith(('.mp3', '.wav', '.m4a', '.ogg'))]
    files.sort()
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
    global board, last_evaluation_comment, actual_user_color, last_move_target, last_move_badge, move_history_san, reward_claimed, board_history_states, custom_board_active
    board = chess.Board()
    custom_board_active = False
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
    return bool(custom_board_active)


def save_game_to_history_list(result_str):
    global completed_games_history
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
    
    now_str = datetime.now().strftime("%H:%M:%S (%d/%m/%Y)")
    game_record = {
        "id": len(completed_games_history) + 1,
        "title": f"Player vs AI ({ai_difficulty})",
        "time": now_str,
        "result": result_str,
        "states": enriched_states
    }
    completed_games_history.append(game_record)


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
        game_res_title = "Player win" if winner_color == actual_user_color else "AI win"
    else:
        result = "draw"
        game_res_title = "Hòa"

    save_game_to_history_list(game_res_title)

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


def describe_move_reason(board_before, board_after, move, uci_str, sacrifice=False):
    piece_names = {
        chess.PAWN: "Tốt", chess.KNIGHT: "Mã", chess.BISHOP: "Tượng",
        chess.ROOK: "Xe", chess.QUEEN: "Hậu", chess.KING: "Vua",
    }

    piece = board_before.piece_at(move.from_square)
    piece_name = piece_names.get(piece.piece_type, "Quân") if piece else "Quân"
    captured = board_before.piece_at(move.to_square)
    is_capture = board_before.is_capture(move)
    is_check = board_after.is_check()
    is_mate = board_after.is_checkmate()
    is_promotion = move.promotion is not None

    if is_mate:
        return f"{piece_name} {uci_str}: chiếu hết — Vua đối phương không còn đường thoát."

    if is_promotion:
        promoted_name = piece_names.get(move.promotion, "quân")
        if is_check:
            return f"Phong cấp thành {promoted_name} và đồng thời chiếu Vua — nước đi forcing."
        return f"Phong cấp thành {promoted_name} để tăng sức mạnh quân cờ."

    if sacrifice:
        if is_check:
            return f"Thí {piece_name} để chiếu Vua và tạo áp lực ngay lập tức."
        if is_capture:
            target_name = piece_names.get(captured.piece_type, "quân") if captured else "quân"
            return f"Thí {piece_name} để ăn {target_name}, đổi vật chất lấy thế chủ động."
        return f"Thí {piece_name} có tính toán, chấp nhận mất quân để đổi lấy thế chủ động."

    if is_check and is_capture:
        target_name = piece_names.get(captured.piece_type, "quân") if captured else "quân"
        return f"{piece_name} ăn {target_name} và chiếu Vua — một nước forcing."

    if is_check:
        return f"{piece_name} chiếu Vua, buộc đối phương phải xử lý mối đe dọa này."

    if is_capture:
        target_name = piece_names.get(captured.piece_type, "quân") if captured else "quân"
        return f"{piece_name} ăn {target_name} tại {uci_str[2:4]}."

    return f"{piece_name} di chuyển từ {uci_str[:2]} đến {uci_str[2:4]}, tiếp tục thế trận."


def evaluate_move(board_before, move):
    global last_evaluation_comment, last_move_target, last_move_badge
    uci_str = move.uci()
    last_move_target = uci_str[2:4]

    try:
        raw_san = board_before.san(move)
        formatted_san = format_custom_san(raw_san)
        move_history_san.append(formatted_san)
    except Exception:
        move_history_san.append(uci_str.lower())

    mover_color = board_before.turn
    score_before = evaluate_board_score(board_before, mover_color)

    board_after = board_before.copy()
    board_after.push(move)
    score_after = evaluate_board_score(board_after, mover_color)

    try:
        best_score, _ = minimax(board_before.copy(), 2, -999999, 999999, True, mover_color)
    except Exception:
        best_score = score_before

    try:
        opponent_reply_score, _ = minimax(
            board_after.copy(), 1, -999999, 999999, False, mover_color
        )
    except Exception:
        opponent_reply_score = score_after

    best_gap = max(0, best_score - opponent_reply_score)
    drop_in_score = score_before - opponent_reply_score

    is_check = board_after.is_check()
    is_capture = board_before.is_capture(move)
    moved_piece = board_before.piece_at(move.from_square)
    moved_piece_value = PIECE_VALUES_AI.get(moved_piece.piece_type, 0) if moved_piece else 0

    opponent_has_mate_in_one = False
    if not board_after.is_game_over():
        for reply in list(board_after.legal_moves):
            test_board = board_after.copy()
            test_board.push(reply)
            if test_board.is_checkmate():
                opponent_has_mate_in_one = True
                break

    opponent_can_take_moved_piece = False
    if moved_piece and not board_after.is_game_over():
        for reply in board_after.legal_moves:
            if reply.to_square == move.to_square and board_after.is_capture(reply):
                opponent_can_take_moved_piece = True
                break

    is_sacrifice_candidate = (
        moved_piece_value >= PIECE_VALUES_AI.get(chess.KNIGHT, 30)
        and opponent_can_take_moved_piece
    )

    is_brilliant = (
        best_gap <= 5
        and drop_in_score <= 5
        and (is_sacrifice_candidate or (is_check and is_capture))
    )

    if board_after.is_checkmate():
        last_evaluation_comment = f"🏆 CHIẾU HẾT! ({uci_str})"
        last_move_badge = "🏆"
    elif opponent_has_mate_in_one:
        last_evaluation_comment = f"?? Bạn đã cho đối thủ có cơ hội cho vua bạn ăn đạn ☠️ ({uci_str})"
        last_move_badge = "??"
    elif best_gap >= 80 or (is_sacrifice_candidate and best_gap >= 55):
        if opponent_can_take_moved_piece:
            last_evaluation_comment = f"?? Quân free — bạn đã cho đối thủ ăn quân quá dễ ({uci_str})"
        else:
            last_evaluation_comment = f"?? Nước đi này làm mất quân quá dễ ({uci_str})"
        last_move_badge = "??"
    elif best_gap >= 30:
        last_evaluation_comment = f"? Nước đi sai lầm ({uci_str})"
        last_move_badge = "?"
    elif uci_str in BOOK_MOVES and board_before.fullmove_number <= 4:
        last_evaluation_comment = f"📖 Khai cuộc ({uci_str})"
        last_move_badge = "📖"
    elif is_brilliant:
        last_evaluation_comment = f"!! Thiên tài — {describe_move_reason(board_before, board_after, move, uci_str, sacrifice=is_sacrifice_candidate)}"
        last_move_badge = "!!"
    elif is_sacrifice_candidate:
        last_evaluation_comment = f"! {describe_move_reason(board_before, board_after, move, uci_str, sacrifice=True)}"
        last_move_badge = "!"
    elif is_check and is_capture:
        last_evaluation_comment = f"! {describe_move_reason(board_before, board_after, move, uci_str)}"
        last_move_badge = "!"
    elif is_check:
        last_evaluation_comment = f"! {describe_move_reason(board_before, board_after, move, uci_str)}"
        last_move_badge = "!"
    elif is_capture:
        last_evaluation_comment = f"⭐ {describe_move_reason(board_before, board_after, move, uci_str)}"
        last_move_badge = "⭐"
    else:
        last_evaluation_comment = f"✔ {describe_move_reason(board_before, board_after, move, uci_str)}"
        last_move_badge = "✔"


@app.route("/get-playlist", methods=["GET"])
def get_playlist():
    files = get_playlist_files()
    return jsonify({"playlist": files})


@app.route("/play-music/<path:filename>", methods=["GET"])
def play_music(filename):
    folder = get_valid_music_folder()
    if not folder:
        return "Không tìm thấy thư mục Music!", 404
    song_path = os.path.join(folder, filename)
    if not os.path.exists(song_path):
        return "Không tìm thấy file nhạc!", 404

    return send_from_directory(folder, filename)








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

    if board.is_game_over():
        return jsonify({"success": False, "message": "Ván cờ đã kết thúc!"})
    if board.turn != actual_user_color:
        return jsonify({"success": False, "message": "Chưa tới lượt của bạn!"})

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

    if board.turn == actual_user_color:
        return jsonify({
            "success": False,
            "message": "Chưa tới lượt AI!",
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

    if ai_difficulty == "easy":
        if random.random() < 0.65:
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
    if board.is_game_over():
        return jsonify({"success": False, "message": "Ván cờ đã kết thúc!"})
    if board.turn != actual_user_color:
        return jsonify({"success": False, "message": "Chưa tới lượt của bạn!"})

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


@app.route("/get-history-list", methods=["GET"])
def get_history_list():
    summary_list = []
    for g in completed_games_history:
        summary_list.append({
            "id": g["id"],
            "title": g["title"],
            "time": g["time"],
            "result": g["result"]
        })
    return jsonify({"success": True, "games": summary_list})


@app.route("/get-history-detail/<int:game_id>", methods=["GET"])
def get_history_detail(game_id):
    for g in completed_games_history:
        if g["id"] == game_id:
            return jsonify({"success": True, "states": g["states"]})
    return jsonify({"success": False, "message": "Không tìm thấy ván đấu!"})


@app.route("/parse-pgn", methods=["POST"])
def parse_pgn():
    global last_evaluation_comment, last_move_target, last_move_badge
    data = request.get_json(silent=True) or {}
    pgn_str = data.get("pgn", "").strip()

    if not pgn_str:
        return jsonify({"success": False, "message": "PGN đã lỗi hoặc sai hoàn toàn"})

    try:
        pgn_io = io.StringIO(pgn_str)
        parsed_game = chess.pgn.read_game(pgn_io)
        if not parsed_game:
            return jsonify({"success": False, "message": "PGN đã lỗi hoặc sai hoàn toàn"})

        temp_board = parsed_game.board()
        states = []

        states.append({
            "fen": temp_board.fen(),
            "eval": "Bắt đầu ván đấu từ PGN!",
            "last_target": last_move_target,
            "last_badge": last_move_badge,
            "pgn": [],
            "board": get_board_state_dict_for_fen(temp_board.fen())
        })

        moves_history_san = []
        for move in parsed_game.mainline_moves():
            if move not in temp_board.legal_moves:
                return jsonify({"success": False, "message": "PGN đã lỗi hoặc sai hoàn toàn"})

            uci_str = move.uci()
            try:
                raw_san = temp_board.san(move)
                formatted_san = format_custom_san(raw_san)
                moves_history_san.append(formatted_san)
            except Exception:
                moves_history_san.append(uci_str.lower())

            saved_comment = last_evaluation_comment
            saved_target = last_move_target
            saved_badge = last_move_badge
            saved_history_len = len(move_history_san)
            evaluate_move(temp_board, move)
            comment = last_evaluation_comment
            badge = last_move_badge
            del move_history_san[saved_history_len:]
            last_evaluation_comment = saved_comment
            last_move_target = saved_target
            last_move_badge = saved_badge

            temp_board.push(move)

            states.append({
                "fen": temp_board.fen(),
                "eval": comment,
                "last_target": uci_str[2:4],
                "last_badge": badge,
                "pgn": list(moves_history_san),
                "board": get_board_state_dict_for_fen(temp_board.fen())
            })

        return jsonify({"success": True, "states": states})
    except Exception:
        return jsonify({"success": False, "message": "PGN đã lỗi hoặc sai hoàn toàn"})


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
    step_index = data.get("step_index")

    if step_index is None:
        return jsonify({"success": False, "message": "Dữ liệu tua nước đi không hợp lệ!"})

    try:
        step_index = int(step_index)
        if step_index < 0 or step_index >= len(board_history_states):
            return jsonify({"success": False, "message": "Mốc tua nước đi không tồn tại!"})

        target_state = board_history_states[step_index]
        board = chess.Board(target_state["fen"])
        user_coins -= 2
        
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
    global board, last_evaluation_comment, last_move_target, last_move_badge, move_history_san, board_history_states, reward_claimed, custom_board_active
    data = request.get_json(silent=True) or {}
    board_map = data.get("board_map")
    if not board_map:
        return jsonify({"success": False, "message": "Dữ liệu bàn cờ trống!"})

    try:
        new_board = chess.Board("8/8/8/8/8/8/8/8 w - - 0 1")
        new_board.clear()
        
        reverse_symbols = {v: k for k, v in PIECE_SYMBOLS.items()}
        
        for sq_name, info in board_map.items():
            if info and info.get("piece"):
                symbol = reverse_symbols.get(info["piece"])
                if symbol:
                    piece = chess.Piece.from_symbol(symbol)
                    sq_index = chess.parse_square(sq_name)
                    new_board.set_piece_at(sq_index, piece)
        
        if len(new_board.pieces(chess.KING, chess.WHITE)) != 1 or len(new_board.pieces(chess.KING, chess.BLACK)) != 1:
            return jsonify({"success": False, "message": "Bàn cờ phải có đúng 1 Vua Trắng và 1 Vua Đen!"})
        if not new_board.is_valid():
            return jsonify({"success": False, "message": "Vị trí quân cờ không hợp lệ!"})

        board = new_board
        custom_board_active = True
        last_evaluation_comment = "🛠️ Đã áp dụng bàn cờ tùy chỉnh!"
        last_move_target = None
        last_move_badge = ""
        move_history_san = []
        board_history_states = []
        reward_claimed = False
        save_board_state_to_history()
        
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
        new_side = data["side_setting"]
        if new_side not in {"white", "black", "random"}:
            return jsonify({"success": False, "message": "side_setting không hợp lệ"}), 400
        user_side_setting = new_side
        if user_side_setting == "white":
            actual_user_color = chess.WHITE
        elif user_side_setting == "black":
            actual_user_color = chess.BLACK
        else:
            actual_user_color = random.choice([chess.WHITE, chess.BLACK])
            
    if "difficulty" in data:
        new_difficulty = data["difficulty"]
        if new_difficulty not in {"easy", "medium", "hard"}:
            return jsonify({"success": False, "message": "difficulty không hợp lệ"}), 400
        ai_difficulty = new_difficulty
        
    if "mode" in data:
        new_mode = data["mode"]
        if new_mode not in {"click", "text"}:
            return jsonify({"success": False, "message": "mode không hợp lệ"}), 400
        control_mode = new_mode
        
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
            "control_mode": control_mode,
            "completed_games_history": completed_games_history,
            "move_history_san": move_history_san,
            "board_history_states": board_history_states,
            "last_evaluation_comment": last_evaluation_comment,
            "last_move_target": last_move_target,
            "last_move_badge": last_move_badge,
            "reward_claimed": reward_claimed,
            "actual_user_color": "w" if actual_user_color == chess.WHITE else "b",
            "custom_board_active": custom_board_active
        }
        temp_file = SAVE_FILE + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        os.replace(temp_file, SAVE_FILE)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.route("/load-game", methods=["POST"])
def load_game():
    global board, user_coins, unlocked_themes, current_theme, has_double_coins, has_editor_unlocked
    global total_wins, wins_easy, wins_medium, wins_hard, unlocked_achievements, completed_games_history
    global ai_difficulty, user_side_setting, control_mode, actual_user_color, last_evaluation_comment
    global move_history_san, board_history_states, last_move_target, last_move_badge, reward_claimed, custom_board_active
    
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
        completed_games_history = data.get("completed_games_history", [])
        ai_difficulty = data.get("ai_difficulty", "easy")
        user_side_setting = data.get("user_side_setting", "white")
        control_mode = data.get("control_mode", "click")
        move_history_san = data.get("move_history_san", [])
        board_history_states = data.get("board_history_states", [])
        last_move_target = data.get("last_move_target")
        last_move_badge = data.get("last_move_badge", "")
        reward_claimed = data.get("reward_claimed", False)
        custom_board_active = data.get("custom_board_active", False)

        if not board_history_states:
            save_board_state_to_history()
        
        saved_color = data.get("actual_user_color")
        if saved_color == "w":
            actual_user_color = chess.WHITE
        elif saved_color == "b":
            actual_user_color = chess.BLACK
        elif user_side_setting == "white":
            actual_user_color = chess.WHITE
        elif user_side_setting == "black":
            actual_user_color = chess.BLACK
        else:
            actual_user_color = random.choice([chess.WHITE, chess.BLACK])
            
        last_evaluation_comment = data.get("last_evaluation_comment", "📂 Đã tải game thành công!")
        
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
        
    if theme_id not in cost_map:
        return jsonify({"success": False, "message": "Giao diện không tồn tại!"})

    cost = cost_map[theme_id]
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
    global total_wins, wins_easy, wins_medium, wins_hard, unlocked_achievements, completed_games_history
    
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
    completed_games_history = []
    
    if os.path.exists(SAVE_FILE):
        os.remove(SAVE_FILE)

    start_new_game()
    return jsonify({"success": True})


@app.route("/clear-achievements", methods=["POST"])
def clear_achievements_route():
    global unlocked_achievements
    unlocked_achievements = []
    try:
        if os.path.exists(SAVE_FILE):
            with open(SAVE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["unlocked_achievements"] = []
            temp_file = SAVE_FILE + ".tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            os.replace(temp_file, SAVE_FILE)
    except Exception as e:
        return jsonify({"success": False, "message": f"Không thể cập nhật file lưu: {e}"}), 500
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
    app.run(host="0.0.0.0", port=5000, debug=False)
