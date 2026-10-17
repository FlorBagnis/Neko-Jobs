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
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import firebase_admin
import requests
from firebase_admin import credentials, firestore

import monitor as m

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "").strip()

MAX_INICIAL = 15               # avisos como máximo la primera vez (o al cambiar filtros)
MAX_PALABRAS = 70              # palabras clave / exclusiones por persona
MAX_AVISADOS = 3000            # puestos que se recuerdan por persona
MINUTOS_ENTRE_BUSQUEDAS = 55   # (ya no se usa para decidir: el modo lo define el workflow)
MAX_COLA = 300                 # puestos que se acumulan por persona en modo /resumen on
ZONA_DEFECTO = "America/Argentina/Buenos_Aires"   # si la persona no tiene zona ni país conocido

# País (sin tildes) -> zona horaria IANA. Mismo mapa que usa el Worker en /zona.
ZONAS_PAIS = {
    "argentina": "America/Argentina/Buenos_Aires",
    "chile": "America/Santiago",
    "mexico": "America/Mexico_City",
    "colombia": "America/Bogota",
    "peru": "America/Lima",
    "uruguay": "America/Montevideo",
    "brasil": "America/Sao_Paulo",
    "brazil": "America/Sao_Paulo",
    "ecuador": "America/Guayaquil",
    "venezuela": "America/Caracas",
    "bolivia": "America/La_Paz",
    "paraguay": "America/Asuncion",
    "costa rica": "America/Costa_Rica",
    "panama": "America/Panama",
    "guatemala": "America/Guatemala",
    "el salvador": "America/El_Salvador",
    "honduras": "America/Tegucigalpa",
    "nicaragua": "America/Managua",
    "republica dominicana": "America/Santo_Domingo",
    "cuba": "America/Havana",
    "puerto rico": "America/Puerto_Rico",
}

# Filtros /nivel y /modalidad: se buscan en título + ubicación (sin tildes, minúsculas).
PATRONES_NIVEL = {
    "junior": re.compile(r"\b(junior|jr|trainee|pasante|entry[- ]?level)\b"),
    "semi": re.compile(r"\b(semi[- ]?(senior|sr)|ssr|semi|intermedio|mid[- ]?level)\b"),
    # "senior" también se puede elegir en /nivel; además sirve para detectar que el título declara OTRO nivel
    "senior": re.compile(r"\b(senior|sr|tech lead|team lead|lider|principal|head of|director)\b"),
}
PATRONES_MODALIDAD = {
    "remoto": re.compile(r"\b(remoto|remota|remote|teletrabajo|home office|work from home|wfh)\b"),
    "hibrido": re.compile(r"\b(hibrido|hibrida|hybrid)\b"),
    # "presencial" también se puede elegir en /modalidad; además sirve para detectar que el puesto declara OTRA modalidad
    "presencial": re.compile(r"\b(presencial|onsite|on[- ]site|in[- ]office)\b"),
}
# "remoto" en /pais: puestos que no dependen del lugar
PATRON_REMOTO = re.compile(
    r"\b(remoto|remota|remote|teletrabajo|home office|work from home|wfh|anywhere|worldwide)\b")

HORA_RESUMEN_UTC = 12          # hora (UTC) desde la que se manda el resumen diario (9:00 en Argentina)

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


def descarta_por_pais(paises_usuario, titulo, lugar):
    """
    True si el usuario eligió países específicos (ej: ['chile', 'argentina']) 
    y NINGUNO de ellos se menciona en el título o ubicación del puesto.
    Si la lista está vacía ([]), pasan todos los de LATAM.
    """
    if not paises_usuario:
        return False  # Quiere todo LATAM abierto

    # "remoto" en /pais: también pasan los puestos que no dependen del lugar
    try:
        if "remoto" in [m.normalizar(x) for x in paises_usuario] and es_remoto(titulo, lugar):
            return False
    except Exception:
        pass
    
    texto_puesto = m.normalizar(f"{titulo} {lugar}")
    
    # Recorremos cada país que eligió el usuario
    for pais in paises_usuario:
        pais_norm = m.normalizar(pais)
        if pais_norm and pais_norm in texto_puesto:
            return False  # ¡Coincidió con al menos uno! No se descarta.
            
    return True  # Ninguno de los países elegidos apareció en el puesto -> se descarta.


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
    "/pais argentina, chile → elegir tus países de búsqueda\n"
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
#  al modo anterior de leer mensajes con getUpdates. Los comandos nuevos
#  /limpiar, /ultimos y /resumen viven solo en el Worker.)

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


