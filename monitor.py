#!/usr/bin/env python3
"""
Monitor de ofertas de empleo.

Revisa las páginas de empleo listadas en empresas.txt, detecta puestos NUEVOS
que coincidan con palabras_clave.txt (y no con excluir.txt) y avisa por Telegram.

Uso local:   python monitor.py
En GitHub:   lo ejecuta .github/workflows/monitor.yml cada hora.
"""
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
MAX_PRIMERA_VEZ = 10  # tope de avisos por empresa la primera vez que se la revisa


# ----------------------------------------------------------------- utilidades
def normalizar(txt):
    """Minúsculas y sin tildes, para comparar 'Atención' con 'atencion'."""
    txt = unicodedata.normalize("NFD", txt or "")
    txt = "".join(c for c in txt if unicodedata.category(c) != "Mn")
    return txt.lower().strip()


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


def compilar(palabras):
    # \b al principio: "soporte" matchea "soportes", pero no "apoyoporte"
    return [re.compile(r"\b" + re.escape(normalizar(p))) for p in palabras]


def coincide(titulo, empresa, incluir, excluir):
    t = normalizar(titulo)
    if not any(p.search(t) for p in incluir):
        return False
    texto_excl = normalizar(f"{empresa} {titulo}")
    return not any(p.search(texto_excl) for p in excluir)


def cargar_empresas():
    empresas = []
    for linea in leer_lista("empresas.txt"):
        if "|" not in linea:
            continue
        nombre, url = [x.strip() for x in linea.split("|", 1)]
        if not url.startswith("http"):
            print(f"[aviso] {nombre}: todavía no tiene link, la salto")
            continue
        empresas.append((nombre, url))
    return empresas


def slug(url, pos=0):
    partes = [p for p in urlparse(url).path.split("/") if p]
    return partes[pos] if len(partes) > pos else None


def get_json(url):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


# ------------------------------------------------- lectores por tipo de página
def buscar_greenhouse(url):
    data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug(url)}/jobs")
    return [
        {
            "id": str(j["id"]),
            "titulo": j["title"],
            "url": j["absolute_url"],
            "lugar": (j.get("location") or {}).get("name", ""),
        }
        for j in data.get("jobs", [])
    ]


def buscar_lever(url):
    api = "api.eu.lever.co" if ".eu." in urlparse(url).netloc else "api.lever.co"
    data = get_json(f"https://{api}/v0/postings/{slug(url)}?mode=json")
    return [
        {
            "id": j["id"],
            "titulo": j["text"],
            "url": j["hostedUrl"],
            "lugar": (j.get("categories") or {}).get("location", ""),
        }
        for j in data
    ]


def buscar_ashby(url):
    data = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug(url)}")
    return [
        {
            "id": j["id"],
            "titulo": j["title"],
            "url": j.get("jobUrl", url),
            "lugar": j.get("location", ""),
        }
        for j in data.get("jobs", [])
    ]


def buscar_workable(url):
    cuenta = slug(url)
    r = requests.post(
        f"https://apply.workable.com/api/v3/accounts/{cuenta}/jobs",
        json={"query": "", "location": [], "department": [], "worktype": [], "remote": []},
        headers=HEADERS,
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    puestos = []
    for j in r.json().get("results", []):
        loc = j.get("location") or {}
        puestos.append(
            {
                "id": j["shortcode"],
                "titulo": j["title"],
                "url": f"https://apply.workable.com/{cuenta}/j/{j['shortcode']}/",
                "lugar": ", ".join(x for x in [loc.get("city"), loc.get("country")] if x),
            }
        )
    return puestos


def buscar_selenios(url):
    """Páginas de empleo hechas con Selenios (applicants.selenios.com/c/empresa).
    Cada puesto es un título <h2>; no tiene un link propio visible, así que
    el aviso apunta a la página de la empresa."""
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    puestos = []
    for h in soup.find_all("h2"):
        titulo = " ".join(h.get_text(" ", strip=True).split())
        if not titulo:
            continue
        modalidad = ""
        # el texto que sigue al título suele ser Remoto / Híbrido / Presencial
        for t in h.find_all_next(string=True, limit=4):
            if t.strip().lower() in ("remoto", "híbrido", "hibrido", "presencial"):
                modalidad = t.strip()
                break
        puestos.append({"id": titulo, "titulo": titulo, "url": url, "lugar": modalidad})
    return puestos


def buscar_generico(url):
    """Plan B para páginas propias: lee los links de la página y usa su texto."""
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    vistos, puestos = set(), []
    for a in soup.find_all("a", href=True):
        texto = " ".join(a.get_text(" ", strip=True).split())
        if len(texto) < 10 or len(texto) > 150:
            continue
        link = urljoin(url, a["href"])
        if link in vistos:
            continue
        vistos.add(link)
        puestos.append({"id": link, "titulo": texto, "url": link, "lugar": ""})
    return puestos


def elegir_lector(url):
    host = urlparse(url).netloc.lower()
    if "greenhouse.io" in host:
        return buscar_greenhouse
    if "lever.co" in host:
        return buscar_lever
    if "ashbyhq.com" in host:
        return buscar_ashby
    if "workable.com" in host:
        return buscar_workable
    if "selenios.com" in host:
        return buscar_selenios
    return buscar_generico


# -------------------------------------------------------------------- avisos
def enviar_telegram(texto):
    """Devuelve None si no está configurado, True si salió bien, False si falló."""
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        return None
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat, "text": texto[:4000], "disable_web_page_preview": "true"},
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        print(f"[error Telegram] {type(e).__name__}")
        return False
    if not r.ok:
        print(f"[error Telegram] {r.status_code}: {r.text}")
    return r.ok


