"""
Web UI - Flask + SocketIO 实时通信

前端 Phaser 游戏通过 WebSocket 获取实时状态
"""
import os
import sys
import threading
import json
import urllib.error
import urllib.request

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from flask import Flask, render_template, request, jsonify, send_from_directory, make_response
from flask_socketio import SocketIO, emit
from openai import OpenAI
from game_engine import WerewolfGameEngine
from config_loader import load_config

app = Flask(__name__,
            static_folder=os.path.join(PROJECT_ROOT, "static"),
            template_folder=os.path.join(PROJECT_ROOT, "ui", "templates"))
app.config["SECRET_KEY"] = "werewolf-ville-secret"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

game = None


CONFIG = load_config()

LLM_PROVIDER_BASE_URLS = {
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
}


def _runtime_llm_override_from_data(data):
    provider = str(data.get("provider", "chat2api") or "chat2api").strip().lower()
    if provider in ("", "chat2api"):
        return None
    if provider not in {"openrouter", "openai", "deepseek", "anthropic", "custom", "custom_anthropic"}:
        return {"error": f"Unsupported LLM provider: {provider}"}

    api_key = str(data.get("api_key", "") or "").strip()
    model = str(data.get("model", "") or "").strip()
    api_base = str(data.get("api_base", "") or "").strip()
    if provider not in {"custom", "custom_anthropic"}:
        api_base = LLM_PROVIDER_BASE_URLS[provider]

    missing = []
    if not api_key:
        missing.append("API key")
    if not model:
        missing.append("model")
    if not api_base:
        missing.append("API base URL")
    if missing:
        return {"error": f"{provider} requires: {', '.join(missing)}."}

    return {
        "provider": provider,
        "api_key": api_key,
        "model": model,
        "api_base": api_base,
    }


def _runtime_llm_override_from_request():
    return _runtime_llm_override_from_data(request.get_json(silent=True) or {})


def _classify_llm_test_error(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}".lower()
    if "402" in text or "insufficient_balance" in text or "insufficient account balance" in text:
        return "insufficient_balance"
    if "429" in text or "rate limit" in text or "rate-limited" in text or "ratelimit" in text:
        return "rate_limited"
    if "401" in text or "403" in text or "unauthorized" in text or "forbidden" in text or "invalid api key" in text:
        return "auth_failed"
    if "404" in text or "not found" in text or "model_not_found" in text:
        return "not_found"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "connection" in text or "urlerror" in text or "502" in text or "503" in text or "504" in text:
        return "network_error"
    return "unknown_error"


def _friendly_llm_test_error(reason: str, provider: str, model: str, raw: str) -> str:
    if reason == "insufficient_balance":
        return (
            f"{provider} / {model} API 余额不足，当前 Key 无法继续调用。"
            "请充值、换一个有余额的 API Key，或切换到其他供应商/模型。"
        )
    if reason == "rate_limited":
        return (
            f"{provider} / {model} 可达，但当前模型或上游供应商限流。"
            "可以稍后重试、换非 free 模型，或在供应商侧配置自己的 BYOK/API key。"
        )
    if reason == "auth_failed":
        return "API Key 无效、权限不足，或该 key 没有访问该模型的权限。"
    if reason == "not_found":
        return "模型名不存在，或当前供应商不支持这个模型名。"
    if reason == "timeout":
        return "API 请求超时，请检查网络、Base URL 或供应商状态。"
    if reason == "network_error":
        return "无法连接到 API 服务，请检查 Base URL、网络或供应商状态。"
    return raw


def _test_anthropic_messages(llm_override):
    payload = {
        "model": llm_override["model"],
        "max_tokens": 8,
        "temperature": 0,
        "messages": [{"role": "user", "content": "Reply with OK."}],
    }
    req = urllib.request.Request(
        llm_override["api_base"].rstrip("/") + "/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": llm_override["api_key"],
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"Anthropic HTTP {e.code}: {body}") from e

    parts = []
    for block in data.get("content", []):
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts).strip()


@app.route("/")
def index():
    response = make_response(render_template("index.html"))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/api/status", methods=["GET"])
def get_status():
    if game is None:
        return jsonify({"error": "game not started"})
    return jsonify(game.get_status())


