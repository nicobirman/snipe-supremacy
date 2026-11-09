# Monitor para snipear el Afnan Supremacy Collector's Edition 100ml
# Versión para GitHub Actions: cada ejecución revisa las tiendas UNA vez.
# GitHub lo corre solo cada ~10 minutos (ver .github/workflows/snipe.yml).
# Si aparece en stock bajo PRECIO_MAX, manda una notificación al celular (app ntfy).

import json
import os
import sys
from datetime import date

import requests

# ---------------- CONFIGURACIÓN ----------------

PRECIO_MAX = 45000             # avisar solo si cuesta esto o menos (CLP)
ERRORES_ANTES_DE_AVISAR = 6    # ~1 hora fallando seguido -> te avisa que esa tienda se rompió

# Tiendas a vigilar: nombre y URL del producto (todas son Shopify)
TIENDAS = [
    ("Productos de Lujo", "https://productosdelujo.cl/products/supremacy-collectors-edition-afnan-100ml-edp-unisex"),
    ("Yauras",            "https://yauras.cl/products/afnan-supremacy-collector-edition-edp-100ml"),
    ("Lodoro",            "https://lodoro.cl/products/afnan-supremacy-collector-edition-eau-de-parfum-100ml-hombre"),
    ("Oferta Perfumes",   "https://www.ofertaperfumes.cl/products/perfume-supremacy-collectors-edp-100-ml-hombre"),
    ("Elite Perfumes",    "https://eliteperfumes.cl/products/afnan-afnan-supremacy-collector-edp-100ml-h"),
    ("Cosmetic",          "https://cosmetic.cl/products/perfume-supremacy-collectors-edition-afnan-edp-100-ml-hombre"),
    ("Multimarcas",       "https://multimarcasperfumes.cl/products/supremacy-collectors-edition-pour-homme-edp-100-ml-afnan"),
    ("DPG Duty Free (Zofri)", "https://dpgdutyfree.cl/products/afnan-supremacy-collectors-edition-edp-100ml-h"),
]

# ------------------------------------------------

ARCHIVO_ESTADO = "estado.json"
ES_PRUEBA_MANUAL = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
CABECERAS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

TOPICO_NTFY = os.environ.get("NTFY_TOPIC", "").strip()
if not TOPICO_NTFY:
    sys.exit("Falta el secreto NTFY_TOPIC (Settings -> Secrets and variables -> Actions).")


def revisar_tienda(url):
    """Consulta el endpoint .js de Shopify y devuelve (disponible, precio_minimo)."""
    respuesta = requests.get(url + ".js", headers=CABECERAS, timeout=20)
    respuesta.raise_for_status()
    datos = respuesta.json()

    # Shopify entrega los precios en centavos (precio * 100)
    precios_disponibles = [v["price"] / 100 for v in datos["variants"] if v["available"]]

    if precios_disponibles:
        return True, min(precios_disponibles)
    return False, datos["price"] / 100


def notificar(titulo, mensaje, link=None):
    """Manda una notificación push con ntfy.sh. Devuelve True si se envió bien."""
    cabeceras = {"Title": titulo, "Priority": "high", "Tags": "rotating_light"}
    if link:
        cabeceras["Click"] = link
    try:
        respuesta = requests.post(f"https://ntfy.sh/{TOPICO_NTFY}", data=mensaje.encode("utf-8"),
                                  headers=cabeceras, timeout=20)
        respuesta.raise_for_status()
        return True
    except requests.RequestException as error:
        print(f"  (no se pudo enviar la notificación: {error})")
        return False


def formato_clp(precio):
    return f"${precio:,.0f}".replace(",", ".")


def cargar_estado():
    """Lee lo que pasó en ejecuciones anteriores (a quién ya se avisó, errores seguidos)."""
    try:
        with open(ARCHIVO_ESTADO, encoding="utf-8") as archivo:
            estado = json.load(archivo)
    except (FileNotFoundError, json.JSONDecodeError):
        estado = {}
    estado.setdefault("avisados", {})   # tienda -> precio al que se avisó
    estado.setdefault("errores", {})    # tienda -> cantidad de errores seguidos
    return estado


def guardar_estado(estado):
    # Guardar la fecha hace que el repo tenga 1 commit al día, así GitHub
    # no pausa el workflow por "inactividad" (pasa a los 60 días sin actividad)
    estado["ultimo_dia"] = date.today().isoformat()
    with open(ARCHIVO_ESTADO, "w", encoding="utf-8") as archivo:
        json.dump(estado, archivo, indent=2, ensure_ascii=False)


def main():
    estado = cargar_estado()
    avisados, errores = estado["avisados"], estado["errores"]
    resumen = []

    for nombre, url in TIENDAS:
        # 1) Consultar la tienda
        try:
            disponible, precio = revisar_tienda(url)
        except Exception as error:
            errores[nombre] = errores.get(nombre, 0) + 1
            print(f"{nombre:24} ERROR ({errores[nombre]} seguidos): {error}")
            resumen.append(f"{nombre}: ERROR")

            # Avisar una sola vez si la tienda lleva ~1 hora fallando (link roto, bloqueo, etc.)
            if errores[nombre] == ERRORES_ANTES_DE_AVISAR:
                notificar("Monitor: tienda con problemas",
                          f"{nombre} lleva {ERRORES_ANTES_DE_AVISAR} revisiones fallando. Revisa el link.",
                          link=url)
            continue

        errores.pop(nombre, None)   # funcionó: reiniciar contador de errores

        estado_txt = "EN STOCK" if disponible else "agotado"
        print(f"{nombre:24} {estado_txt:9} {formato_clp(precio)}")
        resumen.append(f"{nombre}: {estado_txt} {formato_clp(precio)}")

        # 2) Decidir si avisar
        es_oferta = disponible and precio <= PRECIO_MAX
        precio_avisado = avisados.get(nombre)

        if es_oferta and (precio_avisado is None or precio < precio_avisado):
            enviado = notificar("Supremacy CE en stock!", f"{nombre}: {formato_clp(precio)}", link=url)
            if enviado:   # si falló el envío, se reintenta en la próxima revisión
                avisados[nombre] = precio
                print(f"  >>> NOTIFICACIÓN ENVIADA ({nombre})")
        elif not es_oferta:
            avisados.pop(nombre, None)   # se agotó o subió: volver a avisar la próxima vez

    guardar_estado(estado)

    # Si lo corriste a mano desde GitHub, te manda el resumen para comprobar que funciona
    if ES_PRUEBA_MANUAL:
        notificar("Prueba monitor Supremacy", "\n".join(resumen))


if __name__ == "__main__":
    main()
