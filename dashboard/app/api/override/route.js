// Guarda/borra un marcador forzado (override de BetAlpha) en overrides.json del repo,
// vía la API de contenidos de GitHub, y dispara la corrida para que aplique de inmediato.
// Protegido por TRIGGER_PIN. Usa GH_DISPATCH_TOKEN.
export const dynamic = "force-dynamic";

const REPO = "FredyMunevar/gameon-automation";
const FILE = "overrides.json";
const WORKFLOW = "polla.yml";

async function gh(path, token, init = {}) {
  return fetch(`https://api.github.com/repos/${REPO}/${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "gameon-override",
      ...(init.headers || {}),
    },
  });
}

export async function POST(request) {
  let body = {};
  try { body = await request.json(); } catch (e) {}
  const pin = process.env.TRIGGER_PIN;
  if (!pin) return Response.json({ ok: false, error: "Falta configurar TRIGGER_PIN" }, { status: 500 });
  if ((body.pin || "") !== pin) return Response.json({ ok: false, error: "Código incorrecto" }, { status: 401 });

  const token = process.env.GH_DISPATCH_TOKEN;
  if (!token) return Response.json({ ok: false, error: "Falta GH_DISPATCH_TOKEN" }, { status: 500 });

  const fid = String(body.fixtureId || "");
  if (!fid) return Response.json({ ok: false, error: "fixtureId requerido" }, { status: 400 });
  const remove = body.remove === true;
  const hs = Number(body.hs), as_ = Number(body.as_);
  if (!remove && (!Number.isInteger(hs) || !Number.isInteger(as_) || hs < 0 || as_ < 0))
    return Response.json({ ok: false, error: "Marcador inválido" }, { status: 400 });

  // leer overrides.json actual
  const g = await gh(`contents/${FILE}?ref=main`, token);
  if (!g.ok) return Response.json({ ok: false, error: `GitHub ${g.status} al leer overrides` }, { status: 502 });
  const cur = await g.json();
  let data = { overrides: {} };
  try { data = JSON.parse(Buffer.from(cur.content, "base64").toString("utf8")); } catch (e) {}
  if (!data.overrides) data = { overrides: data };

  if (remove) delete data.overrides[fid];
  else data.overrides[fid] = { hs, as_, src: "BetAlpha" };

  const content = Buffer.from(JSON.stringify(data, null, 2) + "\n", "utf8").toString("base64");
  const put = await gh(`contents/${FILE}`, token, {
    method: "PUT",
    body: JSON.stringify({
      message: remove ? `override: quitar ${fid}` : `override: ${fid} ${hs}-${as_} (BetAlpha)`,
      content, sha: cur.sha, branch: "main",
    }),
  });
  if (!put.ok) return Response.json({ ok: false, error: `GitHub ${put.status} al guardar` }, { status: 502 });

  // disparar la corrida para que el override se envíe ya
  await gh(`actions/workflows/${WORKFLOW}/dispatches`, token, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ref: "main" }),
  });
  return Response.json({ ok: true, removed: remove });
}
