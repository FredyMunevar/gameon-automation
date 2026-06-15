#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Envía tus pronósticos (los del modelo) a AppGameOn por su API REST. Sin emulador.

  Login:  Firebase Auth REST (email/clave)  ->  idToken
  Envío:  POST https://apiv2.appgameon.com/fixtures/forecasts  (Authorization: Bearer <idToken>)
          body = lista JSON de {fixtureId, localScore, visitorScore, userId}

REGLA DURA DE ALCANCE (no negociable):
  Solo se envían picks de partidos que NO han empezado (state == "NS") y a los que
  les falta más de CLOSE_MARGIN_MIN minutos para el saque. Nunca se envían partidos
  en curso o terminados. No se falsean timestamps. El gate usa el estado REAL del
  fixture que devuelve la API, no la etiqueta de fecha del pick.

CREDENCIALES POR VARIABLES DE ENTORNO (nunca en el código):
    FIREBASE_API_KEY   la key del APK (no es secreta; igual va por env)
    GAMEON_EMAIL       tu correo de GameOn
    GAMEON_PASSWORD    tu contraseña  (esto SÍ es secreto -> GitHub secret)
    GAMEON_GROUP_ID    tu liga/grupo (p.ej. 32534) — usado para LEER el calendario

USO:
    pip install requests
    export FIREBASE_API_KEY='AIza...' GAMEON_EMAIL='tu@correo' GAMEON_PASSWORD='clave' GAMEON_GROUP_ID='32534'

    python3 submit_gameon.py --probe         # login + estructura de la API
    python3 submit_gameon.py --today         # dry-run de los picks de hoy (Bogotá)
    python3 submit_gameon.py --today --go     # envía de verdad
    python3 submit_gameon.py --go             # envía TODOS los pendientes aún por jugar
"""
import os, json, argparse, datetime, sys, unicodedata
try:
    import requests
except ImportError:
    sys.exit("Falta requests -> pip install requests")

API_BASE = "https://apiv2.appgameon.com"
FB_KEY   = os.environ.get("FIREBASE_API_KEY", "")
EMAIL    = os.environ.get("GAMEON_EMAIL", "")
PASS     = os.environ.get("GAMEON_PASSWORD", "")
GROUP_ID = os.environ.get("GAMEON_GROUP_ID", "")

CLOSE_MARGIN_MIN = 5          # la app cierra la edición 5 min antes del saque
MES = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
BOGOTA = datetime.timezone(datetime.timedelta(hours=-5))

# Estados (state.developerName) que NO permiten enviar pronóstico.
PLAYABLE_STATE = "NS"         # Not Started — único estado en que se puede pronosticar

# Mapa nombre_equipo (picks.json, español) -> nombre en la API (inglés).
# Se compara normalizado (sin acentos, minúsculas, sin signos), así que basta
# con cubrir los nombres que aparecen en picks.json.
ES_TO_EN = {
    "belgica": "Belgium", "egipto": "Egypt", "iran": "Iran",
    "nueva zelanda": "New Zealand", "espana": "Spain", "cabo verde": "Cape Verde Islands",
    "arabia saudita": "Saudi Arabia", "uruguay": "Uruguay", "francia": "France",
    "senegal": "Senegal", "irak": "Iraq", "noruega": "Norway", "argentina": "Argentina",
    "argelia": "Algeria", "austria": "Austria", "jordania": "Jordan", "portugal": "Portugal",
    "r.d. congo": "Congo DR", "rd congo": "Congo DR", "uzbekistan": "Uzbekistan",
    "colombia": "Colombia", "inglaterra": "England", "croacia": "Croatia",
    "ghana": "Ghana", "panama": "Panama",
    # equipos de jornadas ya jugadas (por si se reusan en pendientes):
    "mexico": "Mexico", "sudafrica": "South Africa", "corea del sur": "Korea Republic",
    "rep. checa": "Czech Republic", "canada": "Canada", "bosnia-herz.": "Bosnia and Herzegovina",
    "qatar": "Qatar", "suiza": "Switzerland", "brasil": "Brazil", "marruecos": "Morocco",
    "haiti": "Haiti", "escocia": "Scotland", "ee. uu.": "United States", "paraguay": "Paraguay",
    "australia": "Australia", "turquia": "Türkiye", "alemania": "Germany", "curazao": "Curacao",
    "costa de marfil": "Côte d'Ivoire", "ecuador": "Ecuador", "paises bajos": "Netherlands",
    "japon": "Japan", "suecia": "Sweden", "tunez": "Tunisia",
}

def log(*a): print(*a, flush=True)

def norm(s):
    """minúsculas, sin acentos, sin puntuación, espacios colapsados."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return " ".join(ch for ch in s.replace(".", " ").replace("-", " ").split())

# claves del mapa normalizadas (los nombres en picks.json traen puntos/acentos)
_ES_TO_EN_N = {norm(k): v for k, v in ES_TO_EN.items()}

