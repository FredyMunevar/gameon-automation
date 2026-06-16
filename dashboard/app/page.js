import { promises as fs } from "fs";
import path from "path";

export const dynamic = "force-dynamic"; // siempre leer el JSON más reciente

const TZ = "America/Bogota";
const dayFmt = new Intl.DateTimeFormat("es-CO", { weekday: "short", day: "numeric", month: "short", timeZone: TZ });
const timeFmt = new Intl.DateTimeFormat("es-CO", { hour: "numeric", minute: "2-digit", hour12: true, timeZone: TZ });
const stampFmt = new Intl.DateTimeFormat("es-CO", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit", hour12: true, timeZone: TZ });

function parsePick(s) {
  const [h, a] = String(s || "").split("-").map((n) => parseInt(n, 10));
  return [h, a];
}

// Puntaje de la polla: 6 exacto / 4 ganador+dif / 3 resultado / 0 fallo.
function points(pick, real) {
  const [ph, pa] = parsePick(pick), [ah, aa] = parsePick(real);
  if ([ph, pa, ah, aa].some(Number.isNaN)) return null;
  if (ph === ah && pa === aa) return 6;
  const po = Math.sign(ph - pa), ao = Math.sign(ah - aa);
  if (po !== ao) return 0;
  if (po === 0) return 3;
  if (ph - pa === ah - aa) return 4;
  return 3;
}

// Texto del chip del pick actual, autoexplicativo.
function chipFor(m) {
  const a = m.actual;
  if (!a) return null;
  const [hs, as_] = parsePick(a.pick);
  if (a.tipo === "EMP") {
    let extra = "";
    if (a.prob_1X2) {
      const [ph, , pa] = a.prob_1X2.split("/").map(Number);
      const [team, p] = ph >= pa ? [m.local, ph] : [m.visitante, pa];
      extra = ` (${team} ${p}%)`;
    }
    return { cls: "EMP", text: `Parejo · juego 1-1${extra}` };
  }
  if (hs > as_) return { cls: a.tipo, text: `Gana ${m.local} · ${a.conf}%` };
  if (as_ > hs) return { cls: a.tipo, text: `Gana ${m.visitante} · ${a.conf}%` };
  return { cls: a.tipo, text: `${a.conf}%` };
}

async function loadData() {
  const file = path.join(process.cwd(), "data", "history.json");
  return JSON.parse(await fs.readFile(file, "utf8"));
}

export default async function Page() {
  const data = await loadData();
  const matches = Object.values(data.matches || {})
    .filter((m) => m.saque_utc)
    .sort((a, b) => a.saque_utc.localeCompare(b.saque_utc));

  // resumen de puntos de lo ya jugado
  let total = 0, jugados = 0;
  for (const m of matches) {
    if (m.resultado && m.actual) {
      const p = points(m.actual.pick, m.resultado);
      if (p != null) { total += p; jugados++; }
    }
  }

  // agrupar por día (Bogotá)
  const groups = [];
  let cur = null;
  for (const m of matches) {
    const day = dayFmt.format(new Date(m.saque_utc));
    if (!cur || cur.day !== day) { cur = { day, items: [] }; groups.push(cur); }
    cur.items.push(m);
  }

  return (
    <main className="wrap">
      <div className="header">
        <h1>⚽ Polla GameOn — Pronósticos</h1>
        <div className="sub">
          Modelo Poisson-Elo (bayesiano) · Mundial 2026 · {matches.length} partidos
          {jugados > 0 && <> · <b>{total} pts</b> en {jugados} jugados</>}
        </div>
        {data.updated && <div className="sub">Actualizado: {stampFmt.format(new Date(data.updated))} (Bogotá)</div>}
      </div>

      {groups.map((g) => (
        <section className="daygroup" key={g.day}>
          <h2 className="daytitle">{g.day}</h2>
          {g.items.map((m) => {
            const chip = chipFor(m);
            const played = !!m.resultado;
            const pts = played && m.actual ? points(m.actual.pick, m.resultado) : null;
            return (
              <div className="card" key={m.fixtureId}>
                <div className="row1">
                  <div className="teams">
                    {m.local}
                    <span className="score">{m.actual ? m.actual.pick : "—"}</span>
                    {m.visitante}
                  </div>
                  <div className="time">{timeFmt.format(new Date(m.saque_utc))}</div>
                </div>

                <div className="meta">
                  {chip && <span className={`chip ${chip.cls}`}>{chip.text}</span>}
                  {played && <span className="result">Resultado {m.resultado}</span>}
                  {pts != null && <span className={`pts p${pts}`}>{pts} pts</span>}
                  {m.actual?.prob_1X2 && !played && <span className="prob">1X2 {m.actual.prob_1X2}</span>}
                </div>

                {m.history?.length > 1 && (
                  <details>
                    <summary>Historial ({m.history.length})</summary>
                    <ul className="timeline">
                      {m.history.map((h, i) => (
                        <li className="tl" key={i}>
                          <span className="when">{h.date}</span>
                          <span className="pk">{h.pick}</span>
                          <span className="lbl">
                            {h.etapa ? h.etapa : (h.fuente === "auto" ? "modelo" : "")}
                            {h.conf ? ` · ${h.tipo} ${h.conf}%` : ""}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            );
          })}
        </section>
      ))}

      <p className="legend">
        El <b>marcador</b> es mi pick. El color indica qué tan claro es el favorito:{" "}
        <span className="dot" style={{ color: "var(--fav-fg)" }}>verde</span> muy claro (≥68%) ·{" "}
        <span className="dot" style={{ color: "var(--sor-fg)" }}>naranja</span> moderado (58–68%) ·{" "}
        <span className="dot" style={{ color: "var(--emp-fg)" }}>azul</span> sin favorito → 1-1.
        Puntaje: 6 exacto · 4 ganador+diferencia · 3 resultado. Despliega el historial para ver cómo cambió cada pick.
      </p>
    </main>
  );
}
