set -e
R=/mnt/user-data/outputs/health-edu-assistant
cd $R

# ---------- STREAMLIT: add login ----------
python3 - <<'EOF'
p='frontend/app.py'
s=open(p).read()
s=s.replace('''def post(path: str, payload: dict):
    try:
        r = requests.post(f"{API}{path}", json=payload, timeout=90)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        st.error(f"Backend error: {e}")
        return None
''','''def post(path: str, payload: dict, auth: bool = True):
    headers = {"Authorization": f"Bearer {st.session_state.token}"} if auth and st.session_state.get("token") else {}
    try:
        r = requests.post(f"{API}{path}", json=payload, headers=headers, timeout=90)
        if r.status_code == 401 and auth:
            st.session_state.token = None
            st.warning("Session expired. Please sign in again.")
            st.rerun()
        if not r.ok:
            st.error(r.json().get("detail", r.text))
            return None
        return r.json()
    except requests.RequestException as e:
        st.error(f"Backend error: {e}")
        return None
''')
s=s.replace('''st.title("🩺 Medical & Health Information Assistant")
st.caption("Educational use only — not a substitute for professional medical advice.")
''','''st.title("🩺 Medical & Health Information Assistant")
st.caption("Educational use only — not a substitute for professional medical advice.")

if not st.session_state.get("token"):
    st.subheader("Sign in")
    email = st.text_input("Email")
    pw = st.text_input("Password (min 8 chars)", type="password")
    c1, c2 = st.columns(2)
    for col, label, path in ((c1, "Sign in", "/auth/login"), (c2, "Create account", "/auth/register")):
        if col.button(label):
            res = post(path, {"email": email, "password": pw}, auth=False)
            if res:
                st.session_state.token = res["token"]
                st.session_state.email = res["email"]
                st.rerun()
    st.stop()

with st.sidebar:
    st.write(f"Signed in as **{st.session_state.get('email', '')}**")
    if st.button("Sign out"):
        st.session_state.token = None
        st.rerun()
''')
open(p,'w').write(s)
EOF

# ---------- REACT FRONTEND (Vite) ----------
cat > web/package.json <<'EOF'
{
  "name": "health-edu-web",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": { "dev": "vite", "build": "vite build", "preview": "vite preview" },
  "dependencies": { "react": "^18.3.1", "react-dom": "^18.3.1", "react-markdown": "^9.0.1" },
  "devDependencies": { "@vitejs/plugin-react": "^4.3.1", "vite": "^5.4.0" }
}
EOF