@app.route("/api/test_llm_provider", methods=["POST"])
def test_llm_provider():
    llm_override = _runtime_llm_override_from_request()
    if isinstance(llm_override, dict) and llm_override.get("error"):
        return jsonify({"ok": False, "error": llm_override["error"]}), 400
    if llm_override is None:
        return jsonify({"ok": True, "provider": "chat2api", "message": "Using local Chat2API config."})

    provider = llm_override["provider"]
    model = llm_override["model"]
    api_base = llm_override["api_base"]
    try:
        if provider in ("anthropic", "custom_anthropic"):
            sample = _test_anthropic_messages(llm_override)
        else:
            client = OpenAI(
                api_key=llm_override["api_key"],
                base_url=api_base,
                default_headers={
                    "HTTP-Referer": "http://127.0.0.1:5000",
                    "X-Title": "Werewolf Ville",
                },
            )
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a connectivity test."},
                    {"role": "user", "content": "Reply with OK."},
                ],
                max_tokens=8,
                temperature=0,
                timeout=20,
            )
            sample = (response.choices[0].message.content or "").strip()
        return jsonify({
            "ok": True,
            "provider": provider,
            "model": model,
            "api_base": api_base,
            "sample": sample[:80],
        })
    except Exception as e:
        reason = _classify_llm_test_error(e)
        raw_error = f"{type(e).__name__}: {e}"
        return jsonify({
            "ok": False,
            "provider": provider,
            "model": model,
            "api_base": api_base,
            "reason": reason,
            "error": _friendly_llm_test_error(reason, provider, model, raw_error),
            "raw_error": raw_error,
        }), 400


@app.route("/api/start", methods=["POST"])
def start_game():
    global game
    llm_override = _runtime_llm_override_from_request()
    if isinstance(llm_override, dict) and llm_override.get("error"):
        return jsonify(llm_override), 400
    if game is not None:
        game.set_socketio(None)
        game.stop()
    game = WerewolfGameEngine(llm_override=llm_override)
    game.set_socketio(socketio)
    game.start()
    return jsonify({
        "message": "game started",
        "werewolf_name": game.werewolf_name,
        "werewolf_names": game.werewolf_names,
        "model_assignments": game.model_assignments
    })


@app.route("/api/start_dusk_discussion", methods=["POST"])
def start_dusk_discussion():
    if game is None:
        return jsonify({"error": "game not started"})
    ok = game.start_dusk_discussion()
    return jsonify({"message": "dusk discussion started" if ok else "cannot start dusk discussion"})


@app.route("/api/submit_dusk_statement", methods=["POST"])
def submit_dusk_statement():
    if game is None:
        return jsonify({"error": "game not started"})
    data = request.get_json(silent=True) or {}
    result = game.submit_dusk_statement(data.get("statement", ""))
    return jsonify(result)


@app.route("/api/enter_night", methods=["POST"])
def enter_night():
    if game is None:
        return jsonify({"error": "game not started"})
    game.enter_night()
    return jsonify({"message": "entering night"})


@app.route("/api/move_detective", methods=["POST"])
def move_detective():
    if game is None:
        return jsonify({"error": "game not started"})
    data = request.json
    game.move_detective_to(
        data.get("x", 0),
        data.get("y", 0),
        data.get("location", ""),
    )
    return jsonify({"message": "detective moving"})


@app.route("/api/detective_chat", methods=["POST"])
def detective_chat():
    if game is None:
        return jsonify({"error": "game not started"})
    data = request.json
    result = game.detective_chat(
        data.get("target_name", ""),
        data.get("message", ""),
        data.get("is_deep_dive", False),
    )
    return jsonify(result)


@app.route("/api/detective_announce", methods=["POST"])
def detective_announce():
    if game is None:
        return jsonify({"error": "game not started"})
    data = request.json
    result = game.detective_announce(data.get("werewolf_guess", ""))
    return jsonify(result)


@app.route("/api/jail_vote_target", methods=["POST"])
def jail_vote_target():
    if game is None:
        return jsonify({"error": "game not started"})
    data = request.json
    result = game.jail_vote_target(data.get("target_name", ""))
    return jsonify(result)


@app.route("/api/acquire_silver_bullet", methods=["POST"])
def acquire_silver_bullet():
    if game is None:
        return jsonify({"error": "game not started"})
    result = game.acquire_silver_bullet()
    return jsonify(result)


@app.route("/api/acquire_silver_jewelry", methods=["POST"])
def acquire_silver_jewelry():
    if game is None:
        return jsonify({"error": "game not started"})
    data = request.json
    result = game.acquire_silver_jewelry(data.get("target_name", None))
    return jsonify(result)


@app.route("/api/craft_silver_bullet", methods=["POST"])
def craft_silver_bullet():
    if game is None:
        return jsonify({"error": "game not started"})
    result = game.craft_silver_bullet()
    return jsonify(result)


@app.route("/api/shoot_silver_bullet", methods=["POST"])
def shoot_silver_bullet():
    if game is None:
        return jsonify({"error": "game not started"})
    data = request.json or {}
    result = game.shoot_silver_bullet(data.get("target_name", ""))
    return jsonify(result)


