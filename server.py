#!/usr/bin/env python3
""" This is BIG-BANG - Backend de Meta (Loja / Skins / Créditos / Rank)
Servidor simples em Python puro (stdlib: http.server + sqlite3).
Serve o jogo (index.html) e a API REST no mesmo port.
Sem dependencias externas.
"""
import json
import os
import re
import sqlite3
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "slashdash.db")
PORT = int(os.environ.get("PORT", "9000"))

# ---- CATALOGO DE SKINS (autoritativo no servidor) ----
# Cada skin custa 10000 creditos e concede uma habilidade diferente.
SKINS = [
    {"id": "titan_hull",  "name": "TITAN HULL",  "rarity": "LENDARIO", "price": 10000,
     "bonus": {"hp": 200},        "color": "#ffcc00", "desc": "+200 HP Maximo"},
    {"id": "war_forge",   "name": "WAR FORGE",   "rarity": "EPICO",    "price": 7500,
     "bonus": {"force": 50},       "color": "#ff3366", "desc": "+50 Forca (dano/dash)"},
    {"id": "phantom_eye", "name": "PHANTOM EYE", "rarity": "RARO",     "price": 6500,
     "bonus": {"focus": 50},       "color": "#00ffcc", "desc": "+50% Hiper Foco (camera lenta)"},
    {"id": "blood_thirst","name": "BLOOD THIRST","rarity": "EPICO",    "price": 7500,
     "bonus": {"lifesteal": 10},   "color": "#cc33ff", "desc": "+10 Vampirismo por kill"},
    {"id": "aegis_core",  "name": "AEGIS CORE",  "rarity": "COMUM",    "price": 5000,
     "bonus": {"nanofibra": 80},   "color": "#3366ff", "desc": "+80 HP Maximo"},
]
SKIN_BY_ID = {s["id"]: s for s in SKINS}


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS players(
            nick TEXT PRIMARY KEY,
            credits INTEGER DEFAULT 0,
            kills_total INTEGER DEFAULT 0,
            high_score INTEGER DEFAULT 0,
            owned TEXT DEFAULT '[]',
            equipped TEXT DEFAULT '',
            updated_at REAL
        )"""
    )
    conn.commit()
    return conn


def sanitize_nick(nick):
    nick = (nick or "").strip()[:16]
    nick = re.sub(r"[^A-Za-z0-9_\- ]", "", nick)
    return nick or "GUEST"


def get_or_create(conn, nick):
    nick = sanitize_nick(nick)
    row = conn.execute("SELECT * FROM players WHERE nick=?", (nick,)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO players(nick,credits,kills_total,high_score,owned,equipped,updated_at) VALUES(?,0,0,0,'[]','',0)",
            (nick,),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM players WHERE nick=?", (nick,)).fetchone()
    return row


def to_profile(row):
    return {
        "nick": row["nick"],
        "credits": row["credits"],
        "kills_total": row["kills_total"],
        "high_score": row["high_score"],
        "owned": json.loads(row["owned"] or "[]"),
        "equipped": row["equipped"] or "",
    }


def tier(high_score):
    if high_score >= 1200:
        return "DIAMANTE"
    if high_score >= 600:
        return "PLATINA"
    if high_score >= 300:
        return "OURO"
    if high_score >= 100:
        return "PRATA"
    return "BRONZE"


class Handler(SimpleHTTPRequestHandler):
    directory = BASE

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _send_json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            return {}

    def do_GET(self):
        p = urlparse(self.path)
        # forcar content-type de webp (Windows nao mapeia sozinho)
        if p.path.lower().endswith(".webp"):
            self.extensions_map[".webp"] = "image/webp"
        if p.path == "/favicon.ico":
            self.send_response(204)
            self._cors()
            self.end_headers()
            return
        if p.path.startswith("/api/"):
            self.handle_api(p, None)
        else:
            super().do_GET()

    def do_POST(self):
        p = urlparse(self.path)
        data = self._body() if p.path.startswith("/api/") else {}
        if p.path.startswith("/api/"):
            self.handle_api(p, data)
        else:
            self._send_json({"error": "not found"}, 404)

    def handle_api(self, p, data):
        path = p.path
        qs = parse_qs(p.query)
        nick = (qs.get("nick", [None])[0]) or (data or {}).get("nick")
        conn = get_db()
        try:
            if path == "/api/login" and data is not None:
                row = get_or_create(conn, data.get("nick"))
                self._send_json(to_profile(row))

            elif path == "/api/report" and data is not None:
                row = get_or_create(conn, data.get("nick"))
                kills = max(0, int(data.get("kills", 0) or 0))
                score = max(0, int(data.get("score", 0) or 0))
                conn.execute(
                    "UPDATE players SET credits=credits+?, kills_total=kills_total+?, "
                    "high_score=MAX(high_score, ?), updated_at=0 WHERE nick=?",
                    (kills, kills, score, row["nick"]),
                )
                conn.commit()
                self._send_json(to_profile(conn.execute("SELECT * FROM players WHERE nick=?", (row["nick"],)).fetchone()))

            elif path == "/api/shop":
                prof = to_profile(get_or_create(conn, nick)) if nick else {"owned": [], "equipped": ""}
                self._send_json({
                    "skins": SKINS,
                    "owned": prof["owned"],
                    "equipped": prof["equipped"],
                })

            elif path == "/api/buy" and data is not None:
                row = get_or_create(conn, data.get("nick"))
                skin = SKIN_BY_ID.get(data.get("skin"))
                prof = to_profile(row)
                if not skin:
                    self._send_json({"error": "Skin inexistente"}, 400); return
                if skin["id"] in prof["owned"]:
                    self._send_json({"error": "Ja possui esta skin"}, 400); return
                if prof["credits"] < skin["price"]:
                    self._send_json({"error": "Creditos insuficientes"}, 400); return
                owned = prof["owned"] + [skin["id"]]
                conn.execute(
                    "UPDATE players SET credits=credits-?, owned=? WHERE nick=?",
                    (skin["price"], json.dumps(owned), row["nick"]),
                )
                conn.commit()
                self._send_json(to_profile(conn.execute("SELECT * FROM players WHERE nick=?", (row["nick"],)).fetchone()))

            elif path == "/api/equip" and data is not None:
                row = get_or_create(conn, data.get("nick"))
                prof = to_profile(row)
                skin_id = data.get("skin")
                if skin_id not in prof["owned"]:
                    self._send_json({"error": "Skin nao possuida"}, 400); return
                conn.execute("UPDATE players SET equipped=? WHERE nick=?", (skin_id, row["nick"]))
                conn.commit()
                self._send_json(to_profile(conn.execute("SELECT * FROM players WHERE nick=?", (row["nick"],)).fetchone()))

            elif path == "/api/rank":
                me = to_profile(get_or_create(conn, nick)) if nick else None
                board_rows = conn.execute(
                    "SELECT nick, high_score, kills_total, credits FROM players ORDER BY high_score DESC LIMIT 20"
                ).fetchall()
                board = []
                for i, r in enumerate(board_rows):
                    board.append({
                        "pos": i + 1,
                        "nick": r["nick"],
                        "high_score": r["high_score"],
                        "kills_total": r["kills_total"],
                        "credits": r["credits"],
                        "tier": tier(r["high_score"]),
                    })
                my_pos = None
                if me is not None:
                    cnt = conn.execute(
                        "SELECT COUNT(*)+1 AS c FROM players WHERE high_score > ?", (me["high_score"],)
                    ).fetchone()["c"]
                    my_pos = cnt
                self._send_json({
                    "board": board,
                    "me": {"pos": my_pos, "nick": me["nick"] if me else None,
                           "high_score": me["high_score"] if me else 0,
                           "kills_total": me["kills_total"] if me else 0,
                           "tier": tier(me["high_score"]) if me else "BRONZE"} if me else None,
                })

            else:
                self._send_json({"error": "rota desconhecida"}, 404)
        finally:
            conn.close()


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"BIG-BANG backend rodando em http://localhost:{PORT}")
    print("Abra no navegador: http://localhost:" + str(PORT))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando...")
        server.shutdown()


if __name__ == "__main__":
    main()
