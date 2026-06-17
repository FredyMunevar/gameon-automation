// Disparador confiable del envío diario: Vercel Cron llama a esta ruta y ésta
// dispara el workflow "polla.yml" de GitHub Actions (workflow_dispatch).
//
// Variables de entorno (en el proyecto de Vercel):
//   GH_DISPATCH_TOKEN  PAT de GitHub (fine-grained) con permiso Actions: Read & Write
//                      sobre el repo FredyMunevar/gameon-automation
//   CRON_SECRET        cadena aleatoria; Vercel la envía como Authorization: Bearer
//                      en las llamadas de cron (protege la ruta de accesos externos)

export const dynamic = "force-dynamic";

const REPO = "FredyMunevar/gameon-automation";
const WORKFLOW = "polla.yml";

export async function GET(request) {
  const secret = process.env.CRON_SECRET;
  if (secret) {
    const auth = request.headers.get("authorization");
    if (auth !== `Bearer ${secret}`) {
      return new Response("Unauthorized", { status: 401 });
    }
  }
  const token = process.env.GH_DISPATCH_TOKEN;
  if (!token) {
    return Response.json({ ok: false, error: "Falta GH_DISPATCH_TOKEN" }, { status: 500 });
  }
  const r = await fetch(
    `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
        "User-Agent": "gameon-cron",
      },
      body: JSON.stringify({ ref: "main" }),
    }
  );
  const ok = r.status === 204;
  const detail = ok ? "" : await r.text();
  return Response.json(
    { ok, dispatched: ok, githubStatus: r.status, detail },
    { status: ok ? 200 : 502 }
  );
}
