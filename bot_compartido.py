#!/usr/bin/env python3
"""
Neko Jobs compartido: UN solo bot de Telegram para muchas personas.

- Cada persona se configura chateando con el bot (/start, /agregar, /quitar...).
  Eso lo atiende el Worker de Cloudflare (webhook), no este script.
- Los filtros de cada una se guardan en Firebase (Firestore).
- Este script, en GitHub Actions, busca ofertas y le manda a cada persona
  solo lo que coincide con SUS filtros.

Reutiliza los lectores y filtros de monitor.py, que sigue funcionando igual
para quien lo use con su propio bot.

Secrets de GitHub que necesita:
  BOT_TOKEN                 token del bot compartido (el que te da @BotFather)
  FIREBASE_SERVICE_ACCOUNT  contenido completo del JSON de la cuenta de servicio
  ADMIN_CHAT_ID             (opcional) tu chat ID, para el resumen diario
"""

import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import firebase_admin
import requests
from firebase_admin import credentials, firestore

import monitor as m

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "").strip()

MAX_INICIAL = 15               # avisos como máximo la primera vez (o al cambiar filtros)
MAX_PALABRAS = 30              # palabras clave / exclusiones por persona
MAX_AVISADOS = 3000            # puestos que se recuerdan por persona
MINUTOS_ENTRE_BUSQUEDAS = 55   # (ya no se usa para decidir: el modo lo define el workflow)

# Idioma de la descripción que eligió cada persona con /idioma (campo "idioma" en Firestore).
IDIOMAS = {"es": "español", "en": "inglés", "ambos": "español e inglés"}


def idioma_de(u):
    """Idioma elegido por la persona. Si no tiene el campo (usuarios viejos): español."""
    v = u.get("idioma", "es")
    return v if v in IDIOMAS else "es"


def descarta_por_idioma(pref, detectado):
    """True si el puesto no corresponde al idioma que eligió la persona.
    Si no se pudo detectar el idioma (None), no se descarta: se avisa marcado."""
    if pref == "ambos" or detectado is None:
        return False
    if pref == "es":
        return detectado == "en"
    return detectado != "en"  # pref == "en": solo inglés

def descarta_por_pais(pais_usuario, titulo, lugar):
    """
    True si el usuario eligió un país específico (ej: 'chile') 
    y el puesto NO lo menciona en su título o ubicación.
    Si el usuario dejó el país en blanco (''), pasan todos los de LATAM.
    """
    if not pais_usuario:
        return False  # Quiere todo LATAM abierto
    
    texto_puesto = m.normalizar(f"{titulo} {lugar}")
    return pais_usuario not in texto_puesto


BIENVENIDA = (
    "¡Hola! 🐾 Soy Neko Jobs. Reviso cada hora las páginas de empleo de empresas tech "
    "y te aviso por acá de los puestos nuevos que coincidan con lo que buscás.\n\n"
    "Para empezar, decime qué buscás con /agregar. Por ejemplo:\n"
    "/agregar soporte, customer success, atención\n\n"
    "Si hay puestos que no querés ver:\n"
    "/excluir senior, ventas\n\n"
    "Mirá todos los comandos con /ayuda.\n\n"
    "🔒 Guardo solo tu ID de Telegram, tu nombre y tus filtros, únicamente para mandarte "
    "avisos. Con /borrar eliminás todo cuando quieras.\n\n"
    "⏱️ Puedo tardar unos minutos en contestarte."
)

AYUDA = (
    "🐾 Comandos:\n\n"
    "/agregar soporte, customer success → puestos que querés recibir\n"
    "/quitar soporte → dejar de buscar esa palabra\n"
    "/excluir senior, ventas → descartar puestos con esas palabras\n"
    "/noexcluir senior → volver a permitirlas\n"
    "/filtros → ver lo que tenés configurado\n"
    "/pausar → dejar de recibir avisos\n"
    "/reanudar → volver a recibirlos\n"
    "/borrar → eliminar tus datos\n\n"
    "Las palabras se buscan en el título del puesto, sin importar mayúsculas ni tildes. "
    "Solo aviso de puestos en Argentina o LATAM con la descripción en español."
)


# ------------------------------------------------------------------ Telegram