def llego_al_maximo(actual, nuevos):
    """True si la lista ya está llena y había al menos una palabra realmente nueva."""
    if len(actual) < MAX_PALABRAS:
        return False
    claves = {m.normalizar(x) for x in actual}
    return any(m.normalizar(x) not in claves for x in nuevos)


def resumen_filtros(u):
    palabras = u.get("palabras", [])
    excluir = u.get("excluir", [])
    paises = u.get("pais", [])
    if isinstance(paises, str):
        paises = [paises] if paises else []
    
    estado = "activos ✅" if u.get("activo", True) else "en pausa ⏸️"
    return (
        f"Tus avisos están {estado}\n\n"
        f"🔎 Busco: {', '.join(palabras) if palabras else 'todavía nada (usá /agregar)'}\n"
        f"🌍 Países: {', '.join(paises) if paises else 'todo LATAM abierto'}\n"
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
            if llego_al_maximo(u.get("palabras", []), items):
                return f"Llegaste al máximo de {MAX_PALABRAS} palabras. Quitá alguna con /quitar"
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
            if llego_al_maximo(u.get("excluir", []), items):
                return f"Llegaste al máximo de {MAX_PALABRAS} palabras. Quitá alguna con /noexcluir"
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
    """Lee los mensajes nuevos de Telegram, los contesta y recuerda hasta dónde leyó."""
    meta = db.collection("meta").document("telegram")
    offset = (meta.get().to_dict() or {}).get("offset", 0)
    atendidos = 0
    for _ in range(5):
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
            except Exception as e:
                print(f"[error comando] {type(e).__name__}: {e}")
                respuesta = "Uy, algo falló de mi lado 🙈 Probá de nuevo en un rato."
            if respuesta:
                enviar(chat["id"], respuesta)
            atendidos += 1
        meta.set({"offset": offset}, merge=True)
    return atendidos


# -------------------------------------------------------------------- avisos

def es_remoto(titulo, lugar):
    """True si el título o la ubicación dicen que el puesto no depende del lugar."""
    return bool(PATRON_REMOTO.search(m.normalizar(f"{titulo} {lugar}")))


def declara_otro(texto, elegidos, patrones):
    """True si el texto declara algún valor (nivel/modalidad) y ninguno es de los elegidos.
    Si no declara nada, False: los puestos que no aclaran pasan."""
    dichos = [k for k, p in patrones.items() if p.search(texto)]
    return bool(dichos) and not any(k in dichos for k in elegidos)


def descarta_por_nivel_modalidad(u, titulo, lugar):
    """True solo si la persona configuró /nivel o /modalidad y el título/ubicación declaran
    OTRO valor (ej: eligió junior y el título dice senior). Si no aclaran nada, pasan.
    Sin configurar, o ante cualquier error, deja pasar el puesto."""
    try:
        texto = m.normalizar(f"{titulo} {lugar}")
        niveles = [x for x in (u.get("nivel") or []) if x in PATRONES_NIVEL]
        if niveles and declara_otro(texto, niveles, PATRONES_NIVEL):
            return True
        modalidades = [x for x in (u.get("modalidad") or []) if x in PATRONES_MODALIDAD]
        if modalidades and declara_otro(texto, modalidades, PATRONES_MODALIDAD):
            return True
    except Exception as e:
        print(f"[aviso] filtro nivel/modalidad falló ({type(e).__name__}): dejo pasar")
    return False


def zona_de(u):
    """Zona de la persona: /zona, si no el primer país conocido de /pais, si no Argentina."""
    z = u.get("zona", "")
    if not z:
        paises = u.get("pais", [])
        if isinstance(paises, str):
            paises = [paises] if paises else []
        for p in paises:
            z = ZONAS_PAIS.get(m.normalizar(p), "")
            if z:
                break
    for candidata in (z, ZONA_DEFECTO):
        try:
            if candidata:
                return ZoneInfo(candidata)
        except Exception:
            continue
    return timezone(timedelta(hours=-3))  # último recurso (sin base de zonas): Argentina


def en_silencio(u, ahora_utc):
    """True si ahora es horario de silencio para esta persona (/silencio 22-8, en SU zona).
    Ante cualquier error devuelve False: nunca se frena un aviso por un fallo."""
    try:
        rango = u.get("silencio", "")
        if not rango:
            return False
        ini, fin = (int(x) for x in rango.split("-"))
        if ini == fin or not (0 <= ini <= 23 and 0 <= fin <= 23):
            return False
        hora = ahora_utc.astimezone(zona_de(u)).hour
        return (ini <= hora < fin) if ini < fin else (hora >= ini or hora < fin)
    except Exception as e:
        print(f"[aviso] silencio falló ({type(e).__name__}): no se aplica")
        return False


def clave_puesto(url_empresa, p):
    return hashlib.sha1(f"{url_empresa}|{p['id']}".encode("utf-8")).hexdigest()[:12]


def avisar(db, uid, u, pendientes, descartados):
    """Manda a una persona sus puestos nuevos. Devuelve (enviados, errores)."""
    # Horario de silencio (/silencio): no se envía ni se marca nada, llega después.
    if en_silencio(u, datetime.now(timezone.utc)):
        return 0, 0
    ref = doc_usuario(db, uid)
    avisados = list(u.get("avisados", []))
    inicial = u.get("inicial", False)

    if inicial:
        a_enviar, omitidos = pendientes[:MAX_INICIAL], [c for _, _, c in pendientes[MAX_INICIAL:]]
    else:
        a_enviar, omitidos = pendientes, []

    grupos = {}
    for empresa, p, clave in a_enviar:
        grupos.setdefault(empresa, []).append((p, clave))

    # --- Modo /resumen on: en vez de enviar ahora, se acumula para el mensaje diario.
    # Si algo falla acá, en_cola queda en None y se envía como siempre.
    en_cola = None
    try:
        if u.get("resumen", False) is True and a_enviar:
            en_cola = [
                json.dumps({
                    "e": empresa,
                    "titulo": p["titulo"],
                    "lugar": p.get("lugar", ""),
                    "url": p["url"],
                    "sin_verificar": bool(p.get("sin_verificar")),
                }, ensure_ascii=False)
                for empresa, p, _ in a_enviar
            ]
    except Exception as e:
        print(f"[aviso] {uid}: no pude armar la cola del resumen ({type(e).__name__}): envío normal")
        en_cola = None
    if en_cola is not None:
        avisados += [c for _, _, c in a_enviar]
        grupos = {}

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
            errores += 1

    if enviados or omitidos or descartados or inicial or bloqueado or en_cola:
        cambios = {"avisados": (avisados + omitidos + descartados)[-MAX_AVISADOS:]}
        if enviados:
            cambios["recibidos"] = firestore.Increment(enviados)  # para /stats
        if en_cola:
            cambios["cola_resumen"] = (list(u.get("cola_resumen", [])) + en_cola)[-MAX_COLA:]
        if bloqueado:
            cambios["activo"] = False
            print(f"[aviso] {uid} bloqueó el bot: lo dejo en pausa")
        elif inicial and not errores:
            cambios["inicial"] = False
        ref.update(cambios)
    return enviados, errores


def armar_textos_resumen(items):
    """Arma los mensajes del resumen diario (agrupados por empresa, partidos si son largos)."""
    por_empresa = {}
    for s in items:
        try:
            d = json.loads(s)
            por_empresa.setdefault(d["e"], []).append({
                "titulo": d["titulo"],
                "lugar": d.get("lugar", ""),
                "url": d["url"],
                "sin_verificar": d.get("sin_verificar", False),
            })
        except Exception:
            continue  # un elemento dañado no frena a los demás
    total = sum(len(v) for v in por_empresa.values())
    if not total:
        return []
    bloques = []
    for empresa, ps in por_empresa.items():
        for i in range(0, len(ps), 10):
            bloques.append(m.armar_mensaje(empresa, ps[i:i + 10]))
    encabezado = f"📋 Resumen del día: {total} puesto(s) nuevo(s)\n\n"
    textos, actual = [], encabezado
    for b in bloques:
        if len(actual) + len(b) + 2 > 3800 and actual.strip():
            textos.append(actual.rstrip())
            actual = ""
        actual += b + "\n\n"
    if actual.strip():
        textos.append(actual.rstrip())
    return textos


def enviar_resumenes_diarios(db):
    """Manda el mensaje diario a quien tiene /resumen on. Devuelve cuántos puestos envió.
    Si alguien apagó /resumen con cosas en cola, se le mandan en la próxima corrida."""
    ahora = datetime.now(timezone.utc)
    hoy = ahora.strftime("%Y-%m-%d")
    total = 0
    for d in db.collection("usuarios").stream():
        try:
            u = d.to_dict() or {}
            cola = u.get("cola_resumen", [])
            if not cola or not u.get("activo", True):
                continue
            if en_silencio(u, ahora):
                continue
            if u.get("resumen", False) is True:
                if ahora.hour < HORA_RESUMEN_UTC or u.get("resumen_enviado") == hoy:
                    continue
            ref = doc_usuario(db, d.id)
            textos = armar_textos_resumen(cola)
            if not textos:
                ref.update({"cola_resumen": []})
                continue
            ok = True
            for texto in textos:
                resultado = enviar(int(d.id), texto)
                if resultado == "bloqueado":
                    ref.update({"activo": False})
                    print(f"[aviso] {d.id} bloqueó el bot: lo dejo en pausa")
                    ok = False
                    break
                if resultado != "ok":
                    ok = False
                    break
            if ok:
                ref.update({"cola_resumen": [], "resumen_enviado": hoy,
                            "recibidos": firestore.Increment(len(cola))})
                total += len(cola)
        except Exception as e:
            print(f"[error resumen] {d.id}: {type(e).__name__}: {e}")
    return total


def buscar_y_avisar(db):
    estadisticas = {"enviados": 0, "errores": 0}
    usuarios = {d.id: d.to_dict() for d in db.collection("usuarios").stream()}
    # Reactivar a quien pausó con /pausar <días> y ya cumplió el plazo
    ahora_ts = time.time()
    for uid, u in usuarios.items():
        try:
            hasta = u.get("pausa_hasta", 0)
            if not u.get("activo", True) and hasta and ahora_ts >= hasta:
                doc_usuario(db, uid).update({"activo": True, "inicial": True, "pausa_hasta": 0})
                u["activo"], u["inicial"], u["pausa_hasta"] = True, True, 0
                print(f"[info] {uid}: terminó su pausa, se reactiva")
        except Exception as e:
            print(f"[aviso] {uid}: no pude reactivar la pausa ({type(e).__name__})")

    activos = {uid: u for uid, u in usuarios.items() if u.get("activo", True) and u.get("palabras")}
    if not activos:
        print("No hay personas con avisos activos")
        return estadisticas

    print(f"[info] personas con avisos activos: {len(activos)}")
    por_idioma = {k: sum(1 for u in activos.values() if idioma_de(u) == k) for k in IDIOMAS}
    print(f"[info] idioma elegido: es={por_idioma['es']} en={por_idioma['en']} ambos={por_idioma['ambos']}")

    empresas = m.cargar_empresas()
    permitidas = m.compilar_exacto(m.leer_lista("ubicaciones_permitidas.txt") or m.UBICACIONES_PERMITIDAS)
    bloqueadas = m.compilar_exacto(m.leer_lista("ubicaciones_bloqueadas.txt") or m.UBICACIONES_BLOQUEADAS)
    filtros = {uid: (m.compilar(u["palabras"]), m.compilar(u.get("excluir", [])))
               for uid, u in activos.items()}
    vistos = {uid: set(u.get("avisados", [])) for uid, u in activos.items()}
    pendientes = {uid: [] for uid in activos}
    descartados = {uid: [] for uid in activos}
    cache_idioma = {}

    print(f"[info] empresas a revisar: {len(empresas)}")

    for nombre, url, es_ar in empresas:
        try:
            puestos = m.elegir_lector(url)(url)
        except Exception as e:
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

        # Puestos remotos fuera de zona (solo los usa quien puso "remoto" en /pais);
        # igual se respetan las ubicaciones bloqueadas (ej: "Remote - US").
        try:
            ids_zona = {id(p) for p in en_zona}
            remotos_extra = [
                p for p in puestos
                if id(p) not in ids_zona and es_remoto(p["titulo"], p["lugar"])
                and not any(b.search(m.normalizar(f"{p['titulo']} {p['lugar']}")) for b in bloqueadas)
            ]
        except Exception:
            remotos_extra = []

        for uid in activos:
            u = activos[uid]
            incluir, excluir = filtros[uid]
            pref = idioma_de(u)
            
            # Leemos los países como lista (soporta tanto formato viejo string como array nuevo)
            paises_bruto = u.get("pais", [])
            if isinstance(paises_bruto, str):
                paises_usuario = [paises_bruto] if paises_bruto else []
            else:
                paises_usuario = [p.strip().lower() for p in paises_bruto if p]

            candidatos = en_zona
            if remotos_extra and "remoto" in [m.normalizar(x) for x in paises_usuario]:
                candidatos = en_zona + remotos_extra

            for p in candidatos:
                clave = clave_puesto(url, p)
                if clave in vistos[uid] or not m.coincide(p["titulo"], nombre, incluir, excluir):
                    continue
                
                # Validamos contra la lista de países elegidos por el usuario
                if descarta_por_pais(paises_usuario, p["titulo"], p["lugar"]):
                    continue

                # /nivel y /modalidad (pasan los del valor elegido y los que no aclaran)
                if descarta_por_nivel_modalidad(u, p["titulo"], p["lugar"]):
                    continue

                marca = f"{clave}~{pref}"
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
                if idioma is None:
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


def resumen_demo(db):
    """Resumen a demanda. Solo lee, no reinicia nada."""
    d = db.collection("meta").document("estado").get().to_dict() or {}
    usuarios = [x.to_dict() for x in db.collection("usuarios").stream()]
    activos = sum(1 for u in usuarios if u.get("activo", True) and u.get("palabras"))
    texto = (
        f"🐾 Neko Jobs, resumen completo\n"
        f"Personas: {len(usuarios)} ({activos} con avisos activos)\n"
        f"Avisos enviados desde el último resumen: {d.get('avisos_desde_resumen', 0)}\n"
        f"Errores de lectura de empresas: {d.get('errores_desde_resumen', 0)}"
    )
    if not ADMIN_CHAT_ID:
        print("Falta el secret ADMIN_CHAT_ID")
        return 1
    return 0 if enviar(int(ADMIN_CHAT_ID), texto) == "ok" else 1

# ---------------------------------------------------------------------- main

def main():
    modo = sys.argv[1] if len(sys.argv) > 1 else "buscar"
    if not BOT_TOKEN or not os.environ.get("FIREBASE_SERVICE_ACCOUNT"):
        print("Faltan los secrets BOT_TOKEN y/o FIREBASE_SERVICE_ACCOUNT")
        return 1
    db = conectar()
    if modo == "resumen":
        return resumen_demo(db)
    atendidos = 0

    if modo == "mensajes":
        print(f"[ok] mensajes atendidos: {atendidos}")
        return 0

    meta = db.collection("meta").document("estado")
    meta.set({"ultima_busqueda": time.time()}, merge=True)
    estadisticas = buscar_y_avisar(db)
    try:
        estadisticas["enviados"] += enviar_resumenes_diarios(db)
    except Exception as e:
        print(f"[error] resumen por persona: {type(e).__name__}: {e}")
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
