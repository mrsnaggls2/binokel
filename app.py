from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
import sqlite3
from pathlib import Path

app = FastAPI()

DB_PATH = Path("app.db")


def get_conn():
    # check_same_thread=False ist ok für dieses simple Beispiel
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS greetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/", response_class=HTMLResponse)
def home():
    conn = get_conn()
    row = conn.execute(
        "SELECT id, message, created_at FROM greetings ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()

    latest = "Noch nichts gespeichert." if row is None else f"{row['message']} (#{row['id']}, {row['created_at']})"

    return f"""
<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Hello + SQLite</title>
  <style>
    body {{ font-family: system-ui, Arial, sans-serif; margin: 2rem; line-height: 1.4; }}
    .card {{ max-width: 640px; padding: 1.25rem 1.5rem; border: 1px solid #ddd; border-radius: 12px; }}
    input {{ width: 100%; padding: .6rem .7rem; border-radius: 10px; border: 1px solid #ccc; }}
    button {{ padding: .6rem .9rem; border-radius: 10px; border: 1px solid #ccc; background: white; cursor: pointer; }}
    button:hover {{ background: #f6f6f6; }}
    code {{ background: #f3f3f3; padding: .15rem .35rem; border-radius: 6px; }}
    .row {{ display: flex; gap: .6rem; align-items: center; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Hello World + SQLite</h1>
    <p><b>Letzter gespeicherter Eintrag:</b><br>{latest}</p>

    <h3>Speichern</h3>
    <form method="post" action="/save">
      <div class="row">
        <input name="message" placeholder="Text eingeben…" value="Hello World from SQLite 👋" />
        <button type="submit">Save</button>
      </div>
    </form>

    <h3>Abrufen (API)</h3>
    <p>
      <code>GET /api/hello</code> → liefert JSON vom letzten Eintrag<br>
      <code>POST /api/hello</code> → speichert JSON: {{ "message": "..." }}
    </p>

    <button onclick="loadLatest()">Aktuellen Wert via API laden</button>
    <pre id="out" style="margin-top:1rem; white-space:pre-wrap;"></pre>
  </div>

<script>
async function loadLatest() {{
  const out = document.getElementById("out");
  out.textContent = "Lade...";
  const res = await fetch("/api/hello");
  out.textContent = await res.text();
}}
</script>
</body>
</html>
"""


@app.post("/save")
def save_from_form(message: str = Form(...)):
    conn = get_conn()
    conn.execute("INSERT INTO greetings(message) VALUES (?)", (message,))
    conn.commit()
    conn.close()
    return RedirectResponse("/", status_code=303)


@app.post("/api/hello")
def api_save_hello(payload: dict):
    message = str(payload.get("message", "")).strip()
    if not message:
        return JSONResponse({"error": "message fehlt/leer"}, status_code=400)

    conn = get_conn()
    conn.execute("INSERT INTO greetings(message) VALUES (?)", (message,))
    conn.commit()
    conn.close()
    return {"ok": True, "saved": message}


@app.get("/api/hello")
def api_get_hello():
    conn = get_conn()
    row = conn.execute(
        "SELECT id, message, created_at FROM greetings ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()

    if row is None:
        return {"message": None}

    return {"id": row["id"], "message": row["message"], "created_at": row["created_at"]}
