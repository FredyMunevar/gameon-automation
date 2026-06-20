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
# Estrategia de pick. "modal" (marcador más probable) ganó en backtest: 45 vs 40
# (híbrido) vs 28 (EV) sobre 20 jugados, y 27 vs 25 sobre los 12 originales.
PICK_STRATEGY    = "modal"    # "modal" | "hybrid" | "ev"
# Cuotas de mercado (the-odds-api.com): mezclar la probabilidad implícita del mercado
# con el Poisson-Elo mejora el acierto (el mercado ya incorpora lesiones/forma/viajes).
ODDS_API_KEY     = os.environ.get("ODDS_API_KEY", "")
ODDS_SPORT       = "soccer_fifa_world_cup"
ODDS_WEIGHT      = 0.90       # mercado al mando; el Elo solo matiza/respalda si no hay cuotas
# "Sharp under" tipo BetAlpha: the-odds-api da totales ~0.8x más altos que BetAlpha
# (Alemania 3.08 vs 2.3, Checa 2.44 vs 2.0...). Ajustamos la μ del mercado para igualarlo;
# esto baja marcadores empatados de favoritos claros a 1-0/2-0.
ODDS_TOTAL_BIAS  = 0.80

def load_overrides(path="overrides.json"):
    """Marcadores forzados a mano (p.ej. de BetAlpha): {fixtureId: {hs, as_, src}}."""
    try:
        d = json.load(open(path, encoding="utf-8"))
        d = d.get("overrides", d)
        return {str(k): v for k, v in (d or {}).items()}
    except Exception:
        return {}

_OVERRIDES = {}   # se llena en main()

def apply_override(fixture_id, hs, as_):
    ov = _OVERRIDES.get(str(fixture_id))
    if ov and ov.get("hs") is not None and ov.get("as_") is not None:
        return int(ov["hs"]), int(ov["as_"]), (ov.get("src") or "manual")
    return hs, as_, None
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

# --------------------------- resumen HTML para el correo ---------------------------
MESES_ES = {1:"ene",2:"feb",3:"mar",4:"abr",5:"may",6:"jun",7:"jul",8:"ago",9:"sep",10:"oct",11:"nov",12:"dic"}
DIAS_ES  = {0:"lun",1:"mar",2:"mié",3:"jue",4:"vie",5:"sáb",6:"dom"}
TIPO_LABEL = {  # codigo -> (etiqueta, color_texto, color_fondo)
    "FAV": ("Favorito", "#15803d", "#dcfce7"),
    "SOR": ("Inclinado", "#b45309", "#fef3c7"),
    "EMP": ("Parejo",   "#1d4ed8", "#dbeafe"),
}

def _bogota_str(dt):
    h = dt.hour % 12 or 12
    return f"{dt.day} {MESES_ES[dt.month]} {dt.year}, {h}:{dt.minute:02d} {'am' if dt.hour < 12 else 'pm'}"

def _fmt_kickoff(iso):
    try:
        dt = datetime.datetime.fromisoformat((iso or "").replace("Z", "+00:00")).astimezone(BOGOTA)
    except Exception:
        return "", ""
    h = dt.hour % 12 or 12
    return f"{DIAS_ES[dt.weekday()]} {dt.day} {MESES_ES[dt.month]}", f"{h}:{dt.minute:02d} {'am' if dt.hour < 12 else 'pm'}"

def _ranking_html(rk):
    if not rk or rk.get("position") is None:
        return ""
    pos, total, pts = rk["position"], rk.get("total"), rk.get("points")
    old, exact = rk.get("old"), rk.get("exact")
    mov = ""
    if old:
        if pos < old:   mov = f' <span style="color:#16a34a;font-size:13px;">▲ {old - pos}</span>'
        elif pos > old: mov = f' <span style="color:#dc2626;font-size:13px;">▼ {pos - old}</span>'
        else:           mov = ' <span style="color:#94a3b8;font-size:13px;">=</span>'
    de = f' <span style="font-size:14px;font-weight:400;color:#64748b;">de {total}</span>' if total else ""
    ex = f' · {exact} exacto(s)' if exact is not None else ""
    return (
        '<div style="display:flex;gap:18px;align-items:center;justify-content:center;'
        'background:#0f172a;color:#fff;border-radius:12px;padding:14px 18px;margin:0 0 14px;">'
        '<div style="text-align:center;"><div style="font-size:11px;opacity:.7;text-transform:uppercase;letter-spacing:1px;">Puesto</div>'
        f'<div style="font-size:26px;font-weight:800;line-height:1.1;">{pos}{de}{mov}</div></div>'
        '<div style="width:1px;height:34px;background:#334155;"></div>'
        '<div style="text-align:center;"><div style="font-size:11px;opacity:.7;text-transform:uppercase;letter-spacing:1px;">Puntos</div>'
        f'<div style="font-size:26px;font-weight:800;line-height:1.1;">{pts}<span style="font-size:13px;font-weight:400;opacity:.7;">{ex}</span></div></div>'
        '</div>')

