#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cliente de AppGameOn: login Firebase REST + envío de pronósticos. Sin emulador.

MODO POR DEFECTO (modelo vivo):
  1. login Firebase  ->  idToken
  2. GET fixtures/groups/{GROUP_ID}   (trae resultados FT + estados NS)
  3. actualiza el Elo bayesiano ACUMULADO con TODOS los partidos jugados (FT)
  4. re-predice TODOS los partidos NS con el motor de model.py (Poisson-Elo + Dixon-Coles)
  5. envía/edita esos picks vía  POST fixtures/forecasts

MODO RESPALDO (--from-picks): envía los picks estáticos de picks.json.

REGLA DURA DE ALCANCE (no negociable):
  Solo se envían picks de partidos NO empezados (state == "NS") y con > CLOSE_MARGIN_MIN
  minutos para el saque. Nunca partidos en curso/terminados. El gate usa el estado REAL
  del fixture, no etiquetas de fecha. No se falsean timestamps.

CREDENCIALES POR VARIABLES DE ENTORNO (nunca en el código):
    FIREBASE_API_KEY   key del APK (no secreta; igual va por env)
    GAMEON_EMAIL       correo de GameOn
    GAMEON_PASSWORD    contraseña  (SECRETO -> GitHub secret)
    GAMEON_GROUP_ID    id del grupo/liga (p.ej. 32534) — para LEER el calendario

USO:
    pip install requests
    export FIREBASE_API_KEY=... GAMEON_EMAIL=... GAMEON_PASSWORD=... GAMEON_GROUP_ID=32534

    python3 submit_gameon.py --probe          # login + estructura de la API
    python3 submit_gameon.py                  # dry-run del modelo vivo (todos los NS)
    python3 submit_gameon.py --go             # envía de verdad (modelo vivo)
    python3 submit_gameon.py --today          # dry-run, solo los NS que sacan hoy (Bogotá)
    python3 submit_gameon.py --from-picks --go # envía picks.json estático
"""
import os, json, argparse, datetime, sys, unicodedata
try:
    import requests
except ImportError:
    sys.exit("Falta requests -> pip install requests")

import model  # motor Elo/Poisson (importable, sin efectos colaterales)

API_BASE = "https://apiv2.appgameon.com"
FB_KEY   = os.environ.get("FIREBASE_API_KEY", "")
EMAIL    = os.environ.get("GAMEON_EMAIL", "")
PASS     = os.environ.get("GAMEON_PASSWORD", "")
GROUP_ID = os.environ.get("GAMEON_GROUP_ID", "")

CLOSE_MARGIN_MIN = 5          # la app cierra la edición 5 min antes del saque
PLAYABLE_STATE   = "NS"       # Not Started — único estado en que se puede pronosticar
MES = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
BOGOTA = datetime.timezone(datetime.timedelta(hours=-5))

# Anfitriones (clave Elo): tienen ventaja de campo jugando de local.
HOSTS = {"USA", "Mexico", "Canada"}

# Nombre de equipo en la API -> clave del Elo de model.py (solo los que difieren).
API_TO_ELO = {
    "Korea Republic": "South Korea", "Czech Republic": "Czechia",
    "Bosnia and Herzegovina": "Bosnia", "United States": "USA",
    "Türkiye": "Turkey", "Turkiye": "Turkey", "Côte d'Ivoire": "Ivory Coast",
    "Cape Verde Islands": "Cape Verde", "Congo DR": "DR Congo",
}

# Nombre de equipo en la API -> español (para mostrar en logs / picks_generated.json).
API_TO_ES = {
    "Belgium":"Bélgica","Egypt":"Egipto","Iran":"Irán","New Zealand":"Nueva Zelanda",
    "Spain":"España","Cape Verde Islands":"Cabo Verde","Saudi Arabia":"Arabia Saudita",
    "Uruguay":"Uruguay","France":"Francia","Senegal":"Senegal","Iraq":"Irak","Norway":"Noruega",
    "Argentina":"Argentina","Algeria":"Argelia","Austria":"Austria","Jordan":"Jordania",
    "Portugal":"Portugal","Congo DR":"R.D. Congo","Uzbekistan":"Uzbekistán","Colombia":"Colombia",
    "England":"Inglaterra","Croatia":"Croacia","Ghana":"Ghana","Panama":"Panamá",
    "Mexico":"México","South Africa":"Sudáfrica","Korea Republic":"Corea del Sur",
    "Czech Republic":"Rep. Checa","Canada":"Canadá","Bosnia and Herzegovina":"Bosnia-Herz.",
    "Qatar":"Qatar","Switzerland":"Suiza","Brazil":"Brasil","Morocco":"Marruecos","Haiti":"Haití",
    "Scotland":"Escocia","United States":"EE. UU.","Paraguay":"Paraguay","Australia":"Australia",
    "Türkiye":"Turquía","Germany":"Alemania","Curacao":"Curazao","Côte d'Ivoire":"Costa de Marfil",
    "Ecuador":"Ecuador","Netherlands":"Países Bajos","Japan":"Japón","Sweden":"Suecia","Tunisia":"Túnez",
}

def log(*a): print(*a, flush=True)

def norm(s):
    """minúsculas, sin acentos, sin puntuación, espacios colapsados."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return " ".join(ch for ch in s.replace(".", " ").replace("-", " ").split())

