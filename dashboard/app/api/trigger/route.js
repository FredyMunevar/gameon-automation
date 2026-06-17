// Disparo manual desde el tablero (botón "Actualizar ahora"), protegido por un PIN.
// Env en Vercel:
//   TRIGGER_PIN        código que pide el botón (lo eliges tú)
//   GH_DISPATCH_TOKEN  el mismo token que usa /api/cron
export const dynamic = "force-dynamic";

const REPO = "FredyMunevar/gameon-automation";
const WORKFLOW = "polla.yml";

export async function POST(request) {
  let body = {};
  try { body = await request.json(); } catch (e) {}
  const pin = process.env.TRIGGER_PIN;
  if (!pin) return Response.json({ ok: false, error: "Falta configurar TRIGGER_PIN" }, { status: 500 });
  if ((body.pin || "") !== pin) return Response.json({ ok: false, error: "Código incorrecto" }, { status: 401 });

  const token = process.env.GH_DISPATCH_TOKEN;
  if (!token) return Response.json({ ok: false, error: "Falta GH_DISPATCH_TOKEN" }, { status: 500 });

  const r = await fetch(
    `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
        "User-Agent": "gameon-trigger",
      },
      body: JSON.stringify({ ref: "main" }),
    }
  );
  const ok = r.status === 204;
  return Response.json({ ok, githubStatus: r.status }, { status: ok ? 200 : 502 });
}