def write_html_summary(record, ft_applied, sent, dry, ranking=None, path="summary.html"):
    now_bog = datetime.datetime.now(BOGOTA)
    verbo = "calcularon (dry-run)" if dry else "enviaron"
    rows, last_day = "", None
    for r in record:
        fecha, hora = _fmt_kickoff(r.get("saque_utc"))
        if fecha != last_day:
            rows += (f'<tr><td colspan="3" style="padding:16px 10px 6px;font-weight:700;'
                     f'color:#475569;font-size:13px;text-transform:capitalize;">{fecha}</td></tr>')
            last_day = fecha
        _, fg, bg = TIPO_LABEL.get(r["tipo"], ("", "#475569", "#e2e8f0"))
        try:
            ph, pd, pa = (int(x) for x in r["prob_1X2"].split("/"))
        except Exception:
            ph, pd, pa = 0, 0, 0
        hl, vl = r["pick_local"], r["pick_visitante"]
        if hl > vl:
            chip_txt = f"Gana {r['local']} · {ph}%"
        elif vl > hl:
            chip_txt = f"Gana {r['visitante']} · {pa}%"
        else:
            strong, ps = (r["local"], ph) if ph >= pa else (r["visitante"], pa)
            chip_txt = f"Empate {hl}-{vl} · ligero fav. {strong} {ps}%"
        chip = (f'<span style="background:{bg};color:{fg};padding:2px 9px;border-radius:11px;'
                f'font-size:12px;font-weight:600;white-space:nowrap;">{chip_txt}</span>')
        rows += (
            '<tr>'
            f'<td style="padding:9px 10px;border-bottom:1px solid #eef2f7;font-size:14px;">'
            f'{r["local"]} &nbsp;<b style="font-size:15px;">{r["pick_local"]}-{r["pick_visitante"]}</b>&nbsp; {r["visitante"]}'
            f'<div style="color:#94a3b8;font-size:11px;margin-top:2px;">prob. 1X2: {r["prob_1X2"]}</div></td>'
            f'<td style="padding:9px 10px;border-bottom:1px solid #eef2f7;text-align:center;">{chip}</td>'
            f'<td style="padding:9px 10px;border-bottom:1px solid #eef2f7;color:#64748b;font-size:13px;white-space:nowrap;">{hora}</td>'
            '</tr>')
    if not rows:
        rows = ('<tr><td style="padding:18px 10px;color:#64748b;">No había partidos por enviar '
                'en esta corrida (todos empezados/terminados o sin equipos definidos).</td></tr>')
    html = (
        '<!doctype html><html><body style="margin:0;background:#f1f5f9;'
        'font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#0f172a;">'
        '<div style="max-width:640px;margin:0 auto;padding:20px;">'
        '<div style="background:#0f172a;color:#fff;border-radius:14px 14px 0 0;padding:20px 22px;">'
        '<div style="font-size:20px;font-weight:800;">⚽ Polla GameOn — picks del día</div>'
        f'<div style="opacity:.8;font-size:13px;margin-top:4px;">{_bogota_str(now_bog)} (Bogotá)</div></div>'
        '<div style="background:#fff;padding:18px 22px;">'
        + _ranking_html(ranking) +
        f'<div style="font-size:16px;">Se {verbo} <b style="font-size:22px;">{sent}</b> pronóstico(s).</div>'
        f'<div style="color:#64748b;font-size:13px;margin-top:6px;">Elo actualizado con '
        f'<b>{ft_applied}</b> partido(s) ya jugado(s). Solo se tocan partidos sin empezar.</div>'
        f'<table style="width:100%;border-collapse:collapse;margin-top:8px;">{rows}</table></div>'
        '<div style="background:#fff;border-radius:0 0 14px 14px;padding:14px 22px;'
        'border-top:1px solid #eef2f7;color:#94a3b8;font-size:12px;">'
        'Generado automáticamente. El <b>%</b> es la probabilidad de ese resultado. '
        'El color indica qué tan claro es el favorito: '
        '<b style="color:#15803d;">verde</b> muy claro (≥68%) · '
        '<b style="color:#b45309;">naranja</b> moderado (58–68%) · '
        '<b style="color:#1d4ed8;">azul</b> sin favorito → se juega 1-1.</div>'
        '</div></body></html>')
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

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

