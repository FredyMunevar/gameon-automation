# GameOn — Automatización de pronósticos · Handoff para Claude Code

> Contexto portátil para continuar este proyecto en Claude Code. Reúne todo lo recopilado:
> hallazgos de la API (de decompilar el APK), lo ya construido, lo que falta y los comandos exactos.

---

## 1. Objetivo y ALCANCE (leer primero)

Automatizar el envío de **mis propios pronósticos** (los que genera mi modelo) a la app **AppGameOn**,
**antes del cierre** de cada partido, corriendo **en la nube** (sin emulador, sin mi Mac encendido).

Es una competencia entre amigos de "quién predice mejor usando IA" (sin dinero de por medio).

**Regla dura del proyecto (no negociable):** enviar **solo picks generados ANTES del partido**.
- NO saltarse el cierre (la app permite editar hasta 5 min antes de cada partido).
- NO enviar marcadores ya conocidos / en curso, NO falsear timestamps, NO disfrazar envíos.
- Patrón correcto: **una corrida en la mañana** que deja puestos todos los picks del día, con horas de margen.

---

## 2. Estado actual (lo que YA está hecho)

- **Modelo** `model.py`: Poisson-Elo + corrección Dixon-Coles → matriz de marcadores → pick optimizado
  para el puntaje **6 exacto / 4 ganador+dif / 3 resultado**. Incluye actualización bayesiana del Elo
  (se activa desde la Jornada 2). Backtest sobre 12 partidos jugados: ~+40% de puntos vs el método "a ojo".
- **Picks** `picks.json`: 12 pendientes + 12 jugados (Jornada 1, Mundial 2026). Estructura por pick:
  `{grupo, fecha "Jun 15", local, visitante, pick_local, pick_visitante, confianza_%, tipo, estado, ...}`.
- **Cliente de API** `submit_gameon.py`: login Firebase REST + modo `--probe` + envío (este último, templado).
- **CI** `polla.yml`: workflow de GitHub Actions con cron diario (va en `.github/workflows/`).

---

## 3. Hallazgos de la API (de jadx — NO hay que repetir la decompilación)

APK ya decompilado en: `/Users/mune/Desktop/gameon/jadx-out/`  (sources/ y resources/).

- **App:** AppGameOn — package `com.appgameon.ml`.
- **API base:** `https://apiv2.appgameon.com/`  (es el valor `API_URL` en `Y0/u.java`).
- **Auth:** Firebase **ID token** como header `Authorization: Bearer <idToken>`.
  - Confirmado en `jadx-out/sources/U3/C1936b.java` (interceptor OkHttp que añade el Bearer).
- **Login:** Firebase Auth **email/clave** (`signInWithEmailAndPassword` presente) → replicable por REST:
  ```
  POST https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=<FIREBASE_API_KEY>
  body: {"email": "...", "password": "...", "returnSecureToken": true}
  → respuesta incluye "idToken" (válido ~1h)
  ```
  (También hay Google/Play Games sign-in como alternativa.)
- **Firebase / config** (en `jadx-out/resources/res/values/strings.xml`):
  - `project_id = gameon-chat`
  - `google_app_id = 1:747765654073:android:...`
  - `google_api_key = AIzaSy...`  ← **léelo del strings.xml**. NO es secreto (viene en todo APK;
    la seguridad de Firebase es por Auth + Security Rules), pero úsalo por variable de entorno igual.
  - `firebase_database_url = https://gameon-chat.firebaseio.com` (Realtime DB; es para el chat).
- **Play Integrity / attestation:** **NO** parece gatear la API. Las coincidencias de "attestation"
  son de **AdMob** (`gads:gma_attestation:*`) y **WebAuthn/FIDO** (passkeys), no firman las peticiones.
  → La vía 100% nube es viable.
- **Endpoints (paths Retrofit) relevantes:**
  ```
  GET  users/me
  GET  users/me/stats
  GET  matches/calendar              GET  matches/calendar/home
  GET  matches/users/
  GET  fixtures/date/{date}          GET  fixtures/{matchId}
  GET  fixtures/forecasts
  POST groups/{groupId}/fixtures/{fixtureId}/forecasts   ← CANDIDATO principal de envío
       (otros vistos: fixtures/groups/{groupId}/users/{userId},
        matches/{...}/groups/{groupId}/forecasts/, leagues/standings/..., notifications/...)
  ```
