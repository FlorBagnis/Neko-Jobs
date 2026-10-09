#!/usr/bin/env python3
"""
Monitor de ofertas de empleo multiusuario (Firestore + Telegram).
Revisa las empresas y despacha los puestos según los filtros y país de cada usuario.
"""
import html
import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = Path(__file__).parent
STATE_FILE = BASE / "estado.json"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
TIMEOUT = 25
MAX_PRIMERA_VEZ = 15

# ----------------------------------------------------------------- utilidades
def normalizar(txt):
    txt = unicodedata.normalize("NFD", txt or "")
    txt = "".join(c for c in txt if unicodedata.category(c) != "Mn")
    return txt.lower().strip()


def limpiar_html(h):
    return BeautifulSoup(html.unescape(h or ""), "html.parser").get_text(" ", strip=True)


# ------------------------------------------- filtro de idioma
PALABRAS_ES = {
    "de", "la", "el", "en", "y", "que", "los", "las", "con", "para", "por", "una",
    "del", "se", "al", "su", "sus", "nuestro", "nuestra", "nuestros", "tu", "tus",
    "sobre", "como", "mas", "experiencia", "equipo", "trabajo", "buscamos",
    "requisitos", "responsabilidades", "empresa", "cliente", "clientes",
}
PALABRAS_EN = {
    "the", "and", "of", "to", "in", "for", "with", "you", "your", "our", "we",
    "will", "is", "are", "on", "as", "be", "that", "this", "from", "have", "or",
    "experience", "team", "work", "about", "requirements", "responsibilities",
    "company", "customers", "looking",
}

def idioma_del_texto(texto):
    palabras = re.findall(r"[a-z]+", normalizar(texto))
    if len(palabras) < 40:
        return "es"  # por defecto si es corto
    es = sum(1 for w in palabras if w in PALABRAS_ES)
    en = sum(1 for w in palabras if w in PALABRAS_EN)
    return "es" if es >= en else "en"


def texto_del_puesto(p):
    if p.get("texto"):
        return p["texto"]
    try:
        if p.get("json_url"):
            d = get_json(p["json_url"])
            partes = [d.get("description"), d.get("requirements"), d.get("benefits")]
            return limpiar_html(" ".join(x for x in partes if x))
        r = requests.get(p["url"], headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for t in soup(["script", "style", "nav", "header", "footer"]):
            t.decompose()
        return soup.get_text(" ", strip=True)
    except Exception:
        return ""


def cargar_empresas():
    empresas = []
    ruta = BASE / "empresas.txt"
    if not ruta.exists():
        return []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "|" not in linea:
            continue
        partes = [x.strip() for x in linea.split("|")]
        nombre, url = partes[0], partes[1]
        if url.startswith("http"):
            empresas.append((nombre, url))
    return empresas


def slug(url, pos=0):
    partes = [p for p in urlparse(url).path.split("/") if p]
    return partes[pos] if len(partes) > pos else None


def get_json(url):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


# ------------------------------------------------- lectores de empresas
def buscar_greenhouse(url):
    data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug(url)}/jobs?content=true")
    return [{"id": str(j["id"]), "titulo": j["title"], "url": j["absolute_url"], "lugar": (j.get("location") or {}).get("name", ""), "texto": limpiar_html(j.get("content", ""))} for j in data.get("jobs", [])]

def buscar_lever(url):
    api = "api.eu.lever.co" if ".eu." in urlparse(url).netloc else "api.lever.co"
    data = get_json(f"https://{api}/v0/postings/{slug(url)}?mode=json")
    return [{"id": j["id"], "titulo": j["text"], "url": j["hostedUrl"], "lugar": (j.get("categories") or {}).get("location", ""), "texto": (j.get("descriptionPlain") or "") + " " + (j.get("additionalPlain") or "")} for j in data]

def buscar_ashby(url):
    data = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug(url)}")
    return [{"id": j["id"], "titulo": j["title"], "url": j.get("jobUrl", url), "lugar": j.get("location", ""), "texto": j.get("descriptionPlain") or limpiar_html(j.get("descriptionHtml", ""))} for j in data.get("jobs", [])]

