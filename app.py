import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI()
DB_PATH = Path("app.db")


# Database helpers

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS Overview (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player1 TEXT NOT NULL,
            player2 TEXT NOT NULL,
            player3 TEXT NOT NULL,
            player4 TEXT NOT NULL,
            created_at TEXT NOT NULL,
            team1 TEXT NOT NULL,
            team2 TEXT NOT NULL,
            end_points_team1 INTEGER DEFAULT 0,
            end_points_team2 INTEGER DEFAULT 0,
            winner TEXT
        )
        """
    )
    conn.commit()
    conn.close()


@app.on_event("startup")
def on_startup():
    init_db()


# Utility

def format_date(ts: str) -> str:
    try:
        return datetime.fromisoformat(ts).strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return ts


def ensure_game_table(game_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS "{game_id}" (
            round INTEGER,
            mixing INTEGER,
            bid_value INTEGER,
            bid_team INTEGER,
            meld_team1 INTEGER,
            meld_team2 INTEGER,
            play_team1 INTEGER,
            play_team2 INTEGER,
            confirmed INTEGER,
            result_team1 INTEGER,
            result_team2 INTEGER,
            total_team1 INTEGER,
            total_team2 INTEGER
        )
        """
    )
    conn.commit()
    conn.close()


# API helpers

def fetch_overview(game_id: int) -> sqlite3.Row:
    conn = get_conn()
    row = conn.execute("SELECT * FROM Overview WHERE id = ?", (game_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Game not found")
    return row


def fetch_rounds(game_id: int) -> List[sqlite3.Row]:
    conn = get_conn()
    rows = conn.execute(f"SELECT * FROM \"{game_id}\" ORDER BY round ASC").fetchall()
    conn.close()
    return rows


def compute_previous_totals(rounds: List[sqlite3.Row]) -> Tuple[int, int]:
    if not rounds:
        return 0, 0
    last = rounds[-1]
    return last["total_team1"] or 0, last["total_team2"] or 0


# Routes


@app.get("/", response_class=HTMLResponse)
def home():
    return HTML_CONTENT


@app.get("/api/games")
def api_games():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, player1, player2, player3, player4, created_at, team1, team2, end_points_team1, end_points_team2, winner FROM Overview ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.get("/api/games/{game_id}")
def api_get_game(game_id: int):
    overview = fetch_overview(game_id)
    rounds = fetch_rounds(game_id)
    return {"overview": dict(overview), "rounds": [dict(r) for r in rounds]}


@app.post("/api/games")
def api_create_game(
    player1: str = Form(...),
    player2: str = Form(...),
    player3: str = Form(...),
    player4: str = Form(...),
    mixing_first_round: int = Form(...),
):
    names = [player1.strip(), player2.strip(), player3.strip(), player4.strip()]
    if any(not n for n in names):
        raise HTTPException(status_code=400, detail="Alle Spielernamen angeben")
    if mixing_first_round not in (1, 2, 3, 4):
        raise HTTPException(status_code=400, detail="Mischer muss 1-4 sein")

    created_at = datetime.utcnow().isoformat()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO Overview (player1, player2, player3, player4, created_at, team1, team2)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            names[0],
            names[1],
            names[2],
            names[3],
            created_at,
            f"{names[0]} & {names[2]}",
            f"{names[1]} & {names[3]}",
        ),
    )
    game_id = cur.lastrowid
    conn.commit()
    conn.close()

    ensure_game_table(game_id)
    conn = get_conn()
    conn.execute(
        f"INSERT INTO \"{game_id}\" (round, mixing) VALUES (?, ?)",
        (1, mixing_first_round),
    )
    conn.commit()
    conn.close()

    return {"id": game_id}


