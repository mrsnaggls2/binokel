from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
def home():
    return """
<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Hello World</title>
  <style>
    body { font-family: system-ui, Arial, sans-serif; margin: 2rem; line-height: 1.4; }
    .card { max-width: 520px; padding: 1.25rem 1.5rem; border: 1px solid #ddd; border-radius: 12px; }
    h1 { margin: 0 0 .5rem 0; }
    button { padding: .6rem .9rem; border-radius: 10px; border: 1px solid #ccc; background: white; cursor: pointer; }
    button:hover { background: #f6f6f6; }
    code { background: #f3f3f3; padding: .15rem .35rem; border-radius: 6px; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Hello World 👋</h1>
    <p>Deine App läuft. Das ist die HTML-Startseite.</p>

    <p>
      Test-API: <code>/api/hello</code>
    </p>

    <button onclick="loadHello()">API testen</button>
    <p id="out" style="margin-top: 1rem;"></p>
  </div>

  <script>
    async function loadHello() {
      const out = document.getElementById('out');
      out.textContent = "Lade...";
      try {
        const res = await fetch('/api/hello');
        const data = await res.json();
        out.textContent = "Antwort: " + JSON.stringify(data);
      } catch (e) {
        out.textContent = "Fehler: " + e;
      }
    }
  </script>
</body>
</html>
"""

@app.get("/api/hello")
def api_hello():
    return {"message": "Hello World from Railway 🚂"}