@app.route("/api/use_silver_knife", methods=["POST"])
def use_silver_knife():
    if game is None:
        return jsonify({"error": "game not started"})
    data = request.json or {}
    result = game.use_silver_knife(data.get("holder_name", ""), data.get("target_name", ""))
    return jsonify(result)


@app.route("/api/agent/<name>", methods=["GET"])
def get_agent_info(name):
    if game is None:
        return jsonify({"error": "game not started"})

    agent_name = name.replace("_", " ")
    if agent_name not in game.agents:
        return jsonify({"error": f"agent {agent_name} not found"})

    agent = game.agents[agent_name]
    return jsonify({
        "name": agent.name,
        "role": agent.role,
        "is_alive": agent.is_alive,
        "x": agent.x,
        "y": agent.y,
        "action": agent.current_action,
        "location": agent.current_location,
        "soul": agent.read_soul(),
        "agent_state": agent.read_agent(),
        "memory": agent.read_memory(),
        "cognition": agent.read_cognition(),
        "dialogue_history": getattr(agent, "dialogue_history", []),
        "notebook": agent.read_notebook() if agent.role == "detective" else None,
    })


@app.route("/api/reset", methods=["POST"])
def reset_game():
    global game
    llm_override = _runtime_llm_override_from_request()
    if isinstance(llm_override, dict) and llm_override.get("error"):
        return jsonify(llm_override), 400
    if game is not None:
        game.set_socketio(None)
        game.stop()
    game = WerewolfGameEngine(llm_override=llm_override)
    game.set_socketio(socketio)
    game.start()
    return jsonify({
        "message": "game reset",
        "werewolf_name": game.werewolf_name,
        "werewolf_names": game.werewolf_names,
        "model_assignments": game.model_assignments
    })


@app.route("/api/collision_maze", methods=["GET"])
def get_collision_maze():
    """返回碰撞迷宫数据（0=可通行, 1=碰撞）"""
    if game is None or game.collision_maze is None:
        return jsonify({"error": "maze not available"})
    return jsonify({"maze": game.collision_maze, "width": len(game.collision_maze[0]) if game.collision_maze else 0, "height": len(game.collision_maze)})


# ==================== WebSocket ====================

@socketio.on("connect")
def on_connect():
    print("Client connected")
    if game:
        emit("game_state", game.get_status())


@socketio.on("disconnect")
def on_disconnect():
    print("Client disconnected")


@socketio.on("request_state")
def on_request_state():
    if game:
        emit("game_state", game.get_status())


@socketio.on("move_detective")
def on_move_detective(data):
    if game:
        game.move_detective_to(
            data.get("x", 0),
            data.get("y", 0),
            data.get("location", ""),
        )


@socketio.on("move_detective_to_agent")
def on_move_detective_to_agent(data):
    if game:
        game.move_detective_to_agent(data.get("target_name", ""))


@socketio.on("stop_detective_chat")
def on_stop_detective_chat():
    if game:
        game.detective_conversation_partner = None



@socketio.on("detective_chat")
def on_detective_chat(data):
    if game is None:
        emit("chat_response", {"error": "game not started"})
        return

    target_name = data.get("target_name", "")
    message = data.get("message", "")
    is_deep_dive = data.get("is_deep_dive", False)
    sid = request.sid

    def _do_chat():
        try:
            result = game.detective_chat(target_name, message, is_deep_dive)
            result["target_name"] = target_name
            result["detective_message"] = message
            socketio.emit("chat_response", result, room=sid)
        except Exception as e:
            socketio.emit("chat_response", {"error": str(e)}, room=sid)

    # 在子线程中执行 LLM 调用，避免阻塞 Flask-SocketIO 主线程
    threading.Thread(target=_do_chat, daemon=True).start()


@socketio.on("start_dusk_discussion")
def on_start_dusk_discussion():
    if game:
        game.start_dusk_discussion()


@socketio.on("submit_dusk_statement")
def on_submit_dusk_statement(data):
    if game:
        result = game.submit_dusk_statement(data.get("statement", ""))
        emit("dusk_statement_result", result)


@socketio.on("enter_night")
def on_enter_night():
    if game:
        game.enter_night()


@socketio.on("jail_vote_target")
def on_jail_vote_target(data):
    if game:
        result = game.jail_vote_target(data.get("target_name", ""))
        emit("jail_result", result)


@socketio.on("acquire_silver_bullet")
def on_acquire_silver_bullet():
    if game:
        result = game.acquire_silver_bullet()
        emit("silver_result", result)


@socketio.on("acquire_silver_jewelry")
def on_acquire_silver_jewelry(data):
    if game:
        result = game.acquire_silver_jewelry(data.get("target_name", None))
        emit("silver_result", result)