@app.post("/api/games/{game_id}/rounds/{round_no}/calculate")
def api_calculate_round(
    game_id: int,
    round_no: int,
    bid_value: int = Form(...),
    bid_team: int = Form(...),
    meld_team1: int = Form(0),
    meld_team2: int = Form(0),
    play_team1: int = Form(0),
    play_team2: int = Form(0),
    mode: str = Form("normal"),
):
    if bid_value < 200 or bid_value % 10 != 0:
        raise HTTPException(status_code=400, detail="Gereizt Wert muss ab 200 in 10er Schritten sein")
    if bid_team not in (1, 2):
        raise HTTPException(status_code=400, detail="Gereizt Team muss 1 oder 2 sein")
    if mode not in {"normal", "einfach_ab", "thousand"}:
        raise HTTPException(status_code=400, detail="Ungültiger Modus")

    overview = fetch_overview(game_id)
    ensure_game_table(game_id)
    rounds = fetch_rounds(game_id)
    if not rounds or round_no != rounds[-1]["round"]:
        raise HTTPException(status_code=400, detail="Nur die letzte Runde kann bearbeitet werden")

    prev_total1, prev_total2 = compute_previous_totals(rounds[:-1])

    confirmed = 0
    result_team1 = 0
    result_team2 = 0
    total_team1 = prev_total1
    total_team2 = prev_total2
    winner = None
    end_points_team1 = overview["end_points_team1"]
    end_points_team2 = overview["end_points_team2"]

    if mode == "thousand":
        # sofortiger Sieg für das gereizte Team
        if bid_team == 1:
            end_points_team1 = 1000
            end_points_team2 = 0
            winner = "Team 1"
        else:
            end_points_team1 = 0
            end_points_team2 = 1000
            winner = "Team 2"
        conn = get_conn()
        conn.execute(
            "UPDATE Overview SET end_points_team1=?, end_points_team2=?, winner=? WHERE id=?",
            (end_points_team1, end_points_team2, winner, game_id),
        )
        conn.execute(f"DELETE FROM \"{game_id}\" WHERE round=?", (round_no,))
        conn.commit()
        conn.close()
        return {"status": "thousand", "winner": winner, "end_points_team1": end_points_team1, "end_points_team2": end_points_team2}

    # Normal oder Einfach ab
    if mode == "einfach_ab":
        confirmed = 0
        if bid_team == 1:
            result_team1 = -bid_value
            result_team2 = meld_team2 + play_team2
        else:
            result_team2 = -bid_value
            result_team1 = meld_team1 + play_team1
    else:
        if bid_team == 1:
            confirmed = 1 if (meld_team1 + play_team1) >= bid_value else 0
            result_team1 = (meld_team1 + play_team1) if confirmed else -bid_value * 2
            result_team2 = meld_team2 + play_team2
        else:
            confirmed = 1 if (meld_team2 + play_team2) >= bid_value else 0
            result_team2 = (meld_team2 + play_team2) if confirmed else -bid_value * 2
            result_team1 = meld_team1 + play_team1

    total_team1 += result_team1
    total_team2 += result_team2

    conn = get_conn()
    conn.execute(
        f"""
        UPDATE "{game_id}" SET
            bid_value=?, bid_team=?, meld_team1=?, meld_team2=?, play_team1=?, play_team2=?, confirmed=?,
            result_team1=?, result_team2=?, total_team1=?, total_team2=?
        WHERE round=?
        """,
        (
            bid_value,
            bid_team,
            meld_team1,
            meld_team2,
            play_team1,
            play_team2,
            confirmed,
            result_team1,
            result_team2,
            total_team1,
            total_team2,
            round_no,
        ),
    )

    # Prüfen auf Spielende
    game_finished = False
    if bid_team == 1:
        if total_team1 >= 1000:
            winner = "Team 1"
            game_finished = True
        elif total_team1 <= -1000:
            winner = "Team 2"
            game_finished = True
    else:
        if total_team2 >= 1000:
            winner = "Team 2"
            game_finished = True
        elif total_team2 <= -1000:
            winner = "Team 1"
            game_finished = True

    if game_finished:
        end_points_team1 = total_team1
        end_points_team2 = total_team2
        conn.execute(
            "UPDATE Overview SET end_points_team1=?, end_points_team2=?, winner=? WHERE id=?",
            (end_points_team1, end_points_team2, winner, game_id),
        )
    else:
        # nächste Runde vorbereiten
        next_round = round_no + 1
        next_mixing = ((rounds[-1]["mixing"] or 1) % 4) + 1
        conn.execute(
            f"INSERT INTO \"{game_id}\" (round, mixing, total_team1, total_team2) VALUES (?, ?, ?, ?)",
            (next_round, next_mixing, total_team1, total_team2),
        )

    conn.commit()
    conn.close()

    return {
        "status": "ok",
        "game_finished": game_finished,
        "winner": winner,
        "totals": {"team1": total_team1, "team2": total_team2},
    }


