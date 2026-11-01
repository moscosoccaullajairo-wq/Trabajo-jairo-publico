#!/usr/bin/env python3
"""Genera data/status.json con clima por tienda, sismos y avisos de tsunami.

Solo usa la biblioteca estándar. Se ejecuta en GitHub Actions cada 2 horas.
Con --demo genera datos de prueba sin tocar internet (solo para probar la página).
"""
import csv
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
UA = "mapa-tiendas-clima/1.0 (https://github.com/moscosoccaullajairo-wq/Trabajo-jairo-publico)"
LIMA = timezone(timedelta(hours=-5))
DEMO = "--demo" in sys.argv


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def load_stores():
    with open(os.path.join(DATA, "stores.csv"), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_json(name, default):
    path = os.path.join(DATA, name)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def geocode(stores, cache):
    """Busca en OpenStreetMap (Nominatim) solo las tiendas que aún no tienen coordenadas."""
    changed = False
    for s in stores:
        if s["id"] in cache:
            continue
        if DEMO:
            continue
        q = urllib.parse.urlencode(
            {"q": s["consulta"], "format": "json", "limit": 1, "countrycodes": "pe"}
        )
        try:
            res = json.loads(http_get("https://nominatim.openstreetmap.org/search?" + q))
            if not res:  # segundo intento: solo nombre del mall/ciudad
                q2 = urllib.parse.urlencode(
                    {"q": f'{s["ciudad"]}, {s["region"]}, Perú', "format": "json",
                     "limit": 1, "countrycodes": "pe"}
                )
                time.sleep(1.2)
                res = json.loads(http_get("https://nominatim.openstreetmap.org/search?" + q2))
                nivel = "ciudad"
            else:
                nivel = "consulta"
            if res:
                cache[s["id"]] = {
                    "lat": round(float(res[0]["lat"]), 5),
                    "lon": round(float(res[0]["lon"]), 5),
                    "precision": nivel,
                }
                changed = True
        except Exception as e:  # noqa: BLE001
            print(f"geocode fallo {s['id']}: {e}", file=sys.stderr)
        time.sleep(1.2)  # política de uso de Nominatim: máx. 1 consulta por segundo
    if changed:
        with open(os.path.join(DATA, "coords.json"), "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=1, sort_keys=True)
    return cache


def nivel_lluvia(mm24, mm6):
    # Umbrales referenciales. No equivalen a los avisos oficiales de SENAMHI.
    m = max(mm24, mm6 * 2)
    if m >= 30:
        return 3, "Muy alto"
    if m >= 10:
        return 2, "Alto"
    if m >= 1:
        return 1, "Moderado"
    return 0, "Bajo"


def clima(stores, coords):
    out = {}
    pts = [s for s in stores if s["id"] in coords]
    if not pts:
        return out, "sin coordenadas"
    now = datetime.now(LIMA)
    try:
        for i in range(0, len(pts), 20):  # lotes de 20 tiendas por consulta
            lote = pts[i:i + 20]
            q = urllib.parse.urlencode({
                "latitude": ",".join(str(coords[s["id"]]["lat"]) for s in lote),
                "longitude": ",".join(str(coords[s["id"]]["lon"]) for s in lote),
                "hourly": "precipitation,precipitation_probability",
                "current": "temperature_2m",
                "forecast_days": 2,
                "timezone": "America/Lima",
            })
            data = json.loads(http_get("https://api.open-meteo.com/v1/forecast?" + q))
            if isinstance(data, dict):
                data = [data]
            for s, d in zip(lote, data):
                times = d["hourly"]["time"]
                prec = d["hourly"]["precipitation"]
                prob = d["hourly"]["precipitation_probability"]
                ahora = now.strftime("%Y-%m-%dT%H:00")
                idx = next((k for k, t in enumerate(times) if t >= ahora), 0)
                v24 = [x or 0 for x in prec[idx:idx + 24]]
                p24 = [x or 0 for x in prob[idx:idx + 24]]
                mm24, mm6 = round(sum(v24), 1), round(sum(v24[:6]), 1)
                n, etiqueta = nivel_lluvia(mm24, mm6)
                out[s["id"]] = {
                    "mm_24h": mm24, "mm_6h": mm6,
                    "prob_max_24h": max(p24) if p24 else None,
                    "temp_c": d.get("current", {}).get("temperature_2m"),
                    "nivel": n, "nivel_txt": etiqueta,
                }
        return out, "ok"
    except Exception as e:  # noqa: BLE001
        print(f"open-meteo fallo: {e}", file=sys.stderr)
        return out, f"error: {e}"


def sismos():
    desde = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")
    q = urllib.parse.urlencode({
        "format": "geojson", "starttime": desde, "minmagnitude": 4.0,
        "minlatitude": -20, "maxlatitude": 1, "minlongitude": -84, "maxlongitude": -66,
        "orderby": "time",
    })
    try:
        d = json.loads(http_get("https://earthquake.usgs.gov/fdsnws/event/1/query?" + q))
        lista = []
        for f in d.get("features", []):
            p, (lon, lat, prof) = f["properties"], f["geometry"]["coordinates"]
            lista.append({
                "mag": p.get("mag"), "lugar": p.get("place"),
                "hora_utc": datetime.fromtimestamp(p["time"] / 1000, timezone.utc).isoformat(),
                "lat": lat, "lon": lon, "prof_km": prof, "url": p.get("url"),
            })
        return lista, "ok"
    except Exception as e:  # noqa: BLE001
        print(f"usgs fallo: {e}", file=sys.stderr)
        return [], f"error: {e}"


def tsunami():
    url = "https://www.tsunami.gov/events/xml/PHEBAtom.xml"
    try:
        root = ET.fromstring(http_get(url))
        ns = {"a": "http://www.w3.org/2005/Atom"}
        items = []
        for e in root.findall("a:entry", ns)[:8]:
            items.append({
                "titulo": (e.findtext("a:title", "", ns) or "").strip(),
                "actualizado": (e.findtext("a:updated", "", ns) or "").strip(),
                "url": (e.find("a:link", ns).get("href") if e.find("a:link", ns) is not None else url),
            })
        return items, "ok"
    except Exception as e:  # noqa: BLE001
        print(f"tsunami fallo: {e}", file=sys.stderr)
        return [], f"error: {e}"


def km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def demo_data(stores, coords):
    import random
    random.seed(7)
    cl = {}
    for s in stores:
        mm = random.choice([0, 0, 0.4, 2.5, 12, 35])
        n, t = nivel_lluvia(mm, mm / 3)
        cl[s["id"]] = {"mm_24h": mm, "mm_6h": round(mm / 3, 1), "prob_max_24h": random.randint(0, 90),
                       "temp_c": random.randint(14, 30), "nivel": n, "nivel_txt": t}
    sis = [{"mag": 5.1, "lugar": "DEMO 40 km W of Pisco", "hora_utc": datetime.now(timezone.utc).isoformat(),
            "lat": -13.7, "lon": -76.6, "prof_km": 40, "url": ""}]
    return cl, sis


def main():
    stores = load_stores()
    cache = load_json("coords.json", {})
    if DEMO and not cache:  # coordenadas aproximadas solo para la prueba
        base = {"Lima y Callao": (-12.08, -77.03), "Costa norte": (-6.5, -79.5),
                "Costa sur": (-15.5, -72.5), "Sierra y centro": (-12.5, -73.5), "Selva": (-6.0, -74.5)}
        for i, s in enumerate(stores):
            la, lo = base[s["zona"]]
            cache[s["id"]] = {"lat": la + (i % 5) * 0.03, "lon": lo + (i % 7) * 0.03, "precision": "demo"}
    else:
        cache = geocode(stores, cache)

    if DEMO:
        cl, sis = demo_data(stores, cache)
        est_cl, est_sis, ts, est_ts = "demo", "demo", [], "demo"
    else:
        cl, est_cl = clima(stores, cache)
        sis, est_sis = sismos()
        ts, est_ts = tsunami()

    tiendas = []
    for s in stores:
        c = cache.get(s["id"])
        t = {
            "id": s["id"], "nombre": s["nombre"], "zona": s["zona"], "region": s["region"],
            "ciudad": s["ciudad"], "confianza": s["confianza"],
            "lat": c["lat"] if c else None, "lon": c["lon"] if c else None,
            "precision": c["precision"] if c else None,
            "clima": cl.get(s["id"]),
        }
        if c:
            cerca = [q for q in sis if q["mag"] and km(c["lat"], c["lon"], q["lat"], q["lon"]) <= 200]
            t["sismos_200km_24h"] = len(cerca)
            t["sismo_max_cercano"] = max((q["mag"] for q in cerca), default=None)
        tiendas.append(t)

    ahora = datetime.now(timezone.utc)
    status = {
        "generado_utc": ahora.isoformat(timespec="seconds"),
        "generado_lima": ahora.astimezone(LIMA).strftime("%d/%m/%Y %H:%M"),
        "demo": DEMO,
        "fuentes": {
            "clima": {"nombre": "Open-Meteo (pronóstico por coordenadas)", "estado": est_cl},
            "sismos": {"nombre": "USGS (sismos M4.0+ últimas 24 h)", "estado": est_sis},
            "tsunami": {"nombre": "NOAA/PTWC (boletines Pacífico)", "estado": est_ts},
        },
        "enfen": load_json("enfen.json", {}),
        "tiendas": tiendas,
        "sismos": sis,
        "tsunami": ts,
    }
    out = os.path.join(DATA, "status.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=1)
    print(f"status.json: {len(tiendas)} tiendas, {sum(1 for t in tiendas if t['lat'])} con coordenadas,"
          f" clima={est_cl}, sismos={est_sis}, tsunami={est_ts}")


if __name__ == "__main__":
    main()
