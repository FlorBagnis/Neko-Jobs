# 🐾 neko-jobs · Monitoreo de Ofertas Laborales

> **neko-jobs** es un script automatizado en Python diseñado para revisar de forma periódica las páginas de empleo de empresas tech y plataformas SaaS, filtrar los puestos según palabras clave del perfil profesional y enviar alertas instantáneas a Telegram.

---

## ✨ Características Principales

* 🤖 **Automatización en la Nube:** Ejecución programada mediante **GitHub Actions** para revisar vacantes de forma totalmente autónoma[cite: 1].
* 🎯 **Filtrado Inteligente:** Análisis de puestos basado en palabras clave específicas para perfiles de soporte técnico, Customer Experience y Customer Success.
* 💬 **Alertas en Telegram:** Notificación directa al instante cuando se detecta una nueva oferta compatible.
* 🛡️ **Control de Estado:** Registro de puestos ya procesados para evitar duplicados y reintento automático si falla el envío de la alerta.

---

## 🛠️ Tecnologías Utilizadas

* **Lenguaje:** Python (`requests`, `BeautifulSoup`).
* **Automatización & CI/CD:** GitHub Actions.
* **Integraciones:** Telegram Bot API (y opción de WhatsApp mediante CallMeBot).
* **Control de Versiones:** Git, GitHub.

---

### 🎯 Objetivo del Proyecto

El objetivo es optimizar la búsqueda activa de empleo en el sector tecnológico y de plataformas SaaS. Al automatizar la revisión de las páginas de empleo propias de las empresas, se evita la demora típica de los portales masivos y se asegura una respuesta temprana ante nuevas oportunidades orientadas a perfiles técnicos, de operaciones y de atención al cliente.

---

## 🗄️ Estructura del Proyecto

```text
neko-jobs/
├── .github/
│   └── workflows/
│       └── monitor.yml       <- Configuración de GitHub Actions
├── monitor.py                <- Script principal en Python
├── empresas.txt              <- Lista de URLs de empresas a monitorear
├── palabras_clave.txt        <- Filtros de puestos buscados
├── excluir.txt               <- Palabras clave a descartar
└── estado.json               <- Memoria de puestos ya notificados

```

🚀 Cómo Usarlo
Hacé un fork de este repositorio y creá un bot de Telegram a través de @BotFather.

Configurá las credenciales en Settings > Secrets and variables > Actions añadiendo TELEGRAM_TOKEN y TELEGRAM_CHAT_ID.

Copiá el archivo de flujo de trabajo de ejemplo a .github/workflows/monitor.yml.

Editá empresas.txt con los sitios web o APIs de empleo que te interese seguir y palabras_clave.txt con tus roles objetivo.

⚠️ Limitaciones Conocidas
Las páginas que dependen enteramente de renderizado pesado con JavaScript pueden presentar dificultades de lectura.

El analizador genérico cuenta con una lógica básica.

El filtrado opera estrictamente sobre el título del puesto y no sobre el cuerpo completo de la descripción.

## Avisos por WhatsApp (opcional)

El bot puede avisarte también por WhatsApp, a tu propio número, usando CallMeBot (servicio gratuito y no oficial).

1. Agendá el número de CallMeBot (lo encontrás en callmebot.com) y mandale: `I allow callmebot to send me messages`.
2. Te responde con una clave (apikey).
3. En tu repo: Settings → Secrets and variables → Actions, creá dos secretos:
   - `WHATSAPP_PHONE`: tu número con código de país, sin espacios (ej: `+5491112345678`)
   - `CALLMEBOT_APIKEY`: la clave que recibiste
4. Asegurate de que tu workflow pase esos dos secretos en `env:`.

Los mensajes pueden demorar unos minutos. Cada persona necesita su propia clave.


👩‍💻 Autora

**Florencia Bagnis**

* 💼 [LinkedIn](https://www.linkedin.com/in/florencia-bagnis)
* 💻 [Portfolio](https://florbagnis.github.io/Portfolio-FlorBagnis/)
* 📧 [florenciasoledadbagnis@gmail.com](mailto:florenciasoledadbagnis@gmail.com)

<br>

> 🌸 Script automatizado desarrollado para el monitoreo de oportunidades laborales en empresas tech, enfocado en **Python**, automatización en la nube con **GitHub Actions**, integración con la **API de Telegram** y filtrado inteligente de perfiles profesionales.