@app.delete("/api/games/{game_id}")
def api_delete_game(game_id: int):
    # for cleanup/testing
    fetch_overview(game_id)
    conn = get_conn()
    conn.execute(f"DROP TABLE IF EXISTS \"{game_id}\"")
    conn.execute("DELETE FROM Overview WHERE id=?", (game_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


HTML_CONTENT = """
<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Binokel Scoreboard</title>
  <style>
    :root {
      --blue: #2563eb;
      --red: #dc2626;
      --bg: #f8fafc;
      --card: #ffffff;
      --muted: #475569;
    }
    body { font-family: system-ui, -apple-system, Arial, sans-serif; margin: 0; background: var(--bg); color: #0f172a; }
    header { padding: 16px; background: #0f172a; color: white; }
    h1 { margin: 0; font-size: 22px; }
    main { padding: 16px; max-width: 1100px; margin: 0 auto; }
    .buttons { display: flex; gap: 10px; margin-bottom: 16px; }
    button { border: 1px solid #cbd5e1; background: white; padding: 10px 14px; border-radius: 10px; cursor: pointer; font-weight: 600; }
    button.primary { background: #0f172a; color: white; border-color: #0f172a; }
    button:hover { box-shadow: 0 2px 6px rgba(0,0,0,0.08); }
    .card { background: var(--card); border: 1px solid #e2e8f0; border-radius: 14px; padding: 16px; box-shadow: 0 4px 18px rgba(15, 23, 42, 0.06); }
    .muted { color: var(--muted); }
    .row { display: flex; gap: 10px; flex-wrap: wrap; }
    input, select { padding: 10px 12px; border-radius: 10px; border: 1px solid #cbd5e1; min-width: 0; }
    table { width: 100%; border-collapse: collapse; margin-top: 12px; }
    th, td { border: 1px solid #e2e8f0; padding: 8px; text-align: center; }
    th { background: #f1f5f9; }
    .tag { display: inline-flex; align-items: center; gap: 6px; padding: 6px 10px; border-radius: 14px; background: #e2e8f0; font-weight: 600; }
    .team-blue { border: 2px solid var(--blue); }
    .team-red { border: 2px solid var(--red); }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; }
    .badge { padding: 6px 10px; border-radius: 10px; background: #e2e8f0; font-weight: 600; }
    .winner { color: #16a34a; font-weight: 700; }
    dialog { border: none; border-radius: 14px; padding: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.2); }
    dialog::backdrop { background: rgba(0,0,0,0.4); }
    .small { font-size: 14px; }
  </style>
</head>
<body>
  <header>
    <h1>Binokel Punkte-Tracker</h1>
  </header>
  <main>
    <div class="buttons">
      <button class="primary" onclick="openNewGame()">Neues Spiel</button>
      <button onclick="loadArchive()">Archiv</button>
      <button onclick="showStats()">Statistics</button>
    </div>

    <div id="game-area" class="card">
      <p class="muted">Kein Spiel ausgewählt. Lege ein neues Spiel an oder öffne das Archiv.</p>
    </div>

    <dialog id="dlg-names">
      <h3>Neues Spiel: Spielernamen</h3>
      <div class="grid">
        <input id="p1" placeholder="Spieler 1" class="team-blue" />
        <input id="p2" placeholder="Spieler 2" class="team-red" />
        <input id="p3" placeholder="Spieler 3" class="team-blue" />
        <input id="p4" placeholder="Spieler 4" class="team-red" />
      </div>
      <div style="margin-top:12px; text-align:right;">
        <button onclick="startMixerDialog()">Weiter</button>
      </div>
    </dialog>

    <dialog id="dlg-mixer">
      <h3>Wer mischt die erste Runde?</h3>
      <select id="mixer-select"></select>
      <div style="margin-top:12px; text-align:right;">
        <button onclick="createGame()">OK</button>
      </div>
    </dialog>
  </main>

<script>
let currentGame = null;
let archive = [];

async function fetchJSON(url, options={}) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}

function openNewGame() {
  document.getElementById('dlg-names').showModal();
}

function startMixerDialog() {
  const names = [p1.value.trim(), p2.value.trim(), p3.value.trim(), p4.value.trim()];
  if (names.some(n => !n)) { alert('Bitte alle Namen angeben'); return; }
  const select = document.getElementById('mixer-select');
  select.innerHTML = '';
  names.forEach((n, idx) => {
    const opt = document.createElement('option');
    opt.value = idx + 1;
    opt.textContent = n;
    select.appendChild(opt);
  });
  document.getElementById('dlg-names').close();
  document.getElementById('dlg-mixer').showModal();
}

async function createGame() {
  const names = [p1.value.trim(), p2.value.trim(), p3.value.trim(), p4.value.trim()];
  const mixer = document.getElementById('mixer-select').value;
  const body = new URLSearchParams({
    player1: names[0], player2: names[1], player3: names[2], player4: names[3], mixing_first_round: mixer
  });
  await fetchJSON('/api/games', { method: 'POST', body });
  document.getElementById('dlg-mixer').close();
  loadArchive(true);
}

async function loadArchive(autoSelect=false) {
  archive = await fetchJSON('/api/games');
  if (!archive.length) {
    document.getElementById('game-area').innerHTML = '<p class="muted">Kein Eintrag im Archiv.</p>';
    return;
  }
  const list = archive.map(g => `<li><a href="#" onclick="openGame(${g.id})">Spiel #${g.id} – ${g.team1} vs ${g.team2}</a></li>`).join('');
  document.getElementById('game-area').innerHTML = `<h3>Archiv</h3><ul>${list}</ul>`;
  if (autoSelect) openGame(archive[0].id);
}

async function openGame(id) {
  currentGame = await fetchJSON(`/api/games/${id}`);
  renderGame();
}

function headerInfo(o) {
  return `
    <div class="row" style="justify-content: space-between; gap: 16px;">
      <div>
        <div class="badge">Team 1: ${o.team1}</div>
        <div class="badge" style="margin-top:6px;">Team 2: ${o.team2}</div>
      </div>
      <div class="muted">Datum: ${new Date(o.created_at).toLocaleString()}</div>
      <div class="muted">Index: ${o.id}</div>
    </div>
  `;
}

function renderRoundTable(data) {
  const players = [data.overview.player1, data.overview.player2, data.overview.player3, data.overview.player4];
  const rows = data.rounds;
  let html = `
  <table>
    <thead>
      <tr>
        <th>Runde</th><th>Mischen</th><th>Gereizt</th><th>Gereizt Team</th>
        <th colspan="2">Team 1</th><th colspan="2">Team 2</th><th></th>
      </tr>
      <tr>
        <th></th><th></th><th></th><th></th><th>Gemeldet</th><th>Gespielt</th><th>Gemeldet</th><th>Gespielt</th><th></th>
      </tr>
    </thead>
    <tbody>
  `;

  rows.forEach(r => {
    html += `<tr>
      <td rowspan="3">${r.round}</td>
      <td rowspan="3">${players[(r.mixing||1)-1] || ''}</td>
      <td rowspan="3">${r.bid_value || ''}</td>
      <td rowspan="3">${r.bid_team ? 'Team '+r.bid_team : ''}</td>
      <td>${r.meld_team1 ?? ''}</td>
      <td>${r.play_team1 ?? ''}</td>
      <td>${r.meld_team2 ?? ''}</td>
      <td>${r.play_team2 ?? ''}</td>
      <td rowspan="3">${r.confirmed === 1 ? '✔️' : (r.confirmed === 0 && r.bid_value ? '❌' : '')}</td>
    </tr>`;
    html += `<tr><td colspan="2">Ergebnis T1: ${r.result_team1 ?? ''}</td><td colspan="2">Ergebnis T2: ${r.result_team2 ?? ''}</td></tr>`;
    html += `<tr><td colspan="2">Gesamt T1: ${r.total_team1 ?? ''}</td><td colspan="2">Gesamt T2: ${r.total_team2 ?? ''}</td></tr>`;
  });

  html += '</tbody></table>';
  return html;
}

function renderGame() {
  const o = currentGame.overview;
  let html = `<h3>Aktives Spiel</h3>${headerInfo(o)}`;
  html += renderRoundTable(currentGame);

  if (o.winner) {
    html += `<p class="winner" style="margin-top:12px;">Gewonnen: ${o.winner} – ${o.end_points_team1}:${o.end_points_team2}</p>`;
    const diff = Math.abs((o.end_points_team1||0) - (o.end_points_team2||0));
    html += `<p class="muted">Differenz: ${diff}</p>`;
  } else {
    html += buildInputForm();
  }

  document.getElementById('game-area').innerHTML = html;
}

function buildInputForm() {
  const last = currentGame.rounds[currentGame.rounds.length - 1];
  const round = last.round;
  return `
    <div class="card" style="margin-top:12px;">
      <h4>Runde ${round} eintragen</h4>
      <div class="row">
        <label>Gereizt Wert <input id="bid_value" type="number" min="200" step="10" value="${last.bid_value||200}" /></label>
        <label>Gereizt Team
          <select id="bid_team">
            <option value="1" ${last.bid_team===1?'selected':''}>Team 1</option>
            <option value="2" ${last.bid_team===2?'selected':''}>Team 2</option>
          </select>
        </label>
      </div>
      <div class="row" style="margin-top:10px;">
        <button onclick="setMode('normal')">Weiterschreiben</button>
        <button onclick="setMode('einfach_ab')">Einfach ab</button>
        <button onclick="setMode('thousand')">1000</button>
      </div>
      <div class="grid" style="margin-top:10px;" id="input-normal">
        <label>Gemeldet Team 1 <input id="meld1" type="number" value="${last.meld_team1||0}" /></label>
        <label>Gemeldet Team 2 <input id="meld2" type="number" value="${last.meld_team2||0}" /></label>
        <label>Gespielt Team 1 <input id="play1" type="number" value="${last.play_team1||0}" /></label>
        <label>Gespielt Team 2 <input id="play2" type="number" value="${last.play_team2||0}" /></label>
      </div>
      <p class="muted small" id="mode-info">Modus: normal</p>
      <div style="margin-top:10px;">
        <button class="primary" onclick="submitRound('normal')">Berechnen</button>
      </div>
    </div>
  `;
}

let currentMode = 'normal';
function setMode(mode) {
  currentMode = mode;
  const info = document.getElementById('mode-info');
  if (mode === 'einfach_ab') {
    info.textContent = 'Modus: Einfach ab – nur Gegenpartei trägt Gemeldet ein';
  } else if (mode === 'thousand') {
    info.textContent = 'Modus: 1000 – sofortiges Ende, bestätigt?';
  } else {
    info.textContent = 'Modus: normal';
  }
}

async function submitRound(forceMode='normal') {
  const mode = currentMode || forceMode;
  const last = currentGame.rounds[currentGame.rounds.length - 1];
  const params = new URLSearchParams();
  params.set('bid_value', document.getElementById('bid_value').value);
  params.set('bid_team', document.getElementById('bid_team').value);
  params.set('meld_team1', document.getElementById('meld1').value || 0);
  params.set('meld_team2', document.getElementById('meld2').value || 0);
  params.set('play_team1', document.getElementById('play1').value || 0);
  params.set('play_team2', document.getElementById('play2').value || 0);
  params.set('mode', mode);
  try {
    await fetchJSON(`/api/games/${currentGame.overview.id}/rounds/${last.round}/calculate`, { method: 'POST', body: params });
    currentGame = await fetchJSON(`/api/games/${currentGame.overview.id}`);
    renderGame();
  } catch (err) {
    alert(err.message);
  }
}

function showStats() {
  const msg = archive.length ? `Gespeicherte Spiele: ${archive.length}` : 'Keine Daten vorhanden.';
  document.getElementById('game-area').innerHTML = `<p>${msg}</p>`;
}

window.addEventListener('load', () => loadArchive());
</script>
</body>
</html>
"""
