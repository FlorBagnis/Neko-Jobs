# 🐾 neko-jobs · Monitor de ofertas laborales

Un bot gratuito que revisa cada hora las páginas de empleo de empresas tech y SaaS, filtra los puestos según tus palabras clave y te avisa por Telegram cuando aparece uno nuevo. Corre solo en GitHub Actions: no necesitás servidor ni saber programar.

---

## ✨ Qué hace

* 🤖 **Se ejecuta solo:** GitHub Actions lo corre cada hora, sin que tengas la compu prendida.
* 🎯 **Filtra por título:** te avisa solo de los puestos que coinciden con tus palabras clave (soporte técnico, Customer Experience, Customer Success, etc.) y descarta los que pongas en la lista de exclusión.
* 💬 **Avisa por Telegram:** recibís el título, el lugar y el link de cada puesto nuevo.
* 🛡️ **Sin repetidos:** recuerda los puestos que ya te avisó. Si falla el envío, reintenta en la próxima corrida.

---

## 🚀 Cómo usarlo (unos 15 minutos)

1. **Hacé un fork** de este repositorio (botón *Fork*, arriba a la derecha).
2. **Creá tu bot:** en Telegram hablá con [@BotFather](https://t.me/BotFather), enviá `/newbot` y guardá el token que te da.
3. **Obtené tu chat ID:** escribile cualquier mensaje a tu bot y abrí en el navegador `https://api.telegram.org/bot<TU_TOKEN>/getUpdates` (reemplazá `<TU_TOKEN>`). Buscá `"chat":{"id": ...}` y copiá ese número.
4. **Cargá tus secretos** en tu fork: *Settings → Secrets and variables → Actions → New repository secret*
   * `TELEGRAM_TOKEN`: el token del paso 2
   * `TELEGRAM_CHAT_ID`: el número del paso 3
5. **Reiniciá la memoria:** abrí `estado.json`, tocá el lápiz ✏️, dejá solamente `{}` y guardá (*Commit changes*). Así el bot te avisa de los puestos que hay hoy y no de los míos.
6. **Personalizá tu búsqueda** (ver sección siguiente).
7. **Activá Actions:** pestaña *Actions* → botón verde "I understand my workflows, go ahead and enable them". Después entrá a *Monitor de empleos* → *Run workflow* para probarlo.

Desde ese momento corre solo cada hora.

> 💡 La primera vez puede llegarte una tanda de avisos (hasta 10 por empresa) con los puestos que ya estaban publicados. Después solo llegan los nuevos.

---

## 🎛️ Personalizá tu búsqueda

No hace falta tocar el código. Editá estos archivos desde GitHub (lápiz ✏️ → *Commit changes*) y se aplican en la próxima corrida:

| Archivo | Para qué sirve | Ejemplo |
|---|---|---|
| `empresas.txt` | Páginas de empleo a revisar, una por línea | `Mi Empresa \| https://boards.greenhouse.io/miempresa` |
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
└── estado.json               <- Memoria de puestos ya notificados
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

1. Agendá el número de CallMeBot (lo encontrás en su página) y mandale: `I allow callmebot to send me messages`.
2. Te responde con una clave (apikey).
3. En tu repo creá dos secretos: `WHATSAPP_PHONE` (tu número con código de país, sin espacios, ej: `+5491112345678`) y `CALLMEBOT_APIKEY` (la clave recibida).

Los mensajes pueden demorar unos minutos. Cada persona necesita su propia clave.

---

## ⚠️ Limitaciones conocidas

* Las páginas que cargan todo con JavaScript pueden no leerse bien.
* El lector genérico para páginas propias es básico y puede necesitar ajustes.
* El filtro mira solo el **título** del puesto, no la descripción completa.
* No filtra por país ni idioma: eso depende de las empresas y de las palabras que elijas.
* GitHub pausa los workflows programados si el repo pasa 60 días sin actividad. Si dejás de recibir avisos, entrá a *Actions* y reactivalo.

---

## 🔒 Buenas prácticas

* Nunca escribas tu token en el código: usá siempre *Secrets*.
* El bot solo lee páginas públicas de empleo. Confirmá siempre los datos en la página de la empresa antes de postularte.

---

¿Te sirvió? Dejale una ⭐ al repo.

## 📄 Licencia

MIT

👩‍💻 Autora

**Florencia Bagnis**

* 💼 [LinkedIn](https://www.linkedin.com/in/florencia-bagnis)
* 💻 [Portfolio](https://florbagnis.github.io/Portfolio-FlorBagnis/)
* 📧 [florenciasoledadbagnis@gmail.com](mailto:florenciasoledadbagnis@gmail.com)

<br>

> 🌸 Script automatizado desarrollado para el monitoreo de oportunidades laborales en empresas tech, enfocado en **Python**, automatización en la nube con **GitHub Actions**, integración con la **API de Telegram** y filtrado inteligente de perfiles profesionales.