cat > web/vite.config.js <<'EOF'
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: /api/* is proxied to FastAPI so no CORS setup is needed.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://localhost:8000", rewrite: (p) => p.replace(/^\/api/, "") } },
  },
});
EOF

cat > web/index.html <<'EOF'
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Health Education Assistant</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
EOF

cat > web/src/main.jsx <<'EOF'
import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(<App />);
EOF

cat > web/src/api.js <<'EOF'
const BASE = import.meta.env.VITE_API_URL || "/api";

export const session = {
  get token() { return localStorage.getItem("token"); },
  get email() { return localStorage.getItem("email"); },
  set(token, email) { localStorage.setItem("token", token); localStorage.setItem("email", email); },
  clear() { localStorage.removeItem("token"); localStorage.removeItem("email"); },
};

export async function post(path, body, { auth = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth && session.token) headers.Authorization = `Bearer ${session.token}`;
  const res = await fetch(`${BASE}${path}`, { method: "POST", headers, body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && auth) {
    session.clear();
    window.dispatchEvent(new Event("signed-out"));
  }
  if (!res.ok) {
    const d = data.detail;
    throw new Error(typeof d === "string" ? d : d ? "Please check your input." : `Request failed (${res.status})`);
  }
  return data;
}
EOF

cat > web/src/App.jsx <<'EOF'
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { post, session } from "./api";

function Result({ res }) {
  if (!res) return null;
  return (
    <div className={res.emergency ? "card emergency" : "card"}>
      <ReactMarkdown>{res.answer}</ReactMarkdown>
      {res.sources?.length > 0 && <p className="muted">Sources: {res.sources.join(", ")}</p>}
      <p className="disclaimer"><ReactMarkdown>{res.disclaimer}</ReactMarkdown></p>
    </div>
  );
}

function useCall() {
  const [state, set] = useState({ loading: false, error: "", data: null });
  const run = async (fn) => {
    set({ loading: true, error: "", data: null });
    try { set({ loading: false, error: "", data: await fn() }); }
    catch (e) { set({ loading: false, error: e.message, data: null }); }
  };
  return [state, run];
}

function TextTab({ path, label, placeholder, button }) {
  const [q, setQ] = useState("");
  const [s, run] = useCall();
  return (
    <section>
      <label>{label}</label>
      <textarea rows={3} value={q} placeholder={placeholder} onChange={(e) => setQ(e.target.value)} />
      <button disabled={s.loading || q.trim().length < 2} onClick={() => run(() => post(path, { query: q }))}>
        {s.loading ? "Working…" : button}
      </button>
      {s.error && <p className="error">{s.error}</p>}
      <Result res={s.data} />
    </section>
  );
}

const STATUS = { normal: "🟢 normal", low: "🔻 low", high: "🔺 high", unknown: "❔ unknown" };

function Labs() {
  const [rows, setRows] = useState([{ name: "Hemoglobin", value: "11.2" }, { name: "LDL", value: "135" }]);
  const [sex, setSex] = useState("");
  const [s, run] = useCall();
  const upd = (i, k, v) => setRows(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  const items = rows.filter((r) => r.name.trim() && r.value !== "" && !isNaN(Number(r.value)))
                    .map((r) => ({ name: r.name, value: Number(r.value) }));
  return (
    <section>
      <p className="muted">Try: Hemoglobin, HDL, LDL, Triglycerides, Platelets, WBC, A1c, Glucose, Hematocrit.</p>
      <select value={sex} onChange={(e) => setSex(e.target.value)}>
        <option value="">Sex: not specified</option><option>Female</option><option>Male</option>
      </select>
      {rows.map((r, i) => (
        <div className="row" key={i}>
          <input value={r.name} placeholder="Test" onChange={(e) => upd(i, "name", e.target.value)} />
          <input value={r.value} placeholder="Value" inputMode="decimal" onChange={(e) => upd(i, "value", e.target.value)} />
          <button className="ghost" onClick={() => setRows(rows.filter((_, j) => j !== i))}>✕</button>
        </div>
      ))}
      <div className="row">
        <button className="ghost" onClick={() => setRows([...rows, { name: "", value: "" }])}>+ Add test</button>
        <button disabled={s.loading || !items.length}
                onClick={() => run(() => post("/labs/analyze", { items, sex: sex || null }))}>
          {s.loading ? "Analyzing…" : "Analyze"}
        </button>
      </div>
      {s.error && <p className="error">{s.error}</p>}
      {s.data?.results && (
        <div className="scroll">
          <table>
            <thead><tr><th>Test</th><th>Value</th><th>Typical range</th><th>Status</th></tr></thead>
            <tbody>
              {s.data.results.map((r, i) => (
                <tr key={i}>
                  <td>{r.analyte || r.input_name}</td><td>{r.value} {r.unit}</td>
                  <td>{r.reference_range || "—"}</td><td>{STATUS[r.status]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Result res={s.data} />
    </section>
  );
}

function Flashcards() {
  const [topic, setTopic] = useState("");
  const [count, setCount] = useState(6);
  const [i, setI] = useState(0);
  const [flip, setFlip] = useState(false);
  const [s, run] = useCall();
  const cards = s.data?.cards || [];
  const go = (n) => { setI(n); setFlip(false); };
  return (
    <section>
      <label>Topic</label>
      <input value={topic} placeholder="cholesterol" onChange={(e) => setTopic(e.target.value)} />
      <label>Cards: {count}</label>
      <input type="range" min="3" max="12" value={count} onChange={(e) => setCount(+e.target.value)} />
      <button disabled={s.loading || topic.trim().length < 2}
              onClick={() => { go(0); run(() => post("/flashcards", { topic, count })); }}>
        {s.loading ? "Generating…" : "Generate cards"}
      </button>
      {s.error && <p className="error">{s.error}</p>}
      {s.data?.emergency && <Result res={s.data} />}
      {cards.length > 0 && (
        <>
          <div className={flip ? "flashcard back" : "flashcard"} onClick={() => setFlip(!flip)}>
            {flip ? cards[i].back : cards[i].front}
            <small>{i + 1} / {cards.length} · tap to flip</small>
          </div>
          <div className="row">
            <button className="ghost" disabled={i === 0} onClick={() => go(i - 1)}>← Prev</button>
            <button className="ghost" disabled={i === cards.length - 1} onClick={() => go(i + 1)}>Next →</button>
          </div>
        </>
      )}
      {s.data && !s.data.emergency && cards.length === 0 && <p className="muted">No cards could be made from the reference material for that topic.</p>}
    </section>
  );
}

function Login({ onDone }) {
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [s, run] = useCall();
  const submit = (path) => run(async () => {
    const d = await post(path, { email, password: pw }, { auth: false });
    session.set(d.token, d.email);
    onDone();
    return d;
  });
  return (
    <section className="login">
      <h2>Sign in</h2>
      <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <input type="password" placeholder="Password (min 8 characters)" value={pw} onChange={(e) => setPw(e.target.value)} />
      <div className="row">
        <button disabled={s.loading} onClick={() => submit("/auth/login")}>Sign in</button>
        <button className="ghost" disabled={s.loading} onClick={() => submit("/auth/register")}>Create account</button>
      </div>
      {s.error && <p className="error">{s.error}</p>}
    </section>
  );
}

const TABS = ["Explain", "Labs", "Dictionary", "Flashcards"];

export default function App() {
  const [authed, setAuthed] = useState(!!session.token);
  const [tab, setTab] = useState("Explain");
  useEffect(() => {
    const off = () => setAuthed(false);
    window.addEventListener("signed-out", off);
    return () => window.removeEventListener("signed-out", off);
  }, []);

  return (
    <main>
      <header>
        <h1>🩺 Health Education Assistant</h1>
        {authed && <button className="ghost" onClick={() => { session.clear(); setAuthed(false); }}>Sign out</button>}
      </header>
      <p className="muted">Educational use only — not medical advice.</p>
      {!authed ? <Login onDone={() => setAuthed(true)} /> : (
        <>
          <nav>{TABS.map((t) => <button key={t} className={t === tab ? "tab active" : "tab"} onClick={() => setTab(t)}>{t}</button>)}</nav>
          {tab === "Explain" && <TextTab path="/explain" label="What would you like to understand?" placeholder="How does insulin regulate blood sugar?" button="Explain" />}
          {tab === "Labs" && <Labs />}
          {tab === "Dictionary" && <TextTab path="/vocab" label="Medical term" placeholder="thrombocytopenia" button="Look up" />}
          {tab === "Flashcards" && <Flashcards />}
        </>
      )}
    </main>
  );
}
EOF

cat > web/src/styles.css <<'EOF'
:root { --bg:#f6f8fa; --fg:#1f2933; --card:#fff; --accent:#0e7c86; --border:#d8dee4; --muted:#667085; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#14181d; --fg:#e6e9ec; --card:#1c222a; --accent:#3ab8c3; --border:#2d3640; --muted:#98a2b3; }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:16px/1.5 system-ui, sans-serif; }
main { max-width: 760px; margin: 0 auto; padding: 16px; }
header { display:flex; justify-content:space-between; align-items:center; }
h1 { font-size: 1.3rem; margin: 8px 0; }
nav { display:flex; gap:6px; overflow-x:auto; margin:12px 0; }
section { display:flex; flex-direction:column; gap:10px; }
input, textarea, select { width:100%; padding:10px; border:1px solid var(--border); border-radius:8px; background:var(--card); color:var(--fg); font:inherit; }
button { padding:10px 16px; border:0; border-radius:8px; background:var(--accent); color:#fff; font:inherit; cursor:pointer; }
button:disabled { opacity:.5; cursor:not-allowed; }
button.ghost { background:transparent; color:var(--accent); border:1px solid var(--accent); }
.tab { background:var(--card); color:var(--fg); border:1px solid var(--border); white-space:nowrap; }
.tab.active { background:var(--accent); color:#fff; }
.row { display:flex; gap:8px; }
.card { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:12px 16px; }
.card.emergency { border-color:#d92d20; background:rgba(217,45,32,.08); }
.disclaimer { font-size:.85rem; color:var(--muted); border-top:1px solid var(--border); padding-top:8px; }
.muted { color:var(--muted); font-size:.9rem; }
.error { color:#d92d20; }
.scroll { overflow-x:auto; }
table { width:100%; border-collapse:collapse; background:var(--card); }
th, td { text-align:left; padding:8px; border-bottom:1px solid var(--border); font-size:.92rem; white-space:nowrap; }
.flashcard { min-height:160px; display:flex; flex-direction:column; justify-content:center; align-items:center; text-align:center; gap:12px; padding:20px; background:var(--card); border:2px solid var(--accent); border-radius:14px; font-size:1.1rem; cursor:pointer; }
.flashcard.back { background:var(--accent); color:#fff; }
.flashcard small { opacity:.7; font-size:.75rem; }
.login { max-width:380px; margin:24px auto; }
EOF

cat > web/nginx.conf <<'EOF'
server {
  listen 80;
  root /usr/share/nginx/html;
  location /api/ { proxy_pass http://backend:8000/; proxy_set_header X-Forwarded-For $remote_addr; proxy_set_header X-Real-IP $remote_addr; }
  location / { try_files $uri /index.html; }
}
EOF

cat > web/Dockerfile <<'EOF'
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EOF

cat > docker-compose.yml <<'EOF'
services:
  backend:
    build: ./backend
    env_file: .env
    environment:
      CHROMA_DIR: /srv/medical_db
      USER_DB: /srv/state/users.db
    volumes:
      - chroma:/srv/medical_db
      - state:/srv/state
      - ./backend/data:/srv/data
    ports: ["8000:8000"]
  web:            # React UI -> http://localhost:3000
    build: ./web
    ports: ["3000:80"]
    depends_on: [backend]
  streamlit:      # optional alternative UI -> http://localhost:8501
    build: ./frontend
    environment:
      API_URL: http://backend:8000
    ports: ["8501:8501"]
    depends_on: [backend]
volumes:
  chroma:
  state:
EOF

cat > README.md <<'EOF'
# Health Education Assistant (RAG)

React (or Streamlit) UI -> FastAPI (JWT auth + rate limits) -> ChromaDB -> Gemini, with safety guardrails.

## Setup
```bash
cp .env.example backend/.env      # set GOOGLE_API_KEY and JWT_SECRET (32+ chars)
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python ingest.py --reset          # indexes ./data
uvicorn app.main:app --reload     # http://localhost:8000/docs
```
**React UI:** `cd web && npm install && npm run dev` -> http://localhost:5173
**Streamlit UI (optional):** `cd frontend && pip install -r requirements.txt && streamlit run app.py`
**Docker:** `cp .env.example .env`, `docker compose up --build`, then
`docker compose exec backend python ingest.py --reset` -> React at :3000.

## Auth & rate limiting
- `POST /auth/register` and `/auth/login` return a JWT; all other endpoints need `Authorization: Bearer <token>`.
- Per-user limit (`RATE_LIMIT_PER_MIN`, default 20) and per-IP limit on auth routes (default 8). In-memory, single
  process: swap `_check` in `app/auth.py` for Redis if you run multiple instances.
- Set `ALLOW_REGISTRATION=false` after creating accounts to close signup. Put the app behind HTTPS in production.

## Evaluation
```bash
cd backend
pytest                              # offline: safety, lab ranges, rate limiter (no API key)
python -m eval.run_eval             # live: emergency/scope/grounding/out-of-scope cases
python -m eval.run_eval --judge     # adds LLM-as-judge faithfulness check
```
Add cases to `backend/eval/cases.json`; the runner exits non-zero below `--min` (default 0.9), so it works in CI.
Rerun it after changing prompts, models, chunking, or source documents.

## Notes
- Sample data is illustrative; use licensed sources (MedlinePlus/NIH, WHO).
- Lab ranges in `app/labs.py` are typical adult values; a report's own ranges take priority.
- Keyword screening is a basic safeguard, not triage. Have a clinician review before public use.
EOF

python3 -m py_compile backend/app/*.py backend/eval/run_eval.py backend/tests/test_offline.py frontend/app.py
# run the offline logic tests that need only stdlib modules
cd backend && python3 - <<'EOF'
import sys; sys.path.insert(0,'.')
from app import safety, labs
assert safety.is_emergency("chest pain") and not safety.is_emergency("what is hemoglobin")
assert safety.asks_for_personal_diagnosis("Do I have cancer?")
assert labs.evaluate("Hgb",12.5,"female")["status"]=="normal"
assert labs.evaluate("Hgb",12.5,"male")["status"]=="low"
assert labs.evaluate("LDL",135)["status"]=="high"
assert labs.evaluate("hdl",45,"female")["status"]=="low"
print("logic ok")
EOF
cd /mnt/user-data/outputs && rm -f health-edu-assistant.zip && zip -qr health-edu-assistant.zip health-edu-assistant -x "*/__pycache__/*" && echo zipped
