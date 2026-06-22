#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Convierte una señal de BetAlpha al marcador MÁS PROBABLE (modal), sin inflarlo.
Regla acordada: seguir el ganador/under de BetAlpha, pero dejar el marcador en el
más probable (no en uno abultado). Así maximizamos el bono por exacto.

USO (cualquiera de las dos formas):
  # 1) si BetAlpha da goles esperados por equipo ("Ivory Coast 0.6 - 1.7 Germany"):
  python3 ba_pick.py --home-xg 1.7 --away-xg 0.6

  # 2) si da Total + favorito por margen (hándicap):
  python3 ba_pick.py --total 2.0 --fav home --margin 1.0     # local favorito por ~1
  python3 ba_pick.py --total 2.2 --fav away --margin 0.5     # visitante favorito por ~0.5

El resultado (marcador local-visitante) es el que se mete en el override del tablero.
"""
import argparse
import model  # motor Poisson + Dixon-Coles

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--total", type=float, help="goles totales esperados (μ de BetAlpha)")
    ap.add_argument("--margin", type=float, default=0.0, help="margen del favorito (hándicap)")
    ap.add_argument("--fav", choices=["home", "away"], default="home", help="quién es favorito")
    ap.add_argument("--home-xg", type=float, help="goles esperados del local")
    ap.add_argument("--away-xg", type=float, help="goles esperados del visitante")
    a = ap.parse_args()

    if a.home_xg is not None and a.away_xg is not None:
        lh, la = a.home_xg, a.away_xg
    elif a.total is not None:
        h = abs(a.margin)
        lh, la = ((a.total + h) / 2, (a.total - h) / 2) if a.fav == "home" else ((a.total - h) / 2, (a.total + h) / 2)
    else:
        ap.error("Da --home-xg/--away-xg, o --total (+ --fav/--margin).")

    lh, la = max(0.15, lh), max(0.15, la)
    M = model.score_matrix(lh, la)
    mod = model.modal_score(M)
    cells = sorted(((M[i][j], i, j) for i in range(7) for j in range(7)), reverse=True)[:5]
    print(f"λ  local {lh:.2f}  -  visitante {la:.2f}")
    print(f"→ Marcador más probable (modal):  {mod[0]}-{mod[1]}")
    print("Top 5 marcadores:")
    for pr, i, j in cells:
        print(f"   {i}-{j} : {pr*100:.1f}%")

if __name__ == "__main__":
    main()