def fetch_ranking(token, group_id):
    """Posición y puntos del usuario en el grupo (de GET groups -> userRanking)."""
    try:
        r = api("GET", "groups", token); r.raise_for_status()
        for g in r.json():
            if str(g.get("groupId")) == str(group_id):
                ur = g.get("userRanking") or {}
                return {"position": ur.get("position"), "points": ur.get("points"),
                        "old": ur.get("oldPosition"), "exact": ur.get("exactPoints"),
                        "total": g.get("totalUsers"), "group": g.get("name")}
    except Exception as e:
        log(f"(no se pudo leer ranking: {e})")
    return None

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

# ---- cuotas de mercado (the-odds-api) ----
_ELO_BY_NORM = {norm(k): k for k in model.ELO}
ODDS_TO_ELO_RAW = {"Czech Republic": "Czechia", "Bosnia & Herzegovina": "Bosnia", "Curaçao": "Curacao"}
_MARKET = {}   # (eloHome, eloAway) -> {"p":(ph,pd,pa), "mu":golesTotales, "sup":supremacía}

def odds_elo_key(name):
    if name in ODDS_TO_ELO_RAW: return ODDS_TO_ELO_RAW[name]
    if name in model.ELO: return name
    return _ELO_BY_NORM.get(norm(name))

def _mu_from_over(p_over):
    """Goles totales esperados (μ) tales que Poisson(μ).P(X>=3) = p_over (línea 2.5)."""
    import math as _m
    lo, hi = 0.2, 7.0
    for _ in range(40):
        mid = (lo + hi) / 2
        pov = 1 - _m.exp(-mid) * (1 + mid + mid*mid/2)  # P(X>=3)
        if pov < p_over: lo = mid
        else: hi = mid
    return (lo + hi) / 2

def fetch_market_odds(api_key):
    """Trae 1X2 + totales + hándicap del Mundial; de-viga y promedia entre casas para
    obtener, por partido: prob. 1X2, goles totales esperados (μ) y supremacía (goles)."""
    if not api_key:
        return {}
    try:
        r = requests.get(f"https://api.the-odds-api.com/v4/sports/{ODDS_SPORT}/odds/",
                         params={"apiKey": api_key, "regions": "us,uk,eu",
                                 "markets": "h2h,totals,spreads", "oddsFormat": "decimal"}, timeout=30)
        if not r.ok:
            log(f"(cuotas: API {r.status_code} — se sigue solo con el modelo)"); return {}
        events = r.json()
    except Exception as e:
        log(f"(cuotas: error {e} — se sigue solo con el modelo)"); return {}
    out = {}
    for ev in events:
        home, away = ev.get("home_team"), ev.get("away_team")
        hk, ak = odds_elo_key(home), odds_elo_key(away)
        if not hk or not ak:
            continue
        sh = sd = sa = 0.0; n1 = 0
        smu = 0.0; nmu = 0
        ssup = 0.0; nsup = 0
        for bk in ev.get("bookmakers", []):
            mks = {m.get("key"): m for m in bk.get("markets", [])}
            # 1X2
            if "h2h" in mks:
                pr = {o.get("name"): o.get("price") for o in mks["h2h"].get("outcomes", [])}
                oh, oa, od = pr.get(home), pr.get(away), pr.get("Draw")
                if oh and oa and od:
                    ih, idr, ia = 1/oh, 1/od, 1/oa; s = ih + idr + ia
                    sh += ih/s; sd += idr/s; sa += ia/s; n1 += 1
            # totales (línea 2.5) -> μ
            if "totals" in mks:
                ov = un = None
                for o in mks["totals"].get("outcomes", []):
                    if o.get("point") == 2.5 and o.get("name") == "Over": ov = o.get("price")
                    if o.get("point") == 2.5 and o.get("name") == "Under": un = o.get("price")
                if ov and un:
                    pov = (1/ov) / (1/ov + 1/un)
                    smu += _mu_from_over(pov); nmu += 1
            # hándicap (spread) del local -> supremacía
            if "spreads" in mks:
                hp = next((o.get("point") for o in mks["spreads"].get("outcomes", [])
                           if o.get("name") == home and o.get("point") is not None), None)
                if hp is not None:
                    ssup += -hp; nsup += 1   # local -1.0 => supremacía +1.0
        if n1:
            out[(hk, ak)] = {"p": (sh/n1, sd/n1, sa/n1),
                             "mu": (smu/nmu) if nmu else None,
                             "sup": (ssup/nsup) if nsup else None}
    return out

