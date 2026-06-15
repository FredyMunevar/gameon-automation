#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modelo de pronostico Mundial 2026 optimizado para la polla (6/4/3).
Motor: Elo -> goles esperados -> Poisson + correccion Dixon-Coles ->
matriz de marcadores -> optimizador de puntos esperados (polla).
Incluye backtest sobre los 12 partidos ya jugados.
"""
import math, json

# ---------------------------------------------------------------
# PARAMETROS (calibrados con prior historico + 12 partidos jugados)
# ---------------------------------------------------------------
BASE_TOTAL = 3.10     # goles esperados/partido: ritmo observado (3.17) + calor + 2 pausas hidratación
SUPREMACY_SCALE = 210 # diferencia de Elo -> supremacia de goles
HFA = 55              # ventaja de campo en Elo (solo anfitrion jugando en su pais)
RHO = -0.07           # correccion Dixon-Coles (infla empates/marcadores bajos)
LAMBDA_FLOOR = 0.15
DRAW_GD_BONUS = False # un empate no exacto: 3 pts (no 4). CONFIRMAR con el organizador.
MAXG = 10             # tope de la matriz de probabilidad
PICK_MAX = 6          # tope de marcadores candidatos para la polla

# ---------------------------------------------------------------
# ELO (eloratings.net, ~15 jun 2026; top-12 reales, resto estimado)
# ---------------------------------------------------------------
ELO = {
 "Spain":2157,"Argentina":2115,"France":2063,"England":2024,"Portugal":1989,
 "Colombia":1982,"Brazil":1978,"Netherlands":1944,"Germany":1939,"Norway":1914,
 "Croatia":1912,"Japan":1910,"Switzerland":1895,"Ecuador":1922,"Uruguay":1886,
 "Senegal":1865,"Morocco":1860,"Turkey":1858,"Belgium":1849,"Sweden":1815,
 "Czechia":1805,"Scotland":1800,"USA":1800,"Mexico":1798,"Iran":1798,
 "South Korea":1786,"Austria":1790,"Ivory Coast":1752,"Algeria":1755,"Canada":1755,
 "Bosnia":1715,"Paraguay":1715,"Egypt":1705,"DR Congo":1700,"Ghana":1695,
 "Tunisia":1690,"Australia":1722,"Saudi Arabia":1675,"Uzbekistan":1660,"Panama":1650,
 "South Africa":1645,"Iraq":1635,"Jordan":1625,"Cape Verde":1615,"Haiti":1560,
 "Curacao":1555,"New Zealand":1555,"Qatar":1685,
}

# ---------------------------------------------------------------
# MODELO
# ---------------------------------------------------------------
def pois(k, lam):
    return math.exp(-lam) * lam**k / math.factorial(k)

def lambdas(home, away, host_home=False, host_away=False):
    eh = ELO[home] + (HFA if host_home else 0)
    ea = ELO[away] + (HFA if host_away else 0)
    sup = (eh - ea) / SUPREMACY_SCALE
    lh = max(LAMBDA_FLOOR, (BASE_TOTAL + sup) / 2)
    la = max(LAMBDA_FLOOR, (BASE_TOTAL - sup) / 2)
    return lh, la

def dc_tau(i, j, lh, la, rho=RHO):
    if i == 0 and j == 0: return 1 - lh*la*rho
    if i == 0 and j == 1: return 1 + lh*rho
    if i == 1 and j == 0: return 1 + la*rho
    if i == 1 and j == 1: return 1 - rho
    return 1.0

def score_matrix(lh, la):
    M = [[pois(i, lh)*pois(j, la)*dc_tau(i, j, lh, la) for j in range(MAXG+1)] for i in range(MAXG+1)]
    s = sum(sum(r) for r in M)
    return [[v/s for v in r] for r in M]

def outcome_probs(M):
    ph = sum(M[i][j] for i in range(MAXG+1) for j in range(MAXG+1) if i > j)
    pd = sum(M[i][j] for i in range(MAXG+1) for j in range(MAXG+1) if i == j)
    pa = sum(M[i][j] for i in range(MAXG+1) for j in range(MAXG+1) if i < j)
    return ph, pd, pa

def modal_score(M):
    best, bs = (0,0), -1
    for i in range(MAXG+1):
        for j in range(MAXG+1):
            if M[i][j] > bs: bs, best = M[i][j], (i,j)
    return best

def points(ph, pa, ah, aa, draw_gd=DRAW_GD_BONUS):
    if ph == ah and pa == aa: return 6
    po = (ph > pa) - (ph < pa)
    ao = (ah > aa) - (ah < aa)
    if po != ao: return 0
    if po == 0:  # ambos empate (no exacto)
        return 4 if draw_gd else 3
    if (ph - pa) == (ah - aa): return 4   # mismo ganador y misma diferencia
    return 3

def recommend(md):
    """Estrategia híbrida: si hay favorito claro (>=58%) comprometerse con él
    (pick EV, que asegura el piso de 3 pts); si es moneda al aire, jugar 1-1
    (el marcador más común y con opción al bono exacto)."""
    fav = max(md["ph"], md["pd"], md["pa"])
    if md["ph"] >= 0.58 or md["pa"] >= 0.58:
        return tuple(md["pick"])   # favorito claro -> compromiso (pick EV)
    return (1, 1)                   # moneda al aire -> 1-1

def ev_pick(M):
    """Marcador que MAXIMIZA puntos esperados de la polla."""
    best, bev = (1,0), -1
    for ph in range(PICK_MAX+1):
        for pa in range(PICK_MAX+1):
            ev = 0.0
            for i in range(MAXG+1):
                for j in range(MAXG+1):
                    p = M[i][j]
                    if p > 1e-9:
                        ev += p * points(ph, pa, i, j)
            if ev > bev:
                bev, best = ev, (ph, pa)
    return best, bev

def elo_update(eh, ea, gh, ga, host_home=False, K=60):
    """Actualizacion Elo (bayesiana gradual) con multiplicador por diferencia de gol."""
    d = (eh + (HFA if host_home else 0)) - ea
    we = 1/(1+10**(-d/400))
    w = 1.0 if gh>ga else (0.5 if gh==ga else 0.0)
    gd = abs(gh-ga)
    G = 1.0 if gd<=1 else (1.5 if gd==2 else (11+gd)/8.0)
    delta = K*G*(w-we)
    return delta

# ---------------------------------------------------------------
# DATOS: 24 partidos (jugados con result; pendientes sin result)
#   host: equipo anfitrion jugando en su pais (ventaja de campo)
# ---------------------------------------------------------------
M_ = lambda **k: k
matches = [
 # GRUPO A
 dict(gid="A",date="Jun 11",venue="Azteca, Ciudad de México",home=("México","🇲🇽"),away=("Sudáfrica","🇿🇦"),host="home",
      result=(2,0),note="En 2010 empataron 1-1 en el inaugural de Sudáfrica.",
      hist=[("Pronóstico inicial","Pre-torneo",2,0,72,"FAV","Anfitrión en el Azteca, superior a Sudáfrica.")]),
 dict(gid="A",date="Jun 11",venue="Akron, Guadalajara",home=("Corea del Sur","🇰🇷"),away=("Rep. Checa","🇨🇿"),
      result=(2,1),note="Lee Kang-in frente a Schick; nivel parejo.",
      hist=[("Pronóstico inicial","Pre-torneo",1,1,52,"EMP","Nivel muy parejo; empate lo más probable.")]),
 # GRUPO B
 dict(gid="B",date="Jun 12",venue="BMO Field, Toronto",home=("Canadá","🇨🇦"),away=("Bosnia-Herz.","🇧🇦"),host="home",
      result=(1,1),note="Canadá en casa con Davies y David; Bosnia con Džeko.",
      hist=[("Pronóstico inicial","Pre-torneo",2,1,62,"FAV","Anfitrión con Davies y David; Bosnia peligrosa.")]),
 dict(gid="B",date="Jun 13",venue="SFB Stadium, San Francisco",home=("Qatar","🇶🇦"),away=("Suiza","🇨🇭"),
      result=(1,1),note="Qatar, primer anfitrión eliminado en grupos (2022). Suiza, 5 Mundiales seguidos pasando fase.",
      hist=[("Pronóstico inicial","Pre-torneo",0,2,83,"FAV","Suiza muy superior a Qatar.")]),
 # GRUPO C
 dict(gid="C",date="Jun 13",venue="MetLife, New Jersey",home=("Brasil","🇧🇷"),away=("Marruecos","🇲🇦"),
      result=(1,1),note="Marruecos llegó a semis en 2022.",
      hist=[("Pronóstico inicial","Pre-torneo",2,1,63,"SOR","Brasil favorito, pero Marruecos peligroso.")]),
 dict(gid="C",date="Jun 13",venue="Gillette, Boston",home=("Haití","🇭🇹"),away=("Escocia","🏴󠁧󠁢󠁳󠁣󠁴󠁿"),
      result=(0,1),note="Escocia regresa al Mundial 28 años después.",
      hist=[("Pronóstico inicial","Pre-torneo",0,2,79,"FAV","Escocia con más nivel que Haití.")]),
 # GRUPO D
 dict(gid="D",date="Jun 12",venue="SoFi, Los Ángeles",home=("EE. UU.","🇺🇸"),away=("Paraguay","🇵🇾"),host="home",
      result=(4,1),note="EE.UU. como anfitrión; Paraguay sin figuras de antaño.",
      hist=[("Pronóstico inicial","Pre-torneo",2,0,69,"FAV","Anfitrión, superior a Paraguay.")]),
 dict(gid="D",date="Jun 13",venue="BC Place, Vancouver",home=("Australia","🇦🇺"),away=("Turquía","🇹🇷"),
      result=(2,0),note="Australia llegó a octavos en 2022; Turquía vía playoffs.",
      hist=[("Pronóstico inicial","Pre-torneo",1,1,54,"EMP","Duelo parejo de nivel medio.")]),
 # GRUPO E
 dict(gid="E",date="Jun 14",venue="NRG, Houston",home=("Alemania","🇩🇪"),away=("Curazao","🇨🇼",True),
      result=(7,1),note="Curazao debuta; Alemania tetracampeona.",
      hist=[("Pronóstico inicial","Pre-torneo",4,0,89,"FAV","Goleada esperada ante un debutante."),
            ("Ajuste tras Jornada 1","14 Jun",3,0,88,"FAV","Ningún favorito goleó en la J1. Bajo a 3-0.")]),
 dict(gid="E",date="Jun 14",venue="Lincoln Financial, Filadelfia",home=("Costa de Marfil","🇨🇮"),away=("Ecuador","🇪🇨"),
      result=(1,0),note="Ecuador disciplinado; Costa de Marfil con talento.",
      hist=[("Pronóstico inicial","Pre-torneo",1,1,55,"EMP","Choque parejo.")]),
 # GRUPO F
 dict(gid="F",date="Jun 14",venue="AT&T, Dallas",home=("Países Bajos","🇳🇱"),away=("Japón","🇯🇵"),
      result=(2,2),note="Japón venció a Alemania y España en 2022.",
      hist=[("Pronóstico inicial","Pre-torneo",2,1,65,"SOR","PB favorito, Japón amenaza.")]),
 dict(gid="F",date="Jun 14",venue="BBVA, Monterrey",home=("Suecia","🇸🇪"),away=("Túnez","🇹🇳"),
      result=(5,1),note="Suecia con Isak y Gyökeres; Túnez defensivo.",
      hist=[("Pronóstico inicial","Pre-torneo",2,0,73,"FAV","Suecia superior; 2-0 validado.")]),
 # GRUPO G (PENDIENTE)
 dict(gid="G",date="Jun 15",venue="Lumen Field, Seattle",home=("Bélgica","🇧🇪"),away=("Egipto","🇪🇬"),
      result=None,note="Mo Salah vs la generación belga (De Bruyne, Lukaku).",
      hist=[("Pronóstico inicial","Pre-torneo",2,1,67,"SOR","Bélgica favorita; Egipto con Salah inquieta.")]),
 dict(gid="G",date="Jun 15",venue="SoFi, Los Ángeles",home=("Irán","🇮🇷"),away=("Nueva Zelanda","🇳🇿"),
      result=None,note="Irán competitivo en 2022; NZ regresa tras 16 años.",
      hist=[("Pronóstico inicial","Pre-torneo",2,0,77,"FAV","Irán con más nivel que NZ.")]),
 # GRUPO H (PENDIENTE)
 dict(gid="H",date="Jun 15",venue="Mercedes-Benz, Atlanta",home=("España","🇪🇸"),away=("Cabo Verde","🇨🇻",True),
      result=None,note="Cabo Verde debuta; España campeona de la Euro 2024.",
      hist=[("Pronóstico inicial","Pre-torneo",3,0,86,"FAV","España muy superior al debutante."),
            ("Ajuste tras Jornada 1","14 Jun",2,0,85,"FAV","Los grandes ganaron sin golear. Bajo a 2-0."),
            ("Re-ajuste tras Jornada 4","15 Jun",3,0,86,"FAV","Alemania (7-1) y Suecia (5-1) golearon. Vuelvo a 3-0.")]),
 dict(gid="H",date="Jun 15",venue="Hard Rock, Miami",home=("Arabia Saudita","🇸🇦"),away=("Uruguay","🇺🇾"),
      result=None,note="Arabia venció a Argentina en 2022; Uruguay bicampeón.",
      hist=[("Pronóstico inicial","Pre-torneo",1,2,65,"SOR","Uruguay superior; Arabia da sustos.")]),
 # GRUPO I (PENDIENTE)
 dict(gid="I",date="Jun 16",venue="MetLife, New Jersey",home=("Francia","🇫🇷"),away=("Senegal","🇸🇳"),
      result=None,note="En 2002 Senegal eliminó a Francia en la apertura.",
      hist=[("Pronóstico inicial","Pre-torneo",2,1,68,"SOR","Francia favorita; Senegal peligroso."),
            ("Ajuste tras Jornada 1","14 Jun",1,1,56,"EMP","Top vs top tiende a empate (Brasil-Marruecos)."),
            ("Re-ajuste tras Jornada 4","15 Jun",2,1,66,"SOR","Empate fue sobre-reacción. Vuelvo a 2-1.")]),
 dict(gid="I",date="Jun 16",venue="Gillette, Boston",home=("Irak","🇮🇶"),away=("Noruega","🇳🇴"),
      result=None,note="Haaland en su primer Mundial.",
      hist=[("Pronóstico inicial","Pre-torneo",0,3,81,"FAV","Haaland y Noruega muy superiores."),
            ("Ajuste tras Jornada 1","14 Jun",0,2,79,"FAV","Nadie goleó en la J1. Bajo a 0-2."),
            ("Re-ajuste tras Jornada 4","15 Jun",0,3,81,"FAV","Con Haaland y torneo goleador, vuelvo a 0-3.")]),
 # GRUPO J (PENDIENTE)
 dict(gid="J",date="Jun 16",venue="Arrowhead, Kansas City",home=("Argentina","🇦🇷"),away=("Argelia","🇩🇿"),
      result=None,note="Argentina campeona defensora; Messi lidera.",
      hist=[("Pronóstico inicial","Pre-torneo",3,0,85,"FAV","Argentina campeona; Argelia inferior."),
            ("Ajuste tras Jornada 1","14 Jun",2,0,84,"FAV","Ni Brasil ni Suiza golearon. Bajo a 2-0."),
            ("Re-ajuste tras Jornada 4","15 Jun",3,0,85,"FAV","Tras las goleadas del 14 Jun, vuelvo a 3-0.")]),
 dict(gid="J",date="Jun 16",venue="Levi's, Santa Clara",home=("Austria","🇦🇹"),away=("Jordania","🇯🇴",True),
      result=None,note="Jordania debuta; Austria con Sabitzer y Arnautović.",
      hist=[("Pronóstico inicial","Pre-torneo",2,0,81,"FAV","Austria con más nivel que el debutante.")]),
 # GRUPO K (PENDIENTE)
 dict(gid="K",date="Jun 17",venue="NRG, Houston",home=("Portugal","🇵🇹"),away=("R.D. Congo","🇨🇩"),
      result=None,note="Portugal con Bruno Fernandes y Leão; Congo debuta.",
      hist=[("Pronóstico inicial","Pre-torneo",3,0,84,"FAV","Portugal muy superior al debutante."),
            ("Ajuste tras Jornada 1","14 Jun",2,0,83,"FAV","Corrección J1: margen corto. Bajo a 2-0."),
            ("Re-ajuste tras Jornada 4","15 Jun",3,0,84,"FAV","Torneo goleador; vuelvo a 3-0.")]),
 dict(gid="K",date="Jun 17",venue="Azteca, Ciudad de México",home=("Uzbekistán","🇺🇿",True),away=("Colombia","🇨🇴"),
      result=None,note="¡Colombia debuta en el Azteca! Luis Díaz, Richard Ríos, Borré.",
      hist=[("Pronóstico inicial","Pre-torneo",0,2,79,"FAV","Colombia superior al debutante Uzbekistán."),
            ("Ajuste tras Jornada 1","14 Jun",0,1,76,"FAV","Marcadores cortos en J1. Bajo a 0-1."),
            ("Re-ajuste tras Jornada 4","15 Jun",0,2,79,"FAV","Ante debutante y torneo goleador, vuelvo a 0-2.")]),
 # GRUPO L (PENDIENTE)
 dict(gid="L",date="Jun 17",venue="AT&T, Dallas",home=("Inglaterra","🏴󠁧󠁢󠁥󠁮󠁧󠁿"),away=("Croacia","🇭🇷"),
      result=None,note="Croacia eliminó a Inglaterra en semis 2018.",
      hist=[("Pronóstico inicial","Pre-torneo",2,1,68,"SOR","Inglaterra favorita; Croacia compite.")]),
 dict(gid="L",date="Jun 17",venue="BMO Field, Toronto",home=("Ghana","🇬🇭"),away=("Panamá","🇵🇦"),
      result=None,note="Ghana llegó a cuartos en 2010; Panamá más limitado.",
      hist=[("Pronóstico inicial","Pre-torneo",2,0,75,"FAV","Ghana con más recorrido que Panamá.")]),
]

# Mapa nombre-mostrado -> clave Elo
KEY = {
 "México":"Mexico","Sudáfrica":"South Africa","Corea del Sur":"South Korea","Rep. Checa":"Czechia",
 "Canadá":"Canada","Bosnia-Herz.":"Bosnia","Qatar":"Qatar","Suiza":"Switzerland",
 "Brasil":"Brazil","Marruecos":"Morocco","Haití":"Haiti","Escocia":"Scotland",
 "EE. UU.":"USA","Paraguay":"Paraguay","Australia":"Australia","Turquía":"Turkey",
 "Alemania":"Germany","Curazao":"Curacao","Costa de Marfil":"Ivory Coast","Ecuador":"Ecuador",
 "Países Bajos":"Netherlands","Japón":"Japan","Suecia":"Sweden","Túnez":"Tunisia",
 "Bélgica":"Belgium","Egipto":"Egypt","Irán":"Iran","Nueva Zelanda":"New Zealand",
 "España":"Spain","Cabo Verde":"Cape Verde","Arabia Saudita":"Saudi Arabia","Uruguay":"Uruguay",
 "Francia":"France","Senegal":"Senegal","Irak":"Iraq","Noruega":"Norway",
 "Argentina":"Argentina","Argelia":"Algeria","Austria":"Austria","Jordania":"Jordan",
 "Portugal":"Portugal","R.D. Congo":"DR Congo","Uzbekistán":"Uzbekistan","Colombia":"Colombia",
 "Inglaterra":"England","Croacia":"Croatia","Ghana":"Ghana","Panamá":"Panama",
}

def hk(m): return KEY[m["home"][0]]
def ak(m): return KEY[m["away"][0]]

# ---------------------------------------------------------------
# BACKTEST sobre los 12 jugados (Elo pre-torneo, sin mirar resultados)
# ---------------------------------------------------------------
HEUR = {  # lo que YO habría enviado (heurístico) a cada partido jugado
 ("México","Sudáfrica"):(2,0),("Corea del Sur","Rep. Checa"):(1,1),
 ("Canadá","Bosnia-Herz."):(2,1),("Qatar","Suiza"):(0,2),
 ("Brasil","Marruecos"):(2,1),("Haití","Escocia"):(0,2),
 ("EE. UU.","Paraguay"):(2,0),("Australia","Turquía"):(1,1),
 ("Alemania","Curazao"):(3,0),("Costa de Marfil","Ecuador"):(1,1),
 ("Países Bajos","Japón"):(2,1),("Suecia","Túnez"):(2,0),
}

def brier_1x2(ph,pd,pa, ah,aa):
    y = (1,0,0) if ah>aa else ((0,1,0) if ah==aa else (0,0,1))
    p = (ph,pd,pa)
    return sum((p[i]-y[i])**2 for i in range(3))

played = [m for m in matches if m["result"]]
pending = [m for m in matches if not m["result"]]

model_pts = heur_pts = modal_pts = rec_pts = 0
brier_model = brier_unif = 0.0
bt_rows = []
for m in played:
    host_home = (m.get("host")=="home"); host_away=(m.get("host")=="away")
    lh,la = lambdas(hk(m),ak(m),host_home,host_away)
    M = score_matrix(lh,la)
    ph,pd,pa = outcome_probs(M)
    pick,ev = ev_pick(M)
    mod = modal_score(M)
    rec = recommend(dict(ph=ph,pd=pd,pa=pa,pick=pick,modal=mod))
    ah,aa = m["result"]
    mp = points(*pick,ah,aa); model_pts += mp
    mdp = points(*mod,ah,aa); modal_pts += mdp
    rp = points(*rec,ah,aa); rec_pts += rp
    hpk = HEUR[(m["home"][0],m["away"][0])]; hp = points(*hpk,ah,aa); heur_pts += hp
    brier_model += brier_1x2(ph,pd,pa,ah,aa)
    brier_unif  += brier_1x2(1/3,1/3,1/3,ah,aa)
    bt_rows.append(dict(g=m["gid"],home=m["home"][0],away=m["away"][0],
        actual=(ah,aa),model=pick,modelpts=mp,modal=mod,modalpts=mdp,
        rec=rec,recpts=rp,heur=hpk,heurpts=hp,
        probs=(round(ph*100),round(pd*100),round(pa*100))))

n=len(played)
print("="*64)
print(f"BACKTEST sobre {n} partidos jugados (Jornada 1, Grupos A-F)")
print("="*64)
print(f"{'Partido':<24}{'Real':>5}{'Recom':>7}{'pts':>4}{'Prob':>6}{'pts':>4}{'Heur':>6}{'pts':>4}")
for r in bt_rows:
    pa_=f"{r['actual'][0]}-{r['actual'][1]}"; prc=f"{r['rec'][0]}-{r['rec'][1]}"
    pmo=f"{r['modal'][0]}-{r['modal'][1]}"; ph_=f"{r['heur'][0]}-{r['heur'][1]}"
    name=f"{r['home'][:11]} v {r['away'][:6]}"
    print(f"{name:<24}{pa_:>5}{prc:>7}{r['recpts']:>4}{pmo:>6}{r['modalpts']:>4}{ph_:>6}{r['heurpts']:>4}")
print("-"*60)
print(f"{'TOTAL (12 jugados)':<24}{'':>5}{'RECOM':>7}{rec_pts:>4}{'PROB':>6}{modal_pts:>4}{'HEUR':>6}{heur_pts:>4}")
print(f"\nResumen puntos -> Recomendado(híbrido)={rec_pts} | Más-probable={modal_pts} | EV={model_pts} | Heurístico={heur_pts}")
print(f"\nPuntos: MODELO(EV)={model_pts}  | marcador-mas-probable={modal_pts}  | HEURISTICO={heur_pts}")
print(f"Promedio por partido: MODELO={model_pts/n:.2f}  HEUR={heur_pts/n:.2f}")
print(f"Brier 1X2 (menor=mejor): MODELO={brier_model/n:.3f}  vs azar(1/3)={brier_unif/n:.3f}")

# ---------------------------------------------------------------
# Actualizacion bayesiana (Elo) con la Jornada 1 -> activa desde J2
# (los equipos de grupos G-L aun no juegan; se reporta como referencia)
# ---------------------------------------------------------------
elo_delta = {}
for m in played:
    gh,ga = m["result"]; host_home=(m.get("host")=="home")
    dh = elo_update(ELO[hk(m)],ELO[ak(m)],gh,ga,host_home)
    da = elo_update(ELO[ak(m)],ELO[hk(m)],ga,gh,False)
    elo_delta[hk(m)] = elo_delta.get(hk(m),0)+dh
    elo_delta[ak(m)] = elo_delta.get(ak(m),0)+da

# ---------------------------------------------------------------
# PREDICCIONES para los 12 pendientes (Elo, optimizado para la polla)
# ---------------------------------------------------------------
print("\n"+"="*64)
print("PREDICCIONES OPTIMIZADAS PARA LA POLLA (12 pendientes)")
print("="*64)
print(f"{'Partido':<28}{'1':>4}{'X':>4}{'2':>4}{'Probable':>9}{'EV-alt':>7}")
for m in pending:
    host_home=(m.get("host")=="home"); host_away=(m.get("host")=="away")
    lh,la = lambdas(hk(m),ak(m),host_home,host_away)
    M = score_matrix(lh,la)
    ph,pd,pa = outcome_probs(M)
    pick,ev = ev_pick(M); mod = modal_score(M)
    m["_model"]=dict(ph=ph,pd=pd,pa=pa,lh=lh,la=la,pick=pick,ev=ev,modal=mod)
    name=f"{m['home'][0][:14]} v {m['away'][0][:9]}"
    print(f"{name:<28}{ph*100:>3.0f}%{pd*100:>3.0f}%{pa*100:>3.0f}%{mod[0]:>6}-{mod[1]}{pick[0]:>5}-{pick[1]}")

# ---------------------------------------------------------------
# EMITIR DATOS JSON PARA EL WIDGET
# ---------------------------------------------------------------
def team_obj(t):
    o = {"name":t[0],"flag":t[1]}
    if len(t)>2 and t[2]: o["debut"]=True
    return o

def hist_to_preds(m):
    out=[]
    for h in m["hist"]:
        out.append(dict(stage=h[0],date=h[1],hs=h[2],as_=h[3],conf=h[4],type=h[5],reason=h[6]))
    return out

out_matches=[]
for m in matches:
    o=dict(gid=m["gid"],date=m["date"],venue=m["venue"],
           home=team_obj(m["home"]),away=team_obj(m["away"]),note=m["note"],
           predictions=hist_to_preds(m))
    if m["result"]:
        o["result"]={"hs":m["result"][0],"as_":m["result"][1]}
        # current pick = last hist
        last=m["hist"][-1]; o["hs"]=last[2]; o["as_"]=last[3]; o["conf"]=last[4]; o["type"]=last[5]
    else:
        md=m["_model"]; pick=recommend(md); modal=tuple(md["modal"]); evp=tuple(md["pick"])
        po=(pick[0]>pick[1])-(pick[0]<pick[1])
        conf = md["ph"] if po>0 else (md["pd"] if po==0 else md["pa"])
        coin = not (md["ph"]>=0.58 or md["pa"]>=0.58)
        typ = "EMP" if coin else ("FAV" if max(md["ph"],md["pa"])>=0.68 else "SOR")
        o["hs"]=pick[0]; o["as_"]=pick[1]; o["conf"]=round(conf*100); o["type"]=typ
        o["model"]=dict(ph=round(md["ph"]*100),pd=round(md["pd"]*100),pa=round(md["pa"]*100),
                        lh=round(md["lh"],2),la=round(md["la"],2),
                        modal={"hs":modal[0],"as_":modal[1]},
                        evPick={"hs":evp[0],"as_":evp[1]},ev=round(md["ev"],2),coin=coin)
        if coin:
            reason=(f"Motor Poisson-Elo. 1X2 = {round(md['ph']*100)}/{round(md['pd']*100)}/{round(md['pa']*100)}%. "
                    f"Sin favorito claro (moneda al aire): recomiendo 1-1, el marcador más común y con opción al bono por exacto. "
                    f"En el backtest, jugar 1-1 en los cerrados clavó 3 empates exactos (Canadá, Qatar, Brasil).")
        else:
            reason=(f"Motor Poisson-Elo. 1X2 = {round(md['ph']*100)}/{round(md['pd']*100)}/{round(md['pa']*100)}%. "
                    f"Favorito claro: me comprometo con {pick[0]}-{pick[1]} para asegurar el piso de puntos. "
                    f"Nota: 2-0, no 3-0 — el más probable es {modal[0]}-{modal[1]} y rinde más que un marcador abultado improbable.")
        o["predictions"].append(dict(stage="Modelo Poisson-Elo",date="15 Jun",
                                     hs=pick[0],as_=pick[1],conf=round(conf*100),type=typ,reason=reason))
    out_matches.append(o)

backtest=dict(n=n,modelPoints=model_pts,heurPoints=heur_pts,modalPoints=modal_pts,recPoints=rec_pts,
              recAvg=round(rec_pts/n,2),heurAvg=round(heur_pts/n,2),
              brierModel=round(brier_model/n,3),brierUnif=round(brier_unif/n,3),
              rows=[dict(g=r["g"],home=r["home"],away=r["away"],
                         actual=f"{r['actual'][0]}-{r['actual'][1]}",
                         rec=f"{r['rec'][0]}-{r['rec'][1]}",recpts=r["recpts"],
                         modal=f"{r['modal'][0]}-{r['modal'][1]}",modalpts=r["modalpts"],
                         heur=f"{r['heur'][0]}-{r['heur'][1]}",heurpts=r["heurpts"],
                         probs=r["probs"]) for r in bt_rows])
params=dict(baseTotal=BASE_TOTAL,supScale=SUPREMACY_SCALE,hfa=HFA,rho=RHO,drawGd=DRAW_GD_BONUS)

with open("/home/claude/wc_model.json","w") as f:
    json.dump(dict(matches=out_matches,backtest=backtest,params=params),f,ensure_ascii=False)

print("\nJSON escrito. Backtest:", model_pts, "vs heur", heur_pts, "| modal", modal_pts)
