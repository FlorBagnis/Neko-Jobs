# 🐾 Neko-Jobs · Monitor de ofertas laborales
 
Un bot gratuito que revisa cada hora las páginas de empleo de empresas tech y SaaS, filtra los puestos según tus palabras clave y te avisa por Telegram cuando aparece uno nuevo. Corre solo en GitHub Actions: no necesitás servidor ni saber programar.

---


## 🚧 Bot compartido: próximamente

Estoy trabajando en un **bot compartido** para que cualquier persona pueda usar Neko Jobs directamente desde Telegram, sin instalar nada ni saber programar. Todavía está en preparación. Cuando esté listo, voy a publicar el link acá.

Mientras tanto, si querés tener tu propio bot, podés copiar este repo (fork) y seguir los pasos de abajo.

## ✨ Qué hace

* 🤖 **Se ejecuta solo:** GitHub Actions lo corre cada hora, sin que tengas la compu prendida.
* 🎯 **Filtra por título:** te avisa solo de los puestos que coinciden con tus palabras clave (soporte técnico, Customer Experience, Customer Success, etc.) y descarta los que pongas en la lista de exclusión.
* 🇦🇷 **Filtra por ubicación:** por defecto solo avisa de puestos de Argentina o LATAM. Se puede cambiar.
* 🇪🇸 **Filtra por idioma:** solo avisa de puestos cuya descripción está en español.
* 💬 **Avisa por Telegram** (y opcionalmente por WhatsApp): recibís el título, el lugar y el link de cada puesto nuevo.
* 🛡️ **Sin repetidos:** recuerda los puestos que ya te avisó. Si falla el envío, reintenta en la próxima corrida.
---

## 🚀 Cómo usarlo

Elegí **una** de las dos opciones para tener tu copia del proyecto. Después seguí con la sección **Configuración**.

### Opción A: Fork (la más fácil)

1. Tocá el botón **Fork**, arriba a la derecha de esta página.
2. Tocá **Create fork**.
3. Listo, ya tenés tu copia. Pasá a **Configuración**.

### Opción B: Descargar el ZIP y subirlo a tu propio repo

1. En esta página tocá el botón AZUL **Code** y después **Download ZIP**.

 <img width="609" height="494" alt="image" src="https://github.com/user-attachments/assets/edb0e0d6-53e5-429b-8f7c-1e169b58b870" />

&nbsp;

2. Descomprimí el ZIP en tu compu.
3. En tu GitHub tocá **New repository**, ponele un nombre y tocá **Create repository**.
4. Dentro del repo nuevo tocá **Add file → Upload files**.
5. Arrastrá **todo el contenido** de la carpeta descomprimida, incluida la carpeta `.github`.
6. Tocá **Commit changes**.
7. Verificá que exista `.github/workflows/monitor.yml` en tu repo. Si no se subió (las carpetas que empiezan con punto a veces quedan ocultas; en Mac usá `Cmd + Shift + .` para verlas), creá el archivo a mano:
   * **Add file → Create new file**
   * En el nombre escribí `.github/workflows/monitor.yml` (GitHub arma las carpetas solo)
   * Pegá el contenido del `monitor.yml` de este repo
   * **Commit changes**

---

## ⚙️ Configuración (para las dos opciones)
 