- **Datos de fútbol:** la app usa SportMonks (sus fixtures vienen de ahí; los `fixtureId` son de SportMonks).

---

## 4. Lo que FALTA (tareas para Claude Code, en orden)

1. **Confirmar login en la nube:** correr `python3 submit_gameon.py --probe` con las env vars puestas.
   Debe imprimir `Login OK`. Si la cuenta entra solo con Google (no email/clave), `signInWithPassword`
   fallará → opciones: añadir contraseña a la cuenta desde la app, o capturar el flujo de Google (más complejo).
2. **Del output del `--probe`, extraer:**
   - `groupId` de la liga del usuario (de `matches/users/` o `users/me`).
   - estructura de un *fixture* (su `id` + nombres de equipos) en `matches/calendar` o `fixtures/forecasts`.
3. **Confirmar método y body EXACTOS del envío** leyendo la interfaz Retrofit:
   ```bash
   cd /Users/mune/Desktop/gameon
   grep -rEl 'forecasts' jadx-out/sources --include='*.java'
   grep -rEi -B2 -A2 '@(POST|PUT).*forecast' jadx-out/sources --include='*.java' | head -40
   # abrir la interfaz con @POST/@PUT/@Body y el data class del body
   ```
4. **Finalizar `submit_forecast()`** en `submit_gameon.py`: endpoint real, método y nombres reales del body
   (el candidato actual asume `POST groups/{groupId}/fixtures/{fixtureId}/forecasts` y body `{homeScore, awayScore}`).
5. **Implementar el mapeo `nombre_equipo → fixture_id`** usando `matches/calendar` (casar por nombre y fecha),
   y añadir el `fixture_id` resuelto a cada pick antes de enviar.
6. **Probar:** `--today` (dry-run) y luego `--today --go` con **un solo partido** primero para validar.
7. **Desplegar en la nube:** repo privado en GitHub + `polla.yml` en `.github/workflows/` + secrets (ver §5).
   Cron a `0 13 * * *` (08:00 Bogotá = 13:00 UTC); ajustar a la hora del primer partido del día.

---

## 5. Credenciales — por variables de entorno / GitHub secrets (NUNCA en el código)

| Variable            | Qué es                                   | ¿Secreto? |
|---------------------|------------------------------------------|-----------|
| `FIREBASE_API_KEY`  | la `google_api_key` del APK              | No (pero va por env) |
| `GAMEON_EMAIL`      | correo de la cuenta GameOn               | —         |
| `GAMEON_PASSWORD`   | contraseña de la cuenta                  | **Sí**    |
| `GAMEON_GROUP_ID`   | id de la liga/grupo (del `--probe`)      | No        |

En GitHub: Settings → Secrets and variables → Actions → New repository secret (uno por cada variable).

---

## 6. Archivos del proyecto

- `model.py` — motor del modelo + backtest (genera `wc_model.json` → de ahí salen los picks).
- `picks.json` — picks actuales que lee `submit_gameon.py`.
- `submit_gameon.py` — login Firebase REST + `--probe` + envío (a finalizar en §4).
- `polla.yml` — GitHub Actions (cron diario). Va en `.github/workflows/`.
- (referencia) `jadx-out/` — código decompilado del APK, por si hay que revisar más.

---

## 7. Cómo arrancar en Claude Code

1. Pon `model.py`, `picks.json`, `submit_gameon.py`, `polla.yml` y este `.md` en una carpeta de proyecto.
2. Abre Claude Code en esa carpeta y dale este archivo como contexto inicial.
3. Pídele ejecutar la lista de §4 en orden, empezando por `--probe`.
4. **Mantener el dry-run** hasta confirmar endpoint + body. Respetar el alcance de §1.

## 8. Notas técnicas

- El `idToken` expira en ~1h; como la corrida es diaria, cada ejecución hace **login fresco** → no hay que refrescar tokens.
- El cron de GitHub Actions es UTC y puede retrasarse algunos minutos bajo carga: por eso la corrida matutina (mucho margen), no a 5 min exactos.
- Si en algún momento aparece que el envío exige un token de Play Integrity (improbable según §3), la vía nube no sería viable y habría que reconsiderar; revisar entonces dónde se adjunta el token de integridad en el código.