def elo_key(api_name):
    return API_TO_ELO.get(api_name, api_name)

def es_name(api_name):
    return API_TO_ES.get(api_name, api_name)

# ------------------------------ API ------------------------------
def sign_in():
    if not (FB_KEY and EMAIL and PASS):
        sys.exit("Faltan FIREBASE_API_KEY / GAMEON_EMAIL / GAMEON_PASSWORD en el entorno.")
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FB_KEY}"
    r = requests.post(url, json={"email": EMAIL, "password": PASS, "returnSecureToken": True}, timeout=20)
    if not r.ok:
        sys.exit(f"Login falló ({r.status_code}): {r.text[:300]}")
    log("Login OK — idToken obtenido (válido ~1h; cada corrida hace login fresco).")
    return r.json()["idToken"]

def api(method, path, token, **kw):
    url = f"{API_BASE}/{path.lstrip('/')}"
    h = kw.pop("headers", {}); h["Authorization"] = f"Bearer {token}"
    return requests.request(method, url, headers=h, timeout=30, **kw)

def get_user_id(token):
    r = api("GET", "users/me", token); r.raise_for_status()
    return r.json()["userId"]

def fetch_fixtures(token, group_id):
    r = api("GET", f"fixtures/groups/{group_id}", token); r.raise_for_status()
    return r.json()

def probe(token):
    for path in ["users/me", "groups", f"fixtures/groups/{GROUP_ID or '<GROUP_ID>'}"]:
        try:
            r = api("GET", path, token); txt = r.text
            log(f"\n=== GET {path}  [{r.status_code}] ===")
            log(txt[:1500] + (" …(recortado)" if len(txt) > 1500 else ""))
        except Exception as e:
            log(f"GET {path} -> error: {e}")

# --------------------------- helpers fixture ---------------------------
def fstate(m):
    st = m.get("state") or {}
    return st.get("developerName") or st.get("shortName") or m.get("status") or "?"

def kickoff(m):
    d = m.get("date")
    if not d: return None
    try:
        return datetime.datetime.fromisoformat(d.replace("Z", "+00:00"))
    except ValueError:
        return None

def submittable(m, now):
    if fstate(m) != PLAYABLE_STATE:
        return False, f"estado {fstate(m)} (no NS)"
    ko = kickoff(m)
    if ko is None:
        return False, "sin fecha de saque"
    margin = (ko - now).total_seconds() / 60.0
    if margin <= CLOSE_MARGIN_MIN:
        return False, f"cierre: faltan {margin:.0f} min (< {CLOSE_MARGIN_MIN})"
    return True, f"OK (faltan {margin/60:.1f} h)"