def _market_get(hk, ak):
    if (hk, ak) in _MARKET: return _MARKET[(hk, ak)]
    if (ak, hk) in _MARKET:
        d = _MARKET[(ak, hk)]; ph, pd, pa = d["p"]
        return {"p": (pa, pd, ph), "mu": d["mu"],
                "sup": (-d["sup"] if d["sup"] is not None else None)}  # invertir orientación
    return None

def predict(hk, ak, host_home, elo):
    """Devuelve (pick (hs,as), meta). Si hay cuotas de mercado, las mezcla con el modelo."""
    lh, la = model.lambdas(hk, ak, host_home, False, elo=elo)
    mkt = _market_get(hk, ak)
    used_market = False
    if mkt and (mkt["mu"] is not None or mkt["sup"] is not None):
        w = ODDS_WEIGHT
        model_mu, model_sup = lh + la, lh - la
        mkt_mu = mkt["mu"] * ODDS_TOTAL_BIAS if mkt["mu"] is not None else None
        mu  = w * mkt_mu     + (1 - w) * model_mu  if mkt_mu     is not None else model_mu
        sup = w * mkt["sup"] + (1 - w) * model_sup if mkt["sup"] is not None else model_sup
        lh = max(model.LAMBDA_FLOOR, (mu + sup) / 2)
        la = max(model.LAMBDA_FLOOR, (mu - sup) / 2)
        used_market = True
    M = model.score_matrix(lh, la)
    ph, pd, pa = model.outcome_probs(M)
    if used_market and mkt["p"]:   # afinar el 1X2 hacia el mercado (no cambia el marcador)
        w = ODDS_WEIGHT
        ph = w * mkt["p"][0] + (1 - w) * ph
        pd = w * mkt["p"][1] + (1 - w) * pd
        pa = w * mkt["p"][2] + (1 - w) * pa
        s = ph + pd + pa; ph, pd, pa = ph/s, pd/s, pa/s
    evp, ev = model.ev_pick(M); mod = model.modal_score(M)
    if PICK_STRATEGY == "ev":       pick = evp
    elif PICK_STRATEGY == "hybrid": pick = model.recommend(dict(ph=ph, pd=pd, pa=pa, pick=evp, modal=mod))
    else:                           pick = mod   # "modal": marcador más probable
    coin = not (ph >= 0.58 or pa >= 0.58)
    typ = "EMP" if coin else ("FAV" if max(ph, pa) >= 0.68 else "SOR")
    po = (pick[0] > pick[1]) - (pick[0] < pick[1])
    conf = ph if po > 0 else (pd if po == 0 else pa)
    rng = range(len(M))
    egh = sum(i * sum(M[i]) for i in rng)
    ega = sum(j * sum(M[i][j] for i in rng) for j in rng)
    return pick, dict(ph=round(ph*100), pd=round(pd*100), pa=round(pa*100),
                     modal=mod, evpick=evp, ev=round(ev, 2), lh=round(egh, 2), la=round(ega, 2),
                     coin=coin, type=typ, conf=round(conf*100), market=used_market)

def compute_live_batch(fixtures, user_id, now, elo, date_filter=None):
    """Modelo vivo: predicción de todos los NS enviables (Elo ya calculado)."""

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
        hs, as_, osrc = apply_override(m["fixtureId"], hs, as_)
        tag = f" [OVERRIDE {osrc}]" if osrc else f" [{md['type']} {md['conf']}% · 1X2 {md['ph']}/{md['pd']}/{md['pa']}]"
        log(f"  ✓ {es_name(hn)} {hs}-{as_} {es_name(vn)}  fix={m['fixtureId']} {tag}  {why}")
        batch.append({"fixtureId": m["fixtureId"], "localScore": hs,
                      "visitorScore": as_, "userId": user_id})
        record.append({"fixtureId": m["fixtureId"], "local": es_name(hn), "visitante": es_name(vn),
                       "pick_local": hs, "pick_visitante": as_, "confianza_%": md["conf"],
                       "tipo": md["type"], "prob_1X2": f"{md['ph']}/{md['pd']}/{md['pa']}",
                       "override": osrc, "saque_utc": m.get("date")})
    return batch, record, skipped

