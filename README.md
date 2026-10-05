# 🐾 neko-jobs · Monitor de ofertas laborales

Un bot gratuito que revisa cada hora las páginas de empleo de empresas tech y SaaS, filtra los puestos según tus palabras clave y te avisa por Telegram cuando aparece uno nuevo. Corre solo en GitHub Actions: no necesitás servidor ni saber programar.

---

## ✨ Qué hace

* 🤖 **Se ejecuta solo:** GitHub Actions lo corre cada hora, sin que tengas la compu prendida.
* 🎯 **Filtra por título:** te avisa solo de los puestos que coinciden con tus palabras clave (soporte técnico, Customer Experience, Customer Success, etc.) y descarta los que pongas en la lista de exclusión.
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
3. **Cargá tus secretos** en tu repo: **Settings → Secrets and variables → Actions → New repository secret**. Creá estos dos:
   * `TELEGRAM_TOKEN`: el token del paso 1
   * `TELEGRAM_CHAT_ID`: el número del paso 2
4. **Personalizá tu búsqueda** (ver sección siguiente).
5. **Activá Actions:** pestaña **Actions** → botón verde "I understand my workflows, go ahead and enable them" → elegí **Monitor de empleos** → **Run workflow** para probarlo.

Desde ese momento corre solo, cada hora.

> 💡 La primera vez puede llegarte una tanda de avisos (hasta 10 por empresa) con los puestos que ya estaban publicados. Después solo llegan los nuevos.

---

## 🎛️ Personalizá tu búsqueda

No hace falta tocar el código. Editá estos archivos desde GitHub (lápiz ✏️ → **Commit changes**) y se aplican en la próxima corrida:

| Archivo | Para qué sirve | Ejemplo |
|---|---|---|
| `empresas.txt` | Páginas de empleo a revisar, una por línea con el formato `Nombre \| link` | `Mi Empresa \| https://boards.greenhouse.io/miempresa` |
| `palabras_clave.txt` | Palabras que tiene que tener el título del puesto | `soporte` |
| `excluir.txt` | Palabras que descartan un puesto | `senior` |

Funciona con páginas de **Greenhouse, Lever, Ashby, Workable y Selenios**. También prueba con páginas propias de cada empresa, pero ahí puede fallar si cargan con JavaScript.

Las palabras no distinguen mayúsculas ni tildes: "atención" encuentra "Atencion".

---

## 🗄️ Estructura del proyecto

```text
neko-jobs/
├── .github/
│   └── workflows/
│       └── monitor.yml       <- Configuración de GitHub Actions
├── monitor.py                <- Script principal en Python
├── requirements.txt          <- Librerías necesarias
├── empresas.txt              <- Páginas de empleo a monitorear
├── palabras_clave.txt        <- Puestos que querés recibir
├── excluir.txt               <- Palabras a descartar
└── estado.json               <- Memoria de puestos ya avisados (se crea sola)
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

* Solo avisa de puestos de **Argentina o LATAM**, según el título y la ubicación del aviso. Si no dice dónde es, solo pasa cuando marcaste la empresa con `| AR`.
* Solo avisa de puestos con la descripción en **español**. Si no puede leer el texto, avisa igual con un ⚠️. Este filtro no se cambia desde un archivo: para otros idiomas hay que editar `monitor.py`.
* El filtro de palabras clave mira solo el **título** del puesto.
* Las páginas que cargan todo con JavaScript pueden no leerse bien.
* El lector genérico para páginas propias es básico y puede necesitar ajustes.
* GitHub pausa los workflows programados si el repo pasa 60 días sin actividad. Si dejás de recibir avisos, entrá a **Actions** y reactivalo.

---

## 🔒 Buenas prácticas

* Nunca escribas tu token en el código: usá siempre **Secrets**.
* El bot solo lee páginas públicas de empleo. Confirmá siempre los datos en la página de la empresa antes de postularte.

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