# --------------------------- Elo bayesiano vivo ---------------------------
def build_updated_elo(fixtures):
    """Aplica el Elo bayesiano ACUMULADO con todos los partidos FT (en orden)."""
    working = dict(model.ELO)
    ft = sorted([m for m in fixtures if fstate(m) == "FT"], key=lambda m: m.get("date") or "")
    applied, skipped = 0, []
    for m in ft:
        loc, vis = m.get("local") or {}, m.get("visitor") or {}
        hk, ak = elo_key(loc.get("name")), elo_key(vis.get("name"))
        gh, ga = loc.get("score"), vis.get("score")
        if hk not in working or ak not in working:
            skipped.append((loc.get("name"), vis.get("name"))); continue
        if gh is None or ga is None:
            skipped.append((loc.get("name"), vis.get("name"))); continue
        host_home = hk in HOSTS
        dh = model.elo_update(working[hk], working[ak], gh, ga, host_home)
        da = model.elo_update(working[ak], working[hk], ga, gh, False)
        working[hk] += dh; working[ak] += da; applied += 1
    return working, applied, skipped

def predict(hk, ak, host_home, elo):
    """Devuelve (pick (hs,as), meta) usando el motor de model.py."""
    lh, la = model.lambdas(hk, ak, host_home, False, elo=elo)
    M = model.score_matrix(lh, la)
    ph, pd, pa = model.outcome_probs(M)
    evp, ev = model.ev_pick(M); mod = model.modal_score(M)
    rec = model.recommend(dict(ph=ph, pd=pd, pa=pa, pick=evp, modal=mod))
    coin = not (ph >= 0.58 or pa >= 0.58)
    typ = "EMP" if coin else ("FAV" if max(ph, pa) >= 0.68 else "SOR")
    po = (rec[0] > rec[1]) - (rec[0] < rec[1])
    conf = ph if po > 0 else (pd if po == 0 else pa)
    return rec, dict(ph=round(ph*100), pd=round(pd*100), pa=round(pa*100),
                     modal=mod, evpick=evp, type=typ, conf=round(conf*100))

def compute_live_batch(fixtures, user_id, now, date_filter=None):
    """Modelo vivo: Elo acumulado + predicción de todos los NS enviables."""
    elo, applied, skipped_ft = build_updated_elo(fixtures)
    log(f"Elo bayesiano: {applied} partidos FT aplicados"
        + (f"; {len(skipped_ft)} sin equipo Elo (placeholders/knockout)" if skipped_ft else "") + "\n")

    batch, record, skipped = [], [], 0
    for m in sorted(fixtures, key=lambda x: x.get("date") or ""):
        loc, vis = m.get("local") or {}, m.get("visitor") or {}
        hn, vn = loc.get("name"), vis.get("name")
        if not (hn and vn):
            continue
        ok, why = submittable(m, now)
        if not ok:
            continue  # silencioso: la mayoría son FT/placeholder; se reporta el total al final
        ko = kickoff(m)
        if date_filter:
            lbl = f"{MES[ko.astimezone(BOGOTA).month]} {ko.astimezone(BOGOTA).day}"
            if lbl != date_filter:
                continue
        hk, ak = elo_key(hn), elo_key(vn)
        if hk not in elo or ak not in elo:
            log(f"  ⏭  {es_name(hn)} vs {es_name(vn)}: sin Elo (equipo aún por definir)"); skipped += 1; continue
        (hs, as_), md = predict(hk, ak, hk in HOSTS, elo)
        log(f"  ✓ {es_name(hn)} {hs}-{as_} {es_name(vn)}  fix={m['fixtureId']}  "
            f"[{md['type']} {md['conf']}% · 1X2 {md['ph']}/{md['pd']}/{md['pa']}]  {why}")
        batch.append({"fixtureId": m["fixtureId"], "localScore": hs,
                      "visitorScore": as_, "userId": user_id})
        record.append({"fixtureId": m["fixtureId"], "local": es_name(hn), "visitante": es_name(vn),
                       "pick_local": hs, "pick_visitante": as_, "confianza_%": md["conf"],
                       "tipo": md["type"], "prob_1X2": f"{md['ph']}/{md['pd']}/{md['pa']}",
                       "saque_utc": m.get("date")})
    return batch, record, skipped

# --------------------------- modo respaldo: picks.json ---------------------------
def load_pending(date_filter=None):
    data = json.load(open("picks.json", encoding="utf-8"))
    pend = data.get("pendientes", [])
    if date_filter:
        pend = [p for p in pend if p["fecha"].strip() == date_filter]
    return pend