# --------------------------- datos del tablero (Vercel) ---------------------------
# Mapas derivados de model.py: bandera, grupo, debut por equipo (español); y
# metadatos (estadio, nota, historial inicial) por par de equipos de los 24 originales.
_FLAG, _GID, _DEBUT, _META = {}, {}, {}, {}
for _mm in model.matches:
    for _side in ("home", "away"):
        _t = _mm[_side]
        _FLAG[_t[0]] = _t[1]
        _DEBUT[_t[0]] = bool(len(_t) > 2 and _t[2])
        _GID[_t[0]] = _mm["gid"]
    _META[(_mm["home"][0], _mm["away"][0])] = {
        "venue": _mm["venue"], "note": _mm["note"],
        "hist": [{"stage": h[0], "date": h[1], "hs": h[2], "as_": h[3],
                  "conf": h[4], "type": h[5], "reason": h[6]} for h in _mm["hist"]],
    }

def _reason(hs, as_, md):
    p = f"Mercado (cuotas) + Poisson-Elo. 1X2 = {md['ph']}/{md['pd']}/{md['pa']}%. "
    if hs == as_:
        return p + f"El marcador más probable es un empate {hs}-{as_} (estrategia que mejor puntuó en backtest)."
    return p + f"Marcador más probable del modelo: {hs}-{as_} (estrategia que mejor puntuó en backtest)."

def model_backtest_params():
    """Backtest de los 12 jugados + parámetros, tal como los calcula model.py (fijo)."""
    import io, contextlib, tempfile
    tmp = os.path.join(tempfile.gettempdir(), "wc_model_tmp.json")
    with contextlib.redirect_stdout(io.StringIO()):
        model.run_report(tmp)
    d = json.load(open(tmp, encoding="utf-8"))
    return d.get("backtest"), d.get("params")