def buscar_workable(url):
    cuenta = slug(url)
    r = requests.post(f"https://apply.workable.com/api/v3/accounts/{cuenta}/jobs", json={"query": "", "location": [], "department": [], "worktype": [], "remote": []}, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    puestos = []
    for j in r.json().get("results", []):
        loc = j.get("location") or {}
        puestos.append({"id": j["shortcode"], "titulo": j["title"], "url": f"https://apply.workable.com/{cuenta}/j/{j['shortcode']}/", "lugar": ", ".join(x for x in [loc.get("city"), loc.get("country")] if x), "json_url": f"https://apply.workable.com/api/v2/accounts/{cuenta}/jobs/{j['shortcode']}"})
    return puestos

def buscar_selenios(url):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    puestos = []
    for h in soup.find_all("h2"):
        titulo = " ".join(h.get_text(" ", strip=True).split())
        if titulo:
            puestos.append({"id": titulo, "titulo": titulo, "url": url, "lugar": ""})
    return puestos

def buscar_generico(url):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    vistos, puestos = set(), []
    for a in soup.find_all("a", href=True):
        texto = " ".join(a.get_text(" ", strip=True).split())
        if 10 <= len(texto) <= 150:
            link = urljoin(url, a["href"])
            if link not in vistos:
                vistos.add(link)
                puestos.append({"id": link, "titulo": texto, "url": link, "lugar": ""})
    return puestos

def elegir_lector(url):
    host = urlparse(url).netloc.lower()
    if "greenhouse.io" in host: return buscar_greenhouse
    if "lever.co" in host: return buscar_lever
    if "ashbyhq.com" in host: return buscar_ashby
    if "workable.com" in host: return buscar_workable
    if "selenios.com" in host: return buscar_selenios
    return buscar_generico


# ------------------------------------------------------------------- Firestore
def obtener_token_firebase(sa):
    import time
    import base64
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    ahora = int(time.time())
    def b64(b):
        return base64.urlsafe_b64encode(b).decode().rstrip("=")

    header = b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    payload = b64(json.dumps({
        "iss": sa["client_email"],
        "scope": "https://www.googleapis.com/auth/datastore",
        "aud": "https://oauth2.googleapis.com/token",
        "iat": ahora,
        "exp": ahora + 3600
    }).encode())

    private_key = load_pem_private_key(sa["private_key"].encode(), password=None)
    sig = private_key.sign(f"{header}.{payload}".encode(), padding.PKCS1v15(), hashes.SHA256())
    assertion = f"{header}.{payload}.{b64(sig)}"

    r = requests.post("https://oauth2.googleapis.com/token", data={
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": assertion
    })
    return r.json().get("access_token")


def cargar_usuarios_firestore():
    sa_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT", "")
    if not sa_json:
        print("[aviso] No hay FIREBASE_SERVICE_ACCOUNT configurado en GitHub Secrets.")
        return []
    try:
        sa = json.loads(sa_json)
        token = obtener_token_firebase(sa)
        url = f"https://firestore.googleapis.com/v1/projects/{sa['project_id']}/databases/(default)/documents/usuarios"
        r = requests.get(url, headers={"Authorization": f"Bearer {token}"})
        if not r.ok:
            print(f"[error Firestore] {r.status_code}: {r.text}")
            return []

        usuarios = []
        for doc in r.json().get("documents", []):
            fields = doc.get("fields", {})
            chat_id = int(doc["name"].split("/")[-1])
            activo = fields.get("activo", {}).get("booleanValue", True)
            if not activo:
                continue

            palabras = [v.get("stringValue", "") for v in fields.get("palabras", {}).get("arrayValue", {}).get("values", [])]
            excluir = [v.get("stringValue", "") for v in fields.get("excluir", {}).get("arrayValue", {}).get("values", [])]
            idioma = fields.get("idioma", {}).get("stringValue", "es")
            pais = fields.get("pais", {}).get("stringValue", "").strip().lower()
            inicial = fields.get("inicial", {}).get("booleanValue", True)
            avisados = {v.get("stringValue", "") for v in fields.get("avisados", {}).get("arrayValue", {}).get("values", [])}

            usuarios.append({
                "chat_id": chat_id,
                "palabras": [normalizar(p) for p in palabras if p],
                "excluir": [normalizar(e) for e in excluir if e],
                "idioma": idioma,
                "pais": pais,
                "inicial": inicial,
                "avisados": avisados
            })
        return usuarios
    except Exception as e:
        print(f"[error leyendo Firestore] {e}")
        return []


def enviar_telegram(chat_id, texto):
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    if not token or not chat_id:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": texto[:4000], "disable_web_page_preview": True},
            timeout=TIMEOUT
        )
        return r.ok
    except Exception:
        return False