def en_name(es):
    """nombre en inglés según el mapa (claves normalizadas); si no está, devuelve es."""
    return _ES_TO_EN_N.get(norm(es), es)

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
    r = api("GET", "users/me", token)
    r.raise_for_status()
    return r.json()["userId"]

def probe(token):
    """Confirma auth y muestra estructura real."""
    for path in ["users/me", "groups", f"fixtures/groups/{GROUP_ID or '<GROUP_ID>'}"]:
        try:
            r = api("GET", path, token)
            txt = r.text
            log(f"\n=== GET {path}  [{r.status_code}] ===")
            log(txt[:1500] + (" …(recortado)" if len(txt) > 1500 else ""))
        except Exception as e:
            log(f"GET {path} -> error: {e}")

def fetch_fixtures(token, group_id):
    """Calendario del grupo -> índice {(home_norm, away_norm): fixture}."""
    r = api("GET", f"fixtures/groups/{group_id}", token)
    r.raise_for_status()
    idx = {}
    for m in r.json():
        loc = (m.get("local") or {}).get("name")
        vis = (m.get("visitor") or {}).get("name")
        if loc and vis:
            idx[(norm(loc), norm(vis))] = m
    return idx

def fixture_state(m):
    st = m.get("state") or {}
    return st.get("developerName") or st.get("shortName") or m.get("status") or "?"

def kickoff(m):
    d = m.get("date")
    if not d: return None
    try:
        return datetime.datetime.fromisoformat(d.replace("Z", "+00:00"))
    except ValueError:
        return None

def load_pending(date_filter=None):
    data = json.load(open("picks.json", encoding="utf-8"))
    pend = data.get("pendientes", [])
    if date_filter:
        pend = [p for p in pend if p["fecha"].strip() == date_filter]
    return pend

def resolve(pick, fixtures):
    """Casa un pick con su fixture por nombres (inglés, normalizado)."""
    home = norm(en_name(pick["local"]))
    away = norm(en_name(pick["visitante"]))
    return fixtures.get((home, away))

def submittable(m, now):
    """¿Se puede enviar? Solo NS y con > CLOSE_MARGIN_MIN min para el saque."""
    if fixture_state(m) != PLAYABLE_STATE:
        return False, f"estado {fixture_state(m)} (no NS)"
    ko = kickoff(m)
    if ko is None:
        return False, "sin fecha de saque"
    margin = (ko - now).total_seconds() / 60.0
    if margin <= CLOSE_MARGIN_MIN:
        return False, f"cierre: faltan {margin:.0f} min (< {CLOSE_MARGIN_MIN})"
    return True, f"OK (faltan {margin/60:.1f} h)"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true", help="solo login + ver estructura de la API")
    ap.add_argument("--today", action="store_true", help="solo picks con fecha de hoy (Bogotá)")
    ap.add_argument("--date", help='filtra por etiqueta de fecha del pick, p.ej. "Jun 16"')
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
        t = datetime.datetime.now(BOGOTA)
        date_filter = f"{MES[t.month]} {t.day}"

    pend = load_pending(date_filter)
    if not pend:
        log("Sin pendientes" + (f" para {date_filter}" if date_filter else "")); return

    user_id = get_user_id(token)
    fixtures = fetch_fixtures(token, GROUP_ID)
    log(("DRY-RUN — " if dry else "") + f"evaluando {len(pend)} picks"
        + (f" ({date_filter})" if date_filter else "") + f"  [userId={user_id}]\n")

    batch, skipped = [], 0
    for p in pend:
        line = f"[{p['grupo']}] {p['local']} {p['pick_local']}-{p['pick_visitante']} {p['visitante']}"
        m = resolve(p, fixtures)
        if not m:
            log(f"  ✗ {line}: sin fixture (no casó el nombre)"); skipped += 1; continue
        ok, why = submittable(m, now)
        if not ok:
            log(f"  ⏭  {line}: {why}"); skipped += 1; continue
        log(f"  ✓ {line}  fix={m['fixtureId']}  {why}")
        batch.append({"fixtureId": m["fixtureId"], "localScore": p["pick_local"],
                      "visitorScore": p["pick_visitante"], "userId": user_id})

    if not batch:
        log(f"\nNada que enviar ({skipped} omitidos)."); return

    log(f"\n{'DRY-RUN — ' if dry else ''}batch de {len(batch)} pronóstico(s):")
    log("  " + json.dumps(batch, ensure_ascii=False))
    if dry:
        log(f"\n(dry-run) POST fixtures/forecasts con {len(batch)} item(s). Usa --go para enviar."); return

    r = api("POST", "fixtures/forecasts", token, json=batch)
    log(f"\nPOST fixtures/forecasts -> {r.status_code}")
    log("  " + r.text[:300])
    if not r.ok:
        sys.exit("El envío falló.")
    log(f"\n{len(batch)} pronóstico(s) enviado(s). ({skipped} omitidos por alcance/sin fixture)")

if __name__ == "__main__":
    main()