def build_dashboard_data(fixtures, elo, now, path="dashboard/data/model.json"):
    """Genera el JSON que consume el tablero (forma DB: matches[] con predictions[],
    model{}, result{}). Acumula el historial: agrega una predicción cuando el pick cambia."""
    try:
        prev = {str(m.get("fixtureId")): m for m in json.load(open(path, encoding="utf-8")).get("matches", [])}
    except Exception:
        prev = {}
    nb = now.astimezone(BOGOTA)
    today = f"{nb.day} {MES[nb.month]}"   # p.ej. "16 Jun"
    out = []
    for m in sorted(fixtures, key=lambda x: x.get("date") or ""):
        loc, vis = m.get("local") or {}, m.get("visitor") or {}
        hn, vn = loc.get("name"), vis.get("name")
        if not (hn and vn):
            continue
        hk, ak = elo_key(hn), elo_key(vn)
        if hk not in elo or ak not in elo:
            continue  # placeholders/knockout sin equipos
        fid = str(m["fixtureId"])
        hes, ves = es_name(hn), es_name(vn)
        meta = _META.get((hes, ves), {})
        ko = kickoff(m)
        date_lbl = f"{MES[ko.astimezone(BOGOTA).month]} {ko.astimezone(BOGOTA).day}" if ko else ""
        (hs, as_), md = predict(hk, ak, hk in HOSTS, elo)
        hs, as_, osrc = apply_override(m["fixtureId"], hs, as_)

        # historial acumulado: arranca del previo, o se siembra del histórico viejo
        preds = (prev.get(fid) or {}).get("predictions")
        if preds is None:
            preds = list(meta.get("hist", []))
        st = fstate(m)
        if st == "NS":
            if not preds or preds[-1]["hs"] != hs or preds[-1]["as_"] != as_:
                if osrc:
                    preds.append({"stage": f"Override · {osrc}", "date": today, "hs": hs, "as_": as_,
                                  "conf": md["conf"], "type": md["type"],
                                  "reason": f"Marcador forzado manualmente ({osrc})."})
                else:
                    preds.append({"stage": "Mercado + Elo", "date": today, "hs": hs, "as_": as_,
                                  "conf": md["conf"], "type": md["type"], "reason": _reason(hs, as_, md)})
            cur = {"hs": hs, "as_": as_, "conf": md["conf"], "type": md["type"]}
        else:
            # FT/en juego: el pick queda congelado en la última predicción registrada
            last = preds[-1] if preds else {"hs": hs, "as_": as_, "conf": md["conf"], "type": md["type"]}
            cur = {"hs": last["hs"], "as_": last["as_"], "conf": last.get("conf", md["conf"]),
                   "type": last.get("type", md["type"])}

        entry = {
            "fixtureId": m["fixtureId"],
            "gid": _GID.get(hes, (m.get("league") or {}).get("round", "?")),
            "date": date_lbl,
            "venue": meta.get("venue", ""),
            "home": {"name": hes, "flag": _FLAG.get(hes, "🏳️"), **({"debut": True} if _DEBUT.get(hes) else {})},
            "away": {"name": ves, "flag": _FLAG.get(ves, "🏳️"), **({"debut": True} if _DEBUT.get(ves) else {})},
            "note": meta.get("note", ""),
            "predictions": preds,
            "hs": cur["hs"], "as_": cur["as_"], "conf": cur["conf"], "type": cur["type"],
            "model": {"ph": md["ph"], "pd": md["pd"], "pa": md["pa"], "lh": md["lh"], "la": md["la"],
                      "modal": {"hs": md["modal"][0], "as_": md["modal"][1]},
                      "evPick": {"hs": md["evpick"][0], "as_": md["evpick"][1]},
                      "ev": md["ev"], "coin": md["coin"]},
        }
        if st == "FT":
            gh, ga = loc.get("score"), vis.get("score")
            if gh is not None and ga is not None:
                entry["result"] = {"hs": gh, "as_": ga}
        out.append(entry)

    backtest, params = model_backtest_params()
    data = {"matches": out, "backtest": backtest, "params": params, "updated": now.isoformat()}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return len(out)

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

    record, ft_applied, ranking = [], 0, None
    live = not args.from_picks
    if args.from_picks:
        batch, skipped = compute_picks_batch(fixtures, user_id, now, date_filter)
    else:
        elo, ft_applied, skipped_ft = build_updated_elo(fixtures)
        log(f"Elo bayesiano: {ft_applied} partidos FT aplicados"
            + (f"; {len(skipped_ft)} sin equipo Elo (placeholders/knockout)" if skipped_ft else ""))
        _MARKET.update(fetch_market_odds(ODDS_API_KEY))
        log((f"Cuotas de mercado: {len(_MARKET)} partidos mezclados al {int(ODDS_WEIGHT*100)}%"
             if _MARKET else "Cuotas de mercado: no disponibles (solo modelo)"))
        _OVERRIDES.update(load_overrides())
        log((f"Overrides manuales: {len(_OVERRIDES)} partido(s) forzado(s)" if _OVERRIDES
             else "Overrides manuales: ninguno") + "\n")
        batch, record, skipped = compute_live_batch(fixtures, user_id, now, elo, date_filter)
        n_dash = build_dashboard_data(fixtures, elo, now)
        log(f"(tablero actualizado: {n_dash} partidos en dashboard/data/model.json)")
        ranking = fetch_ranking(token, GROUP_ID)
        if ranking and ranking.get("position") is not None:
            log(f"(ranking: puesto {ranking['position']}"
                + (f"/{ranking['total']}" if ranking.get("total") else "")
                + f", {ranking['points']} pts)")
    if record:
        with open("picks_generated.json", "w", encoding="utf-8") as f:
            json.dump({"generado_utc": now.isoformat(), "picks": record}, f, ensure_ascii=False, indent=1)
        log(f"\n(picks_generated.json escrito: {len(record)} picks calculados)")

    if not batch:
        if live: write_html_summary(record, ft_applied, 0, dry, ranking=ranking)
        log(f"\nNada que enviar ({skipped} omitidos)."); return

    log(f"\n{'DRY-RUN — ' if dry else ''}batch de {len(batch)} pronóstico(s).")
    if dry:
        if live: write_html_summary(record, ft_applied, len(batch), dry=True, ranking=ranking)
        log("  " + json.dumps(batch, ensure_ascii=False))
        log("\n(dry-run) POST fixtures/forecasts. Usa --go para enviar."); return

    r = api("POST", "fixtures/forecasts", token, json=batch)
    log(f"POST fixtures/forecasts -> {r.status_code}")
    log("  " + r.text[:300])
    if not r.ok:
        sys.exit("El envío falló.")
    if live: write_html_summary(record, ft_applied, len(batch), dry=False, ranking=ranking)
    log(f"\n{len(batch)} pronóstico(s) enviado(s). ({skipped} omitidos por alcance/sin Elo)")

if __name__ == "__main__":
    main()