@socketio.on("craft_silver_bullet")
def on_craft_silver_bullet():
    if game:
        result = game.craft_silver_bullet()
        emit("silver_result", result)


@socketio.on("shoot_silver_bullet")
def on_shoot_silver_bullet(data):
    if game:
        result = game.shoot_silver_bullet(data.get("target_name", ""))
        emit("silver_result", result)


@socketio.on("use_silver_knife")
def on_use_silver_knife(data):
    if game:
        result = game.use_silver_knife(data.get("holder_name", ""), data.get("target_name", ""))
        emit("silver_result", result)


@socketio.on("detective_announce")
def on_announce(data):
    if game:
        result = game.detective_announce(data.get("werewolf_guess", ""))
        emit("announce_result", result)


OBJECT_TRANSLATIONS = {
    "bar customer seating": "酒吧顾客座椅",
    "bathroom sink": "洗手池",
    "bed": "舒适大床",
    "behind the bar counter": "酒吧柜台内侧",
    "behind the cafe counter": "咖啡馆前台内侧",
    "behind the grocery counter": "杂货店收银台内侧",
    "behind the pharmacy counter": "药房柜台内侧",
    "behind the supply store counter": "五金店收银台内侧",
    "blackboard": "学术黑板",
    "bookshelf": "藏书架",
    "cafe customer seating": "咖啡馆雅座",
    "classroom podium": "教师讲台",
    "classroom student seating": "学生课桌椅",
    "closet": "衣柜",
    "common room sofa": "休息室沙发",
    "common room table": "休息室桌子",
    "computer": "现代计算机",
    "computer desk": "电脑桌",
    "cooking area": "烹饪料理台",
    "desk": "写字桌",
    "dorm garden": "宿舍小花园",
    "easel": "画架",
    "game console": "游戏主机",
    "garden chair": "花园靠椅",
    "grocery store counter": "杂货铺收银台",
    "grocery store shelf": "商品货架",
    "guitar": "民谣吉他",
    "harp": "典雅竖琴",
    "house garden": "庭院花园",
    "kitchen sink": "厨房洗涤水池",
    "library sofa": "图书馆沙发",
    "library table": "自习长桌",
    "lifting weight": "健身器械",
    "microphone": "演唱麦克风",
    "park garden": "公园花坛",
    "pharmacy store counter": "药房柜台",
    "pharmacy store shelf": "药剂陈列架",
    "piano": "古典钢琴",
    "pool table": "台球桌",
    "refrigerator": "冰箱",
    "shelf": "储物架",
    "shower": "淋浴间",
    "supply store counter": "五金店服务柜台",
    "supply store product shelf": "工具陈列架",
    "toaster": "烤面包机",
    "toilet": "卫生间马桶"
}

@app.route("/api/objects", methods=["GET"])
def get_interactive_objects():
    from game_engine import load_scene_data
    try:
        if game is not None and getattr(game, 'go_maze', None) is not None:
            go_maze = game.go_maze
            go_dict = game.go_dict
        else:
            scene_data = load_scene_data()
            go_maze = scene_data[2]
            go_dict = scene_data[5]
            
        height = len(go_maze)
        width = len(go_maze[0]) if height > 0 else 0
        visited = set()
        clusters = []
        
        for y in range(height):
            for x in range(width):
                val = go_maze[y][x]
                if val in go_dict and (x, y) not in visited:
                    name = go_dict[val]
                    queue = [(x, y)]
                    visited.add((x, y))
                    comp = []
                    head = 0
                    while head < len(queue):
                        cx, cy = queue[head]
                        head += 1
                        comp.append((cx, cy))
                        for dx, dy in [(1,0), (-1,0), (0,1), (0,-1)]:
                            nx, ny = cx + dx, cy + dy
                            if 0 <= nx < width and 0 <= ny < height:
                                if (nx, ny) not in visited and go_maze[ny][nx] == val:
                                    visited.add((nx, ny))
                                    queue.append((nx, ny))
                    
                    sum_x = sum(tx for tx, ty in comp)
                    sum_y = sum(ty for tx, ty in comp)
                    avg_x = round(sum_x / len(comp))
                    avg_y = round(sum_y / len(comp))
                    
                    clusters.append({
                        "name": name,
                        "chinese": OBJECT_TRANSLATIONS.get(name, name),
                        "x": avg_x,
                        "y": avg_y,
                        "tile_count": len(comp)
                    })
        return jsonify({"objects": clusters, "count": len(clusters)})
    except Exception as e:
        return jsonify({"error": str(e)})


def start_ui():
    socketio.run(
        app,
        host=CONFIG["ui"]["host"],
        port=CONFIG["ui"]["port"],
        debug=False,
        allow_unsafe_werkzeug=True,
    )


if __name__ == "__main__":
    start_ui()