# ------------------------------- comodines y listas de compatibilidad
# (usados por bot_compartido.py)
UBICACIONES_PERMITIDAS = [
    "argentina", "buenos aires", "caba", "capital federal", "gba",
    "cordoba", "rosario", "mendoza", "la plata", "tucuman", "santa fe",
    "mar del plata", "neuquen", "salta", "palermo",
    "latam", "latin america", "latinoamerica", "america latina",
    "south america", "sudamerica",
    # Sumamos los países de LATAM para que pasen sin problema
    "chile", "colombia", "mexico", "peru", "uruguay", "brasil", "brazil",
    "ecuador", "venezuela", "bolivia", "paraguay", "costa rica", "panama"
]

# Ojo: los países de LATAM NO están en esta lista de bloqueo
UBICACIONES_BLOQUEADAS = [
    "spain", "espana", "madrid", "barcelona", "portugal",
    "united states", "usa", "us", "estados unidos", "eeuu",
    "canada", "north america", "europe", "emea", "apac",
    "uk", "united kingdom", "london", "germany", "india",
    "philippines", "poland", "israel",
]

def compilar_exacto(palabras):
    return [re.compile(r"\b" + re.escape(normalizar(p)) + r"\b") for p in palabras]

# Alias: bot_compartido.py llama a m.compilar(...)
compilar = compilar_exacto

def leer_lista(nombre_archivo):
    ruta = BASE / nombre_archivo
    if not ruta.exists():
        return []
    lineas = []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#"):
            lineas.append(linea)
    return lineas


# ---------------------------------------------------------------------- main
def main():
    empresas = cargar_empresas()
    if not empresas:
        print("No hay empresas con link en empresas.txt")
        return 1

    usuarios = cargar_usuarios_firestore()
    if not usuarios:
        print("No hay usuarios activos en Firestore para notificar.")
        return 0

    estado = json.loads(STATE_FILE.read_text("utf-8")) if STATE_FILE.exists() else {}

    for nombre, url in empresas:
        try:
            puestos = elegir_lector(url)(url)
        except Exception as e:
            print(f"[error] {nombre}: {e}")
            continue

        if not puestos:
            print(f"[aviso] {nombre}: no se encontraron puestos.")
            continue

        vistos = set(estado.get(url, []))
        sin_ver = [p for p in puestos if p["id"] not in vistos]

        if not sin_ver:
            continue

        # Evaluamos para cada usuario
        for u in usuarios:
            if not u["palabras"]:
                continue

            # Filtramos puestos para este usuario específico
            nuevos_usuario = []
            for p in sin_ver:
                titulo_norm = normalizar(p["titulo"])
                lugar_norm = normalizar(p["lugar"])
                texto_completo = f"{titulo_norm} {lugar_norm}"

                # 1. Validar palabras clave obligatorias
                if not any(palabra in titulo_norm for palabra in u["palabras"]):
                    continue

                # 2. Validar exclusiones
                if any(exc in titulo_norm or exc in normalizar(nombre) for exc in u["excluir"]):
                    continue

                # 3. Validar país (si el usuario eligió uno con /pais)
                if u["pais"] and u["pais"] not in texto_completo:
                    continue

                # 4. Validar idioma
                if u["idioma"] != "ambos":
                    lang = idioma_del_texto(texto_del_puesto(p))
                    if lang != u["idioma"]:
                        continue

                nuevos_usuario.append(p)

            if not nuevos_usuario:
                continue

            # Si es la primera vez del usuario, limitamos
            if u["inicial"]:
                nuevos_usuario = nuevos_usuario[:MAX_PRIMERA_VEZ]

            # Armar mensaje personalizado
            lineas = [f"🔔 {nombre}: {len(nuevos_usuario)} puesto(s) nuevo(s)", ""]
            for p in nuevos_usuario:
                lugar = f" ({p['lugar']})" if p["lugar"] else ""
                lineas.append(f"• {p['titulo']}{lugar}\n  {p['url']}")

            mensaje = "\n".join(lineas)
            enviar_telegram(u["chat_id"], mensaje)

        # Actualizamos vistos generales de la empresa
        estado[url] = sorted(vistos | {p["id"] for p in puestos})

    STATE_FILE.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
