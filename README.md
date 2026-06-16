# GameOn — Automatización de pronósticos (Mundial 2026)

Envía **mis pronósticos** a la app [AppGameOn](https://apiv2.appgameon.com/) de forma autónoma, todos los días, **en la nube** (GitHub Actions) — sin emulador ni mi Mac encendida.

Es una competencia entre amigos de "quién predice mejor usando IA" (sin dinero). Cada mañana el sistema lee los resultados ya jugados, actualiza un modelo Elo bayesiano, re-predice los partidos que faltan y deja puestos los marcadores antes del cierre.

---

## Cómo funciona (lazo diario)

Cada corrida de [`submit_gameon.py`](submit_gameon.py) (modo por defecto, *modelo vivo*):

1. **Login** — Firebase Auth REST (email/clave) → `idToken` (header `Authorization: Bearer`).
2. **Lee el calendario** — `GET fixtures/groups/{GROUP_ID}` → fixtures con resultados (FT) y estados.
3. **Actualiza el Elo bayesiano ACUMULADO** con *todos* los partidos jugados (FT), en orden cronológico.
4. **Re-predice TODOS los partidos NS** (no empezados) con el motor de [`model.py`](model.py): Poisson-Elo + corrección Dixon-Coles → matriz de marcadores → pick óptimo para el puntaje **6 exacto / 4 ganador+dif / 3 resultado**.
5. **Envía/edita** los picks vía `POST fixtures/forecasts` (endpoint batch).

```
Login OK → Elo bayesiano: N partidos FT aplicados → batch de M → POST fixtures/forecasts → 200
```

### Regla dura de alcance (no negociable)

Solo se envían picks de partidos que **NO han empezado** (`state == "NS"`) y con **más de 5 minutos** para el saque. El gate usa el **estado real** del fixture que devuelve la API, **no** una etiqueta de fecha. Nunca se envían partidos en curso/terminados ni se falsean timestamps. Re-correr es idempotente: sobrescribe con el pick más reciente. Por eso la corrida es **matutina**, con horas de margen.

---

## El modelo ([`model.py`](model.py))

- **Motor:** Elo → goles esperados → Poisson + corrección Dixon-Coles (ρ) → matriz de marcadores → optimizador de puntos esperados de la polla.
- **Actualización bayesiana del Elo:** `Δ = K · G · (resultado_real − esperado)`, con `K=60` (valor de eloratings.net para fase final de Mundial: el rating reacciona rápido), `G` = multiplicador por diferencia de goles. Se aplica acumulada desde la Jornada 2.
- **Ventaja de localía (HFA):** +55 Elo para anfitriones jugando en casa (México, USA, Canadá).
- **Pick híbrido:** favorito claro (≥58%) → marcador EV (asegura el piso); moneda al aire → 1-1.
- Corriendo `python3 model.py` (standalone) imprime el backtest y escribe `wc_model.json` (datos para un widget). Como módulo importable, expone solo el motor (constantes + funciones), sin efectos.

---

## Archivos

| Archivo | Qué es |
|---|---|
| [`submit_gameon.py`](submit_gameon.py) | Cliente de la API: login + modelo vivo + envío. Modo respaldo `--from-picks`. |
| [`model.py`](model.py) | Motor Elo/Poisson + backtest (importable). |
| [`picks.json`](picks.json) | Picks estáticos (respaldo del modo `--from-picks`). |
| [`.github/workflows/polla.yml`](.github/workflows/polla.yml) | GitHub Actions, cron diario. |
| `.env` | Credenciales locales (gitignored, **nunca** se versiona). |
| `wc_model.json`, `picks_generated.json` | Artefactos generados (gitignored). |

---

## Uso local

```bash
pip install requests
cp .env.example .env          # rellena GAMEON_EMAIL y GAMEON_PASSWORD
set -a; . ./.env; set +a      # carga las variables
export GAMEON_GROUP_ID=32534

python3 submit_gameon.py --probe        # login + estructura de la API
python3 submit_gameon.py                # dry-run del modelo vivo (todos los NS)
python3 submit_gameon.py --go           # envía de verdad
python3 submit_gameon.py --today        # dry-run, solo los NS que sacan hoy (Bogotá)
python3 submit_gameon.py --from-picks --go  # envía picks.json estático
```

Por defecto es **dry-run**; `--go` envía de verdad.

---

## Despliegue en la nube (GitHub Actions)

Corre solo vía cron. El workflow está en [`.github/workflows/polla.yml`](.github/workflows/polla.yml):

- **Cron:** `0 13 * * *` (UTC) = **08:00 Bogotá**, todos los días. También se puede disparar a mano (*workflow_dispatch*).
- **Secrets del repo** (Settings → Secrets and variables → Actions):

| Secret | Valor |
|---|---|
| `FIREBASE_API_KEY` | la `google_api_key` del APK (no es secreta, pero va por secret) |
| `GAMEON_EMAIL` | mi correo de GameOn |
| `GAMEON_PASSWORD` | mi contraseña (**secreto**) |
| `GAMEON_GROUP_ID` | `32534` (la polla del Mundial 2026) |

Disparar a mano y ver el resultado:

```bash
gh workflow run "Enviar picks polla"
gh run watch
```

**Pausar/apagar** (p. ej. al terminar el torneo): Actions → "Enviar picks polla" → `···` → *Disable workflow*, o `gh workflow disable "Enviar picks polla"`.

---

## Notas de la API (de decompilar el APK)

- **Base:** `https://apiv2.appgameon.com/` · package `com.appgameon.ml` · datos de fútbol vía SportMonks.
- **Auth:** Firebase ID token (`signInWithPassword` REST). El token expira ~1h; cada corrida hace login fresco.
- **Envío (confirmado en la interfaz Retrofit):** `POST fixtures/forecasts`, body = **array** de `{fixtureId, localScore, visitorScore, userId}` (no lleva groupId). Devuelve `List<Integer>`.
- **Mi userId:** `229455` · **groupId:** `32534`.

---

## Seguridad

- Credenciales **solo** por variables de entorno / GitHub secrets. Nunca en el código ni en el repo.
- `.env` y el código decompilado del APK están en `.gitignore`.