def tg(metodo, datos=None, intentos=3):
    """Llama a la API de Telegram. Devuelve la respuesta, o None si no hubo conexión."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{metodo}"
    for _ in range(intentos):
        try:
            r = requests.post(url, data=datos or {}, timeout=m.TIMEOUT)
        except requests.RequestException as e:
            print(f"[error Telegram] {type(e).__name__}")
            return None
        if r.status_code == 429:  # demasiados mensajes: espera lo que pide Telegram
            try:
                espera = r.json().get("parameters", {}).get("retry_after", 2)
            except ValueError:
                espera = 2
            time.sleep(min(espera, 30) + 1)
            continue
        return r
    return None


def enviar(chat_id, texto):
    """Devuelve 'ok', 'bloqueado' (la persona frenó o bloqueó el bot) o 'error'."""
    r = tg("sendMessage", {
        "chat_id": chat_id,
        "text": texto[:4000],
        "disable_web_page_preview": "true",
    })
    if r is None:
        return "error"
    if r.ok:
        time.sleep(0.05)  # Telegram limita la velocidad de envío
        return "ok"
    print(f"[error Telegram] {r.status_code}: {r.text[:200]}")
    return "bloqueado" if r.status_code == 403 else "error"


# ------------------------------------------------------------------ Firebase

def conectar():
    clave = json.loads(os.environ["FIREBASE_SERVICE_ACCOUNT"])
    firebase_admin.initialize_app(credentials.Certificate(clave))
    return firestore.client()


def doc_usuario(db, chat_id):
    return db.collection("usuarios").document(str(chat_id))


def asegurar_usuario(db, chat_id, nombre):
    """Devuelve (referencia, datos, es_nuevo). Crea a la persona si no existía."""
    ref = doc_usuario(db, chat_id)
    snap = ref.get()
    if snap.exists:
        return ref, snap.to_dict(), False
    datos = {
        "chat_id": chat_id,
        "nombre": nombre,
        "palabras": [],
        "excluir": [],
        "activo": True,
        "idioma": "es",
        "inicial": True,  # True = en la próxima búsqueda recibe lo ya publicado (tope MAX_INICIAL)
        "avisados": [],
        "creado": firestore.SERVER_TIMESTAMP,
    }
    ref.set(datos)
    return ref, datos, True


# ------------------------------------------------------------------ comandos
# (Hoy los atiende el Worker de Cloudflare; este código queda por si se vuelve
#  al modo anterior de leer mensajes con getUpdates.)

def lista_desde(texto):
    """'soporte, Customer Success' -> ['soporte', 'customer success']"""
    items = []
    for x in re.split(r"[,\n;]", texto):
        x = " ".join(x.split()).lower()
        if x and len(x) <= 40 and x not in items:
            items.append(x)
    return items


def sumar(actual, nuevos):
    claves = {m.normalizar(x) for x in actual}
    resultado, agregados = list(actual), []
    for x in nuevos:
        if m.normalizar(x) not in claves and len(resultado) < MAX_PALABRAS:
            resultado.append(x)
            claves.add(m.normalizar(x))
            agregados.append(x)
    return resultado, agregados


def restar(actual, quitar):
    claves = {m.normalizar(x) for x in quitar}
    quitados = [x for x in actual if m.normalizar(x) in claves]
    return [x for x in actual if m.normalizar(x) not in claves], quitados


def resumen_filtros(u):
    palabras = u.get("palabras", [])
    excluir = u.get("excluir", [])
    estado = "activos ✅" if u.get("activo", True) else "en pausa ⏸️"
    return (
        f"Tus avisos están {estado}\n\n"
        f"🔎 Busco: {', '.join(palabras) if palabras else 'todavía nada (usá /agregar)'}\n"
        f"🚫 Descarto: {', '.join(excluir) if excluir else 'nada'}\n"
        f"🌐 Idioma de las ofertas: {IDIOMAS[idioma_de(u)]}"
    )


def procesar(db, chat_id, nombre, texto):
    """Interpreta un mensaje y devuelve la respuesta."""
    cmd, _, resto = texto.strip().partition(" ")
    cmd = cmd.lower().split("@")[0]
    if not cmd.startswith("/"):
        return "No entendí 🙈 Probá con /ayuda para ver qué puedo hacer."

    if cmd == "/borrar":
        doc_usuario(db, chat_id).delete()
        return "Listo, borré tus datos y no te voy a mandar más avisos. Si querés volver, escribime /start 👋"

    ref, u, nuevo = asegurar_usuario(db, chat_id, nombre)
    palabras, excluir = u.get("palabras", []), u.get("excluir", [])

    if cmd == "/start":
        return BIENVENIDA if nuevo else "¡Ya estás dentro! 🐾\n\n" + resumen_filtros(u)
    if cmd == "/ayuda":
        return AYUDA
    if cmd == "/filtros":
        return resumen_filtros(u)

    if cmd == "/agregar":
        items = lista_desde(resto)
        if not items:
            return "Decime qué querés agregar. Ejemplo:\n/agregar soporte, customer success"
        palabras, agregadas = sumar(palabras, items)
        if not agregadas:
            return "Esas palabras ya estaban 😉\n\n" + resumen_filtros(u)
        ref.update({"palabras": palabras, "inicial": True})
        return (f"✅ Agregué: {', '.join(agregadas)}\n\n"
                "En la próxima búsqueda te mando lo que ya está publicado (hasta "
                f"{MAX_INICIAL} puestos) y después solo lo nuevo.")

    if cmd == "/quitar":
        palabras, quitadas = restar(palabras, lista_desde(resto))
        if not quitadas:
            return "No encontré esas palabras en tu lista. Mirá /filtros"
        ref.update({"palabras": palabras})
        return f"✅ Quité: {', '.join(quitadas)}"

    if cmd == "/excluir":
        items = lista_desde(resto)
        if not items:
            return "Decime qué querés descartar. Ejemplo:\n/excluir senior, ventas"
        excluir, agregadas = sumar(excluir, items)
        if not agregadas:
            return "Esas palabras ya estaban 😉\n\n" + resumen_filtros(u)
        ref.update({"excluir": excluir})
        return f"✅ Voy a descartar puestos con: {', '.join(agregadas)}"

    if cmd == "/noexcluir":
        excluir, quitadas = restar(excluir, lista_desde(resto))
        if not quitadas:
            return "No encontré esas palabras en tus exclusiones. Mirá /filtros"
        ref.update({"excluir": excluir, "inicial": True})
        return f"✅ Ya no descarto: {', '.join(quitadas)}"

    if cmd == "/idioma":
        mapa = {
            "es": "es", "espanol": "es",
            "en": "en", "ingles": "en", "english": "en",
            "ambos": "ambos", "todos": "ambos", "both": "ambos",
        }
        v = mapa.get(m.normalizar(resto))
        if not v:
            return (f"Hoy te aviso de ofertas en {IDIOMAS[idioma_de(u)]}.\n\n"
                    "Para cambiarlo:\n/idioma es\n/idioma en\n/idioma ambos")
        ref.update({"idioma": v, "inicial": True})
        return f"✅ Listo, te aviso de ofertas en {IDIOMAS[v]}."

    if cmd == "/pausar":
        ref.update({"activo": False})
        return "⏸️ Listo, pausé tus avisos. Con /reanudar los volvés a activar."

    if cmd == "/reanudar":
        ref.update({"activo": True, "inicial": True})
        return "▶️ Avisos activados otra vez. Te mando lo publicado mientras tanto y después lo nuevo."

    return "Ese comando no lo conozco 🙈 Probá con /ayuda"


def procesar_mensajes(db):
    """Lee los mensajes nuevos de Telegram, los contesta y recuerda hasta dónde leyó.
    (Sin uso mientras el webhook del Worker esté activo: getUpdates no funciona con webhook.)"""
    meta = db.collection("meta").document("telegram")
    offset = (meta.get().to_dict() or {}).get("offset", 0)
    atendidos = 0
    for _ in range(5):  # hasta 500 mensajes por corrida
        r = tg("getUpdates", {
            "offset": offset, "limit": 100, "timeout": 0,
            "allowed_updates": json.dumps(["message"]),
        })
        if r is None or not r.ok:
            print("[aviso] no pude leer los mensajes de Telegram")
            break
        novedades = r.json().get("result", [])
        if not novedades:
            break
        for up in novedades:
            offset = up["update_id"] + 1
            msg = up.get("message") or {}
            chat = msg.get("chat") or {}
            texto = msg.get("text")
            if chat.get("type") != "private" or not texto:
                continue
            nombre = (msg.get("from") or {}).get("first_name", "")
            try:
                respuesta = procesar(db, chat["id"], nombre, texto)
            except Exception as e:  # un mensaje problemático no frena a los demás
                print(f"[error comando] {type(e).__name__}: {e}")
                respuesta = "Uy, algo falló de mi lado 🙈 Probá de nuevo en un rato."
            if respuesta:
                enviar(chat["id"], respuesta)
            atendidos += 1
        meta.set({"offset": offset}, merge=True)
    return atendidos


# -------------------------------------------------------------------- avisos

def clave_puesto(url_empresa, p):
    return hashlib.sha1(f"{url_empresa}|{p['id']}".encode("utf-8")).hexdigest()[:12]


def avisar(db, uid, u, pendientes, descartados):
    """Manda a una persona sus puestos nuevos. Devuelve (enviados, errores)."""
    ref = doc_usuario(db, uid)
    avisados = list(u.get("avisados", []))
    inicial = u.get("inicial", False)

    if inicial:  # primera vez / filtros nuevos: tope de avisos, el resto se marca como visto
        a_enviar, omitidos = pendientes[:MAX_INICIAL], [c for _, _, c in pendientes[MAX_INICIAL:]]
    else:
        a_enviar, omitidos = pendientes, []

    grupos = {}  # un mensaje por empresa, igual que monitor.py
    for empresa, p, clave in a_enviar:
        grupos.setdefault(empresa, []).append((p, clave))

    enviados = errores = 0
    bloqueado = False
    for empresa, items in grupos.items():
        resultado = enviar(int(uid), m.armar_mensaje(empresa, [p for p, _ in items]))
        if resultado == "ok":
            avisados += [c for _, c in items]
            enviados += len(items)
        elif resultado == "bloqueado":
            bloqueado = True
            break
        else:
            errores += 1  # no se marca como visto: se reintenta en la próxima búsqueda

    if enviados or omitidos or descartados or inicial or bloqueado:
        cambios = {"avisados": (avisados + omitidos + descartados)[-MAX_AVISADOS:]}
        if bloqueado:
            cambios["activo"] = False
            print(f"[aviso] {uid} bloqueó el bot: lo dejo en pausa")
        elif inicial and not errores:
            cambios["inicial"] = False
        ref.update(cambios)
    return enviados, errores


def buscar_y_avisar(db):
    estadisticas = {"enviados": 0, "errores": 0}
    usuarios = {d.id: d.to_dict() for d in db.collection("usuarios").stream()}
    activos = {uid: u for uid, u in usuarios.items() if u.get("activo", True) and u.get("palabras")}
    if not activos:
        print("No hay personas con avisos activos")
        return estadisticas

    # DIAGNÓSTICO: solo cantidades, nunca IDs ni nombres (el log de un repo público es visible)
    print(f"[info] personas con avisos activos: {len(activos)}")
    por_idioma = {k: sum(1 for u in activos.values() if idioma_de(u) == k) for k in IDIOMAS}
    print(f"[info] idioma elegido: es={por_idioma['es']} en={por_idioma['en']} ambos={por_idioma['ambos']}")

    empresas = m.cargar_empresas()
    permitidas = m.compilar_exacto(m.leer_lista("ubicaciones_permitidas.txt") or m.UBICACIONES_PERMITIDAS)
    bloqueadas = m.compilar_exacto(m.leer_lista("ubicaciones_bloqueadas.txt") or m.UBICACIONES_BLOQUEADAS)
    filtros = {uid: (m.compilar(u["palabras"]), m.compilar(u.get("excluir", [])))
               for uid, u in activos.items()}
    vistos = {uid: set(u.get("avisados", [])) for uid, u in activos.items()}
    pendientes = {uid: [] for uid in activos}   # (empresa, puesto, clave)
    descartados = {uid: [] for uid in activos}  # puestos que no son del idioma elegido: se marcan vistos
    cache_idioma = {}                           # el idioma de cada puesto se lee una sola vez

    print(f"[info] empresas a revisar: {len(empresas)}")

    for nombre, url, es_ar in empresas:
        try:
            puestos = m.elegir_lector(url)(url)
        except Exception as e:  # una empresa que falla no frena a las demás
            print(f"[error] {nombre}: {e}")
            estadisticas["errores"] += 1
            continue
        if not puestos:
            print(f"[aviso] {nombre}: no se encontraron puestos")
            continue

        en_zona = [p for p in puestos
                   if m.ubicacion_ok(p["titulo"], p["lugar"], permitidas, bloqueadas, es_ar)]
        coinciden = sum(
            1 for p in en_zona
            if any(m.coincide(p["titulo"], nombre, inc, exc) for inc, exc in filtros.values())
        )
        print(f"[info] {nombre}: {len(puestos)} puestos, {len(en_zona)} en zona, "
              f"{coinciden} coinciden por título")

        for uid in activos:
            incluir, excluir = filtros[uid]
            pref = idioma_de(activos[uid])
            for p in en_zona:
                clave = clave_puesto(url, p)
                if clave in vistos[uid] or not m.coincide(p["titulo"], nombre, incluir, excluir):
                    continue
                marca = f"{clave}~{pref}"  # puesto ya descartado antes por el idioma que tiene hoy
                if marca in vistos[uid]:
                    continue
                if clave not in cache_idioma:
                    cache_idioma[clave] = m.idioma_del_texto(m.texto_del_puesto(p))
                    print(f"[info] {nombre} | {p['titulo']} | idioma={cache_idioma[clave]}")
                idioma = cache_idioma[clave]
                if descarta_por_idioma(pref, idioma):
                    descartados[uid].append(marca)
                    continue
                q = dict(p)
                if idioma is None:  # no se pudo leer: se avisa, pero marcado
                    q["sin_verificar"] = True
                pendientes[uid].append((nombre, q, clave))

    print(f"[info] puestos pendientes de avisar (suma de todas las personas): "
          f"{sum(len(v) for v in pendientes.values())}")

    for uid, u in activos.items():
        try:
            enviados, errores = avisar(db, uid, u, pendientes[uid], descartados[uid])
        except Exception as e:
            print(f"[error] {uid}: {type(e).__name__}: {e}")
            estadisticas["errores"] += 1
            continue
        estadisticas["enviados"] += enviados
        estadisticas["errores"] += errores
    return estadisticas


# ------------------------------------------------------------ resumen diario

def resumen_diario(db):
    """Una vez por día (desde las 12:00 UTC = 9:00 en Argentina) te avisa que el bot sigue vivo."""
    if not ADMIN_CHAT_ID:
        return
    ahora = datetime.now(timezone.utc)
    hoy = ahora.strftime("%Y-%m-%d")
    meta = db.collection("meta").document("estado")
    d = meta.get().to_dict() or {}
    if ahora.hour < 12 or d.get("ultimo_resumen") == hoy:
        return
    usuarios = [x.to_dict() for x in db.collection("usuarios").stream()]
    activos = sum(1 for u in usuarios if u.get("activo", True) and u.get("palabras"))
    texto = (
        f"🐾 Neko Jobs sigue vivo ({hoy})\n"
        f"Personas: {len(usuarios)} ({activos} con avisos activos)\n"
        f"Avisos enviados desde el último resumen: {d.get('avisos_desde_resumen', 0)}\n"
        f"Errores de lectura de empresas: {d.get('errores_desde_resumen', 0)}"
    )
    if enviar(int(ADMIN_CHAT_ID), texto) == "ok":
        meta.set({"ultimo_resumen": hoy, "avisos_desde_resumen": 0, "errores_desde_resumen": 0}, merge=True)


# ---------------------------------------------------------------------- main

def main():
    # Los mensajes de las personas los atiende el Worker de Cloudflare (webhook).
    # Este script solo busca ofertas y manda los avisos.
    modo = sys.argv[1] if len(sys.argv) > 1 else "buscar"
    if not BOT_TOKEN or not os.environ.get("FIREBASE_SERVICE_ACCOUNT"):
        print("Faltan los secrets BOT_TOKEN y/o FIREBASE_SERVICE_ACCOUNT")
        return 1
    db = conectar()
    atendidos = 0

    if modo == "mensajes":
        print(f"[ok] mensajes atendidos: {atendidos}")
        return 0

    meta = db.collection("meta").document("estado")
    meta.set({"ultima_busqueda": time.time()}, merge=True)
    estadisticas = buscar_y_avisar(db)
    meta.set({
        "avisos_desde_resumen": firestore.Increment(estadisticas["enviados"]),
        "errores_desde_resumen": firestore.Increment(estadisticas["errores"]),
    }, merge=True)

    resumen_diario(db)
    print(f"[ok] mensajes atendidos: {atendidos} | avisos enviados: "
          f"{estadisticas['enviados']} | errores: {estadisticas['errores']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