def enviar_whatsapp(texto):
    """WhatsApp a tu propio número, vía CallMeBot (servicio gratuito no oficial)."""
    telefono = os.environ.get("WHATSAPP_PHONE", "").strip()
    apikey = os.environ.get("CALLMEBOT_APIKEY", "").strip()
    if not telefono or not apikey:
        return None
    try:
        r = requests.get(
            "https://api.callmebot.com/whatsapp.php",
            params={"phone": telefono, "text": texto[:1500], "apikey": apikey},
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        print(f"[error WhatsApp] {type(e).__name__}")
        return False
    if not r.ok:
        print(f"[error WhatsApp] {r.status_code}: {r.text[:200]}")
    return r.ok


def enviar(texto):
    """True si el aviso salió por algún canal (o si no hay canales: modo prueba)."""
    resultados = [r for r in (enviar_telegram(texto), enviar_whatsapp(texto)) if r is not None]
    if not resultados:
        print("[modo prueba, sin Telegram ni WhatsApp configurado]\n" + texto + "\n")
        return True
    return any(resultados)


def armar_mensaje(nombre, nuevos):
    lineas = [f"🔔 {nombre}: {len(nuevos)} puesto(s) nuevo(s)", ""]
    for p in nuevos:
        lugar = f" ({p['lugar']})" if p["lugar"] else ""
        lineas.append(f"• {p['titulo']}{lugar}\n  {p['url']}")
    return "\n".join(lineas)


# ---------------------------------------------------------------------- main
def main():
    empresas = cargar_empresas()
    if not empresas:
        print("No hay empresas con link en empresas.txt")
        return 1

    incluir = compilar(leer_lista("palabras_clave.txt"))
    excluir = compilar(leer_lista("excluir.txt"))
    estado = json.loads(STATE_FILE.read_text("utf-8")) if STATE_FILE.exists() else {}

    for nombre, url in empresas:
        try:
            puestos = elegir_lector(url)(url)
        except Exception as e:  # una empresa que falla no frena a las demás
            print(f"[error] {nombre}: {e}")
            continue

        if not puestos:
            print(f"[aviso] {nombre}: no se encontraron puestos "
                  "(¿la página carga con JavaScript o cambió el link?)")
            continue

        vistos = set(estado.get(url, []))
        primera_vez = url not in estado
        nuevos = [
            p for p in puestos
            if p["id"] not in vistos and coincide(p["titulo"], nombre, incluir, excluir)
        ]
        if primera_vez:
            nuevos = nuevos[:MAX_PRIMERA_VEZ]

        print(f"[ok] {nombre}: {len(puestos)} puestos leídos, {len(nuevos)} para avisar")
        enviado = enviar(armar_mensaje(nombre, nuevos)) if nuevos else True

        if enviado:
            estado[url] = sorted(vistos | {p["id"] for p in puestos})
        else:
            print(f"[aviso] {nombre}: no se pudo avisar, se reintenta en la próxima corrida")

    STATE_FILE.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
