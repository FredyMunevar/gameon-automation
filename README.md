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
- **Pick = marcador más probable (modal):** la estrategia que mejor puntuó en backtest (45 vs 40 del híbrido vs 28 del EV, sobre 20 jugados; robusta a `BASE_TOTAL`/`RHO`). Configurable en `submit_gameon.py` (`PICK_STRATEGY`: `modal` | `hybrid` | `ev`).
- **Mezcla con cuotas de mercado:** si hay `ODDS_API_KEY` ([the-odds-api.com](https://the-odds-api.com)), cada corrida trae 3 mercados del Mundial y los promedia de-vigados entre casas: **1X2** (quién gana), **totales O/U 2.5** → goles totales esperados (μ), y **hándicap** → supremacía (diferencia de goles). Con μ y supremacía del mercado fija los goles esperados de cada equipo (λ) — **con el mercado al mando** vía `ODDS_WEIGHT` (90% por defecto; el Elo solo matiza o sirve de respaldo cuando no hay cuotas) — y de ahí salen el marcador (modal) y el 1X2. Así el mercado mueve el *marcador*, no solo la probabilidad. El mercado ya incorpora lesiones, forma y viajes (enfoque de apps como BetAlpha). Si no hay key o falla, usa solo el modelo (*fallback*).
- Corriendo `python3 model.py` (standalone) imprime el backtest y escribe `wc_model.json` (datos para un widget). Como módulo importable, expone solo el motor (constantes + funciones), sin efectos.

---

## Archivos

| Archivo | Qué es |
|---|---|
| [`submit_gameon.py`](submit_gameon.py) | Cliente de la API: login + modelo vivo + envío + historial. Modo respaldo `--from-picks`. |
| [`model.py`](model.py) | Motor Elo/Poisson + backtest (importable). |
| [`picks.json`](picks.json) | Picks estáticos (respaldo del modo `--from-picks`). |
| [`dashboard/`](dashboard) | App Next.js del tablero web (se despliega en Vercel). |
| `dashboard/data/model.json` | Datos del tablero (matches + historial + backtest); lo actualiza y commitea el workflow. |
| [`.github/workflows/polla.yml`](.github/workflows/polla.yml) | GitHub Actions, cron diario. |
| `.env` | Credenciales locales (gitignored, **nunca** se versiona). |
| `wc_model.json`, `picks_generated.json`, `summary.html` | Artefactos generados (gitignored). |

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

El workflow está en [`.github/workflows/polla.yml`](.github/workflows/polla.yml) y se dispara por `workflow_dispatch`.

- **Disparo diario:** lo hace **Vercel Cron** (más fiable que el `schedule` de GitHub Actions, que se retrasaba/omitía). El tablero expone [`/api/cron`](dashboard/app/api/cron/route.js) que llama a la API de GitHub (`workflow_dispatch`); `dashboard/vercel.json` lo programa a las `17 13 * * *` UTC ≈ **08:17 Bogotá**. También se puede disparar a mano desde la pestaña Actions o con `gh workflow run "Enviar picks polla"`.
  - Requiere en el proyecto de Vercel: env `GH_DISPATCH_TOKEN` (PAT fine-grained con *Actions: Read & Write* sobre el repo) y `CRON_SECRET` (cadena aleatoria; Vercel la envía como `Authorization: Bearer` y la ruta la valida).
- **Secrets del repo** (Settings → Secrets and variables → Actions):

| Secret | Valor |
|---|---|
| `FIREBASE_API_KEY` | la `google_api_key` del APK (no es secreta, pero va por secret) |
| `GAMEON_EMAIL` | mi correo de GameOn |
| `GAMEON_PASSWORD` | mi contraseña (**secreto**) |
| `GAMEON_GROUP_ID` | `32534` (la polla del Mundial 2026) |
| `ODDS_API_KEY` | key de [the-odds-api.com](https://the-odds-api.com) para mezclar cuotas de mercado (opcional) |

Disparar a mano y ver el resultado:

```bash
gh workflow run "Enviar picks polla"
gh run watch
```

**Pausar/apagar** (p. ej. al terminar el torneo): Actions → "Enviar picks polla" → `···` → *Disable workflow*, o `gh workflow disable "Enviar picks polla"`.

### Notificación por correo

Al terminar cada corrida (corra bien o **falle**), el workflow envía un correo con un **resumen HTML** legible: tu **posición en el ranking y puntos** (de `GET groups` → `userRanking`, con flecha de movimiento ▲/▼), conteo de picks, partidos usados para el Elo, y una tabla agrupada por día con cada partido, su marcador, probabilidad 1X2, tipo (Favorito/Inclinado/Parejo) y hora de Bogotá. El HTML lo genera `submit_gameon.py` (`summary.html`); si la corrida falla, el correo trae el log completo. Usa [`dawidd6/action-send-mail`](https://github.com/dawidd6/action-send-mail) vía SMTP. Secrets necesarios:

| Secret | Ejemplo |
|---|---|
| `MAIL_SERVER` | `smtp.gmail.com` |
| `MAIL_PORT` | `465` |
| `MAIL_USERNAME` | mi correo (usuario SMTP) |
| `MAIL_PASSWORD` | **app password** del correo (no la clave normal) |
| `MAIL_TO` | destinatario del aviso |

---

## Tablero web (Vercel)

[`dashboard/`](dashboard) es una app **Next.js** (App Router) que muestra, desde cualquier dispositivo: tarjetas por partido con banderas y barra de probabilidad 1X2, tabs por grupo, un resumen con aciertos, el backtest del modelo, y un **modal por partido con la línea de tiempo "Historial de predicciones"** (cada etapa con su razón) + resultado y puntos (6/4/3). Lee `dashboard/data/model.json` (forma `{matches[], backtest, params}`, con `predictions[]`, `model{}` y `result{}` por partido).

- **Datos:** cada corrida del workflow regenera `dashboard/data/model.json` (acumula el historial: agrega una predicción cuando el pick cambia; siembra el histórico viejo de `model.py`; registra resultados al terminar) y lo **commitea** al repo. Vercel redespliega solo en cada push → el tablero queda al día.
- **Despliegue en Vercel:** proyecto con **Root Directory = `dashboard`**, framework Next.js (autodetectado). Sin variables de entorno (lee un archivo del repo). Apuntar el subdominio deseado.
- **Botón "Actualizar ahora":** el tablero tiene un botón (protegido por un PIN) para disparar el envío a mano desde cualquier dispositivo, sin entrar a GitHub. Usa la ruta [`/api/trigger`](dashboard/app/api/trigger/route.js). Requiere en Vercel la env `TRIGGER_PIN` (el código que eliges) y `GH_DISPATCH_TOKEN`.
- **Override manual (BetAlpha):** en el modal de cada partido sin empezar puedes **forzar un marcador** (con el mismo PIN). Lo guarda en `overrides.json` del repo vía [`/api/override`](dashboard/app/api/override/route.js) y dispara la corrida; `submit_gameon.py` usa ese marcador en vez del modelo para ese partido (y lo etiqueta en el historial). "Quitar" lo elimina. Útil para los partidos donde confías en BetAlpha.
- **Última actualización:** el tablero muestra la fecha/hora (Bogotá) de la última corrida (campo `updated` de `model.json`).
- **Local:** `cd dashboard && npm install && npm run dev` → http://localhost:3000

## Notas de la API (de decompilar el APK)

- **Base:** `https://apiv2.appgameon.com/` · package `com.appgameon.ml` · datos de fútbol vía SportMonks.
- **Auth:** Firebase ID token (`signInWithPassword` REST). El token expira ~1h; cada corrida hace login fresco.
- **Envío (confirmado en la interfaz Retrofit):** `POST fixtures/forecasts`, body = **array** de `{fixtureId, localScore, visitorScore, userId}` (no lleva groupId). Devuelve `List<Integer>`.
- **Mi userId:** `229455` · **groupId:** `32534`.

---

## Seguridad

- Credenciales **solo** por variables de entorno / GitHub secrets. Nunca en el código ni en el repo.
- `.env` y el código decompilado del APK están en `.gitignore`.