1. **Creá tu bot de Telegram:** hablá con [@BotFather](https://t.me/BotFather), enviá `/newbot`, elegí un nombre y guardá el **token** que te da.
2. **Obtené tu chat ID:** escribile cualquier mensaje a tu bot. Después abrí en el navegador esta dirección, reemplazando `<TU_TOKEN>` por tu token:
   `https://api.telegram.org/bot<TU_TOKEN>/getUpdates`
   Buscá `"chat":{"id": ...}` y copiá ese número.
3. **Cargá tus secretos** en tu repo: **Settings → Secrets and variables → Actions → New repository secret**. Creá estos dos, con **exactamente** estos nombres:
   * `TELEGRAM_TOKEN`: el token del paso 1
   * `TELEGRAM_CHAT_ID`: el número del paso 2
4. **Revisá `estado.json`:** tiene que contener solamente `{}`. Es la memoria del bot y, si trae contenido, no te avisa de esos puestos.
5. **Personalizá tu búsqueda** (ver sección siguiente).
6. **Activá Actions:** pestaña **Actions** → botón verde "I understand my workflows, go ahead and enable them". Si ves **Monitor de empleos** como deshabilitado, tocá **Enable workflow**.
7. **Probalo:** **Actions → Monitor de empleos → Run workflow**. Tendría que llegarte un aviso a Telegram.
Desde ese momento corre solo, cada hora.
 
> 💡 La primera vez puede llegarte una tanda de avisos (hasta 10 por empresa) con los puestos que ya estaban publicados. Después solo llegan los nuevos.
 
---

## 🎛️ Personalizá tu búsqueda
 
No hace falta tocar el código. Editá estos archivos desde GitHub (lápiz ✏️ → **Commit changes**) y se aplican en la próxima corrida:
 
| Archivo | Para qué sirve | Ejemplo |
|---|---|---|
| `empresas.txt` | Páginas de empleo a revisar, una por línea: `Nombre \| link`. Si la empresa es argentina, agregá `\| AR` al final | `Mi Empresa \| https://jobs.lever.co/miempresa \| AR` |
| `palabras_clave.txt` | Palabras que tiene que tener el título del puesto | `soporte` |
| `excluir.txt` | Palabras que descartan un puesto | `senior` |
| `ubicaciones_permitidas.txt` (opcional) | Lugares que sí querés recibir, uno por línea. Si lo creás, reemplaza la lista por defecto (Argentina y LATAM) | `argentina` |
| `ubicaciones_bloqueadas.txt` (opcional) | Lugares que querés descartar, uno por línea. Si lo creás, reemplaza la lista por defecto | `mexico` |
 
Las palabras no distinguen mayúsculas ni tildes: "atención" encuentra "Atencion".
 
### ¿Qué hace el `| AR`?
 
Muchos avisos no dicen en qué país es el puesto. Si la empresa está marcada con `| AR`, esos avisos sin ubicación **sí pasan** el filtro. Si no la marcás, solo pasan los que nombran Argentina o una ciudad argentina en el título o en la ubicación. Si el aviso nombra otro país, se descarta igual.
 
### 📋 Machete: cómo cargar empresas en `empresas.txt`
 
**Paso 1.** Entrá al sitio de la empresa y buscá "Trabajá con nosotros", "Careers" o "Sumate".
 
**Paso 2.** Abrí cualquier puesto y mirá cómo empieza el link:
 
| Si el link empieza con... | Plataforma |
|---|---|
| `boards.greenhouse.io/...` | Greenhouse |
| `jobs.lever.co/...` | Lever |
| `jobs.ashbyhq.com/...` | Ashby |
| `apply.workable.com/...` | Workable |
| `applicants.selenios.com/c/...` | Selenios |
| cualquier otro | Página propia (puede fallar) |
 
Copiá el link de la **lista** de puestos, no el de un puesto puntual.
 
**Paso 3.** Formato de ejemplo. Reemplazá `nombreempresa` por el que aparece en el link real:
 
```text
Empresa A | https://boards.greenhouse.io/nombreempresa | AR
Empresa B | https://jobs.lever.co/nombreempresa
Empresa C | https://jobs.ashbyhq.com/nombreempresa
Empresa D | https://apply.workable.com/nombreempresa/
Empresa E | https://applicants.selenios.com/c/nombreempresa | AR
```
 
**Paso 4.** Para Greenhouse, Lever y Ashby podés comprobar que el nombre existe abriendo estos links en el navegador. Si ves una lista con datos, funciona; si da error, el nombre está mal:
 
* Greenhouse: `https://boards-api.greenhouse.io/v1/boards/nombreempresa/jobs`
* Lever: `https://api.lever.co/v0/postings/nombreempresa?mode=json`
* Ashby: `https://api.ashbyhq.com/posting-api/job-board/nombreempresa`
**Consejos:**
 
* Las líneas que empiezan con `#` se ignoran (sirven para dejar notas o desactivar una empresa).
* Empezá con pocas empresas (5 a 10) y sumá más después.
* Las páginas propias de cada empresa pueden no leerse bien, sobre todo si cargan con JavaScript.
---
 
## 🔍 Cómo ver qué está pasando
 
Entrá a **Actions**, abrí la última corrida, tocá el job **monitor** y abrí el paso **Buscar puestos nuevos**. Ahí ves, empresa por empresa, qué pasó:
 
| Lo que dice el log | Qué significa |
|---|---|
| `[ok] Empresa: 25 puestos leídos, 2 para avisar` | Todo bien |
| `sin ver antes: X \| con tus palabras clave: Y \| en Argentina/LATAM: Z` | Cuántos puestos pasó cada filtro |
| `ejemplos de ubicaciones: ...` | Hubo puestos con tus palabras clave, pero se descartaron por ubicación |
| `(1 descartados por estar en inglés)` | Hubo puestos que pasaron los filtros, pero la descripción está en inglés |
| `no se encontraron puestos` | El link está mal o la página carga con JavaScript |
| `[error] Empresa: 404 ...` | El link no existe o cambió |
| `[modo prueba, sin Telegram ni WhatsApp configurado]` | Faltan los secretos: el bot lee los puestos pero no manda nada |
 
Una empresa que falla no frena a las demás.
 
### ❓ Problemas frecuentes
 
**No me llega nada a Telegram.** Revisá que los secretos se llamen exactamente `TELEGRAM_TOKEN` y `TELEGRAM_CHAT_ID`, y que le hayas escrito un mensaje a tu bot antes de pedir el chat ID. Si el log dice "modo prueba", los secretos no se están leyendo.
 
**La corrida sale con una cruz roja ❌.** Abrí el log y mirá la última línea del paso que falló. Los errores más comunes son un `empresas.txt` sin ninguna empresa válida (`No hay empresas con link`) o un archivo `.py` o `.yml` con el contenido cambiado.
 
**Me llegaron muchos avisos juntos.** Es normal la primera vez: avisa de lo que ya estaba publicado (hasta 10 por empresa).
 
**Dejé de recibir avisos.** GitHub pausa los workflows programados si el repo pasa 60 días sin actividad. Entrá a **Actions** y reactivalo con **Enable workflow**.
 
**No me avisa de puestos que sí existen.** Probablemente el título no tiene tus palabras clave, el aviso no nombra Argentina (probá marcar la empresa con `| AR`) o la descripción está en inglés.
 
---
 
## 🗄️ Estructura del proyecto
 
```text
Neko-Jobs/
├── .github/
│   └── workflows/
│       └── monitor.yml            <- Configuración de GitHub Actions
├── monitor.py                     <- Script principal en Python
├── requirements.txt               <- Librerías necesarias
├── empresas.txt                   <- Páginas de empleo a monitorear
├── palabras_clave.txt             <- Puestos que querés recibir
├── excluir.txt                    <- Palabras a descartar
├── ubicaciones_permitidas.txt     <- (opcional) Lugares que sí querés
├── ubicaciones_bloqueadas.txt     <- (opcional) Lugares que no querés
└── estado.json                    <- Memoria de puestos ya avisados
```
 
---
 
## 🛠️ Tecnologías
 
* **Python:** `requests`, `BeautifulSoup`
* **GitHub Actions:** ejecución programada
* **Telegram Bot API** (y WhatsApp opcional con CallMeBot)
---
 
## 📣 Opcional: avisos para varias personas
 
Podés crear un canal público de Telegram, agregar tu bot como administrador con permiso de publicar y poner `@NombreDelCanal` en `TELEGRAM_CHAT_ID`. Todos los que se unan al canal reciben los avisos con tus filtros.
 
---
 
## 📱 Opcional: avisos por WhatsApp
 
El bot puede avisarte también por WhatsApp, a tu propio número, con [CallMeBot](https://www.callmebot.com) (servicio gratuito y no oficial).
 
1. Agendá el número de CallMeBot (lo encontrás en su página) y mandale este mensaje: `I allow callmebot to send me messages`.
2. Te responde con una clave (apikey).
3. En tu repo creá dos secretos más (**Settings → Secrets and variables → Actions**):
   * `WHATSAPP_PHONE`: tu número con código de país, sin espacios (ej: `+5491112345678`)
   * `CALLMEBOT_APIKEY`: la clave que recibiste
El workflow ya está preparado para usarlos. Los mensajes pueden demorar unos minutos y cada persona necesita su propia clave.
 
---
 
## ⚠️ Limitaciones conocidas
 
* Por defecto solo avisa de puestos de **Argentina o LATAM**, según el título y la ubicación del aviso. Se puede cambiar con `ubicaciones_permitidas.txt` y `ubicaciones_bloqueadas.txt`.
* Solo avisa de puestos con la descripción en **español**. Si no puede leer el texto, avisa igual con un ⚠️. Este filtro no se cambia desde un archivo: para otros idiomas hay que editar `monitor.py`.
* El filtro de palabras clave mira solo el **título** del puesto.
* **No funciona con portales de empleo como LinkedIn, Bumeran o Computrabajo.** Esos sitios bloquean el acceso automático, así que sus links no se pueden cargar en `empresas.txt`. El bot lee las páginas de empleo propias de cada empresa, que son públicas.
* Las páginas que cargan todo con JavaScript pueden no leerse bien.
* El lector genérico para páginas propias es básico y puede necesitar ajustes.
* GitHub pausa los workflows programados si el repo pasa 60 días sin actividad.
---
 
## 🔒 Buenas prácticas
 
* Nunca escribas tu token en el código: usá siempre **Secrets**.
* El bot solo lee páginas públicas de empleo. Confirmá siempre los datos en la página de la empresa antes de postularte.
* No agregues cientos de empresas de golpe: revisar unas pocas páginas por hora es razonable, pero conviene no abusar.

---


¿Te sirvió? Dejale una ⭐ al repo.

---

## 📄 Licencia

Distribuido bajo licencia MIT. Ver el archivo `LICENSE`.

👩‍💻 Autora

**Florencia Bagnis**

* 💼 [LinkedIn](https://www.linkedin.com/in/florencia-bagnis)
* 💻 [Portfolio](https://florbagnis.github.io/Portfolio-FlorBagnis/)
* 📧 [florenciasoledadbagnis@gmail.com](mailto:florenciasoledadbagnis@gmail.com)

<br>

> 🌸 Script automatizado desarrollado para el monitoreo de oportunidades laborales en empresas tech, enfocado en **Python**, automatización en la nube con **GitHub Actions**, integración con la **API de Telegram** y filtrado inteligente de perfiles profesionales.