def compute_picks_batch(fixtures, user_id, now, date_filter=None):
    """Modo respaldo: casa picks.json (español) con fixtures por nombre."""
    # índice por par normalizado de nombres en inglés
    idx = {}
    for m in fixtures:
        loc = (m.get("local") or {}).get("name"); vis = (m.get("visitor") or {}).get("name")
        if loc and vis:
            idx[(norm(loc), norm(vis))] = m
    # mapa español(picks) -> inglés(API) tomando model.KEY + tabla inversa
    es2en = {norm(k): v for k, v in {**{es: en for en, es in API_TO_ES.items()}}.items()}
    def to_en(es):
        # model.KEY: español -> clave Elo (que suele = inglés API salvo casos)
        return es2en.get(norm(es), es)
    batch, skipped = [], 0
    for p in load_pending(date_filter):
        # resolvemos por nombre español -> inglés -> normalizado
        home_es, away_es = p["local"], p["visitante"]
        m = None
        for (h, a), fx in idx.items():
            if h == norm(to_en(home_es)) and a == norm(to_en(away_es)):
                m = fx; break
        line = f"[{p.get('grupo','?')}] {home_es} {p['pick_local']}-{p['pick_visitante']} {away_es}"
        if not m:
            log(f"  ✗ {line}: sin fixture (no casó el nombre)"); skipped += 1; continue
        ok, why = submittable(m, now)
        if not ok:
            log(f"  ⏭  {line}: {why}"); skipped += 1; continue
        log(f"  ✓ {line}  fix={m['fixtureId']}  {why}")
        batch.append({"fixtureId": m["fixtureId"], "localScore": p["pick_local"],
                      "visitorScore": p["pick_visitante"], "userId": user_id})
    return batch, skipped

# ------------------------------ main ------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true", help="solo login + estructura de la API")
    ap.add_argument("--today", action="store_true", help="solo partidos que sacan hoy (Bogotá)")
    ap.add_argument("--date", help='filtra por fecha de saque (Bogotá), p.ej. "Jun 16"')
    ap.add_argument("--from-picks", action="store_true", help="usar picks.json estático en vez del modelo vivo")
    ap.add_argument("--go", action="store_true", help="envía de verdad (si no, dry-run)")
    args = ap.parse_args()

    token = sign_in()
    if args.probe:
        probe(token); return
    if not GROUP_ID:
        sys.exit("Falta GAMEON_GROUP_ID (p.ej. 32534) para leer el calendario.")

    dry = not args.go
    now = datetime.datetime.now(datetime.timezone.utc)
    date_filter = args.date
    if args.today:
        t = datetime.datetime.now(BOGOTA); date_filter = f"{MES[t.month]} {t.day}"

    user_id = get_user_id(token)
    fixtures = fetch_fixtures(token, GROUP_ID)
    mode = "picks.json estático" if args.from_picks else "modelo vivo (Elo bayesiano)"
    log(("DRY-RUN — " if dry else "") + f"{mode}  [userId={user_id}]"
        + (f"  filtro={date_filter}" if date_filter else "") + "\n")

    record = []
    if args.from_picks:
        batch, skipped = compute_picks_batch(fixtures, user_id, now, date_filter)
    else:
        batch, record, skipped = compute_live_batch(fixtures, user_id, now, date_filter)

    if record:
        with open("picks_generated.json", "w", encoding="utf-8") as f:
            json.dump({"generado_utc": now.isoformat(), "picks": record}, f, ensure_ascii=False, indent=1)
        log(f"\n(picks_generated.json escrito: {len(record)} picks calculados)")

    if not batch:
        log(f"\nNada que enviar ({skipped} omitidos)."); return

    log(f"\n{'DRY-RUN — ' if dry else ''}batch de {len(batch)} pronóstico(s).")
    if dry:
        log("  " + json.dumps(batch, ensure_ascii=False))
        log("\n(dry-run) POST fixtures/forecasts. Usa --go para enviar."); return

    r = api("POST", "fixtures/forecasts", token, json=batch)
    log(f"POST fixtures/forecasts -> {r.status_code}")
    log("  " + r.text[:300])
    if not r.ok:
        sys.exit("El envío falló.")
    log(f"\n{len(batch)} pronóstico(s) enviado(s). ({skipped} omitidos por alcance/sin Elo)")

if __name__ == "__main__":
    main()
