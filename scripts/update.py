#!/usr/bin/env python3
"""Genera data/status.json: clima por tienda, aeropuertos (METAR), sismos, tsunami y nivel de riesgo.

Solo usa la biblioteca estandar. Corre en GitHub Actions cada 2 horas.
Con --demo genera datos de prueba sin internet (solo para probar la pagina).
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
UA = "mapa-tiendas-clima/2.0 (https://github.com/moscosoccaullajairo-wq/Trabajo-jairo-publico)"
LIMA = timezone(timedelta(hours=-5))
DEMO = "--demo" in sys.argv
NIVELES = ["Bajo", "Medio", "Alto", "Crítico"]

# Aeropuertos de Peru con METAR (codigo OACI). Los que no respondan se ignoran.
AEROPUERTOS = ["SPJC", "SPSO", "SPQU", "SPZO", "SPQT", "SPCL", "SPTN", "SPJJ", "SPJR", "SPNC",
               "SPHI", "SPRU", "SPEO", "SPUR", "SPYL", "SPME", "SPJL", "SPHO", "SPTU", "SPST", "SPHZ"]


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def load_json(name, default):
    path = os.path.join(DATA, name)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def load_stores():
    with open(os.path.join(DATA, "stores.csv"), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def geocode(stores, cache):
    """Busca en OpenStreetMap (Nominatim) solo las tiendas que aun no tienen coordenadas."""
    changed = False
    for s in stores:
        if s["id"] in cache or DEMO:
            continue
        try:
            q = urllib.parse.urlencode({"q": s["consulta"], "format": "json", "limit": 1, "countrycodes": "pe"})
            res = json.loads(http_get("https://nominatim.openstreetmap.org/search?" + q))
            nivel = "consulta"
            if not res:
                time.sleep(1.2)
                q2 = urllib.parse.urlencode({"q": f'{s["ciudad"]}, {s["region"]}, Perú', "format": "json",
                                             "limit": 1, "countrycodes": "pe"})
                res = json.loads(http_get("https://nominatim.openstreetmap.org/search?" + q2))
                nivel = "ciudad"
            if res:
                cache[s["id"]] = {"lat": round(float(res[0]["lat"]), 5), "lon": round(float(res[0]["lon"]), 5),
                                  "precision": nivel}
                changed = True
        except Exception as e:  # noqa: BLE001
            print(f"geocode fallo {s['id']}: {e}", file=sys.stderr)
        time.sleep(1.2)  # politica de Nominatim: maximo 1 consulta por segundo
    if changed:
        with open(os.path.join(DATA, "coords.json"), "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=1, sort_keys=True)
    return cache


# ---------------------------------------------------------------- fuentes
def clima(stores, coords):
    """Open-Meteo: pronostico por coordenadas. Devuelve {id: datos} y estado."""
    out, now = {}, datetime.now(LIMA)
    pts = [s for s in stores if s["id"] in coords]
    try:
        for i in range(0, len(pts), 20):
            lote = pts[i:i + 20]
            q = urllib.parse.urlencode({
                "latitude": ",".join(str(coords[s["id"]]["lat"]) for s in lote),
                "longitude": ",".join(str(coords[s["id"]]["lon"]) for s in lote),
                "hourly": "precipitation,precipitation_probability,wind_gusts_10m,weather_code,cape",
                "current": "temperature_2m,precipitation,wind_gusts_10m,weather_code",
                "wind_speed_unit": "kmh", "forecast_days": 2, "timezone": "America/Lima",
            })
            data = json.loads(http_get("https://api.open-meteo.com/v1/forecast?" + q))
            if isinstance(data, dict):
                data = [data]
            for s, d in zip(lote, data):
                h, cur = d["hourly"], d.get("current", {})
                ahora = now.strftime("%Y-%m-%dT%H:00")
                idx = next((k for k, t in enumerate(h["time"]) if t >= ahora), 0)
                sl = slice(idx, idx + 24)
                num = lambda arr: [x or 0 for x in arr[sl]]  # noqa: E731
                pr, pb, gu, wc, ca = (num(h["precipitation"]), num(h["precipitation_probability"]),
                                      num(h["wind_gusts_10m"]), num(h["weather_code"]), num(h["cape"]))
                out[s["id"]] = {
                    "mm_24h": round(sum(pr), 1), "mm_6h": round(sum(pr[:6]), 1),
                    "mm_ahora": round(cur.get("precipitation") or 0, 1),
                    "prob_max_24h": max(pb) if pb else None,
                    "prob_max_6h": max(pb[:6]) if pb else None,
                    "rafaga_max_kmh": round(max(gu)) if gu else None,
                    "rafaga_ahora_kmh": round(cur.get("wind_gusts_10m") or 0),
                    "temp_c": cur.get("temperature_2m"),
                    "cape_max": round(max(ca)) if ca else None,
                    "tormenta_6h": any(c in (95, 96, 99) for c in wc[:6]),
                    "tormenta_24h": any(c in (95, 96, 99) for c in wc),
                    "granizo_24h": any(c in (96, 99) for c in wc),
                    "codigo_ahora": cur.get("weather_code"),
                    "horas": [{"h": h["time"][idx + k][11:13], "mm": round(pr[k], 1), "prob": pb[k]}
                              for k in range(len(pr))],
                }
        return out, "ok"
    except Exception as e:  # noqa: BLE001
        print(f"open-meteo fallo: {e}", file=sys.stderr)
        return out, f"error: {e}"


def metar():
    """Observaciones de aeropuertos (NOAA Aviation Weather)."""
    try:
        url = ("https://aviationweather.gov/api/data/metar?format=json&hours=3&ids=" + ",".join(AEROPUERTOS))
        raw = http_get(url)
        data = json.loads(raw) if raw.strip() else []
        ult = {}
        for m in data:
            k = m.get("icaoId")
            if k and (k not in ult or (m.get("obsTime") or 0) > (ult[k].get("obsTime") or 0)):
                ult[k] = m
        out = {}
        for k, m in ult.items():
            if m.get("lat") is None or m.get("lon") is None:
                continue
            wx = (m.get("wxString") or "").strip()
            out[k] = {
                "icao": k, "nombre": m.get("name") or k, "lat": m["lat"], "lon": m["lon"],
                "hora_utc": datetime.fromtimestamp(m["obsTime"], timezone.utc).isoformat(timespec="minutes")
                if m.get("obsTime") else None,
                "temp_c": m.get("temp"), "viento_kt": m.get("wspd"), "rafaga_kt": m.get("wgst"),
                "vis_mi": m.get("visib"), "fenomeno": wx, "raw": m.get("rawOb"),
                "tormenta": "TS" in wx, "lluvia": any(x in wx for x in ("RA", "DZ", "SH")),
            }
        return out, "ok" if out else "error: sin observaciones"
    except Exception as e:  # noqa: BLE001
        print(f"metar fallo: {e}", file=sys.stderr)
        return {}, f"error: {e}"


def sismos():
    desde = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")
    q = urllib.parse.urlencode({
        "format": "geojson", "starttime": desde, "minmagnitude": 4.0, "minlatitude": -20, "maxlatitude": 1,
        "minlongitude": -84, "maxlongitude": -66, "orderby": "time",
    })
    try:
        d = json.loads(http_get("https://earthquake.usgs.gov/fdsnws/event/1/query?" + q))
        lista = []
        for f in d.get("features", []):
            p, (lon, lat, prof) = f["properties"], f["geometry"]["coordinates"]
            lista.append({"mag": p.get("mag"), "lugar": p.get("place"),
                          "hora_utc": datetime.fromtimestamp(p["time"] / 1000, timezone.utc).isoformat(),
                          "lat": lat, "lon": lon, "prof_km": prof, "url": p.get("url")})
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
            lk = e.find("a:link", ns)
            items.append({"titulo": (e.findtext("a:title", "", ns) or "").strip(),
                          "actualizado": (e.findtext("a:updated", "", ns) or "").strip(),
                          "url": lk.get("href") if lk is not None else url})
        return items, "ok"
    except Exception as e:  # noqa: BLE001
        print(f"tsunami fallo: {e}", file=sys.stderr)
        return [], f"error: {e}"


# ---------------------------------------------------------------- riesgo
def evaluar(s, c, apto, sis_cerca, um):
    """Devuelve (nivel 0-3, motivos, banderas). Umbrales en data/umbrales.json."""
    u = um["costa"] if s["zona"] in um["zonas_costa"] else um["andes_selva"]
    nivel, motivos = 0, []

    def sube(n, texto):
        nonlocal nivel
        nivel = max(nivel, n)
        motivos.append((n, texto))

    if c:
        mm24, mm6 = c["mm_24h"], c["mm_6h"]
        if mm24 >= u["critico_mm24"]:
            sube(3, f"Lluvia prevista de {mm24} mm en 24 h")
        elif mm24 >= u["alto_mm24"]:
            sube(2, f"Lluvia prevista de {mm24} mm en 24 h")
        elif mm24 >= u["medio_mm24"]:
            sube(1, f"Lluvia prevista de {mm24} mm en 24 h")
        if mm6 >= u["critico_mm6"]:
            sube(3, f"{mm6} mm previstos en las próximas 6 h")
        elif mm6 >= u["alto_mm6"]:
            sube(2, f"{mm6} mm previstos en las próximas 6 h")
        if c["mm_ahora"] >= 0.1:
            sube(2 if c["mm_ahora"] >= um["lluvia_ahora_alto_mm_h"] else 1, f"Lloviendo ahora ({c['mm_ahora']} mm/h)")
        if c["tormenta_6h"]:
            sube(2, "Tormenta eléctrica probable en las próximas 6 h")
        elif c["tormenta_24h"]:
            sube(1, "Tormenta eléctrica probable en las próximas 24 h")
        if c["granizo_24h"]:
            sube(2, "Granizo posible")
        g = max(c["rafaga_max_kmh"] or 0, c["rafaga_ahora_kmh"] or 0)
        if g >= u["critico_viento"]:
            sube(3, f"Ráfagas de hasta {g} km/h")
        elif g >= u["alto_viento"]:
            sube(2, f"Ráfagas de hasta {g} km/h")
        elif g >= u["medio_viento"]:
            sube(1, f"Ráfagas de hasta {g} km/h")
    if apto and apto["km"] <= um["aeropuerto_radio_km"] and apto.get("obs"):
        o = apto["obs"]
        if o["tormenta"]:
            sube(2, f"Aeropuerto {o['icao']} ({apto['km']} km): tormenta eléctrica en curso")
        elif o["lluvia"]:
            sube(1, f"Aeropuerto {o['icao']} ({apto['km']} km): lluvia en curso")
    sm = um["sismo"]
    for q in sis_cerca:
        d = q["km"]
        if q["mag"] >= sm["critico_mag"] and d <= sm["alto_km"]:
            sube(3, f"Sismo M{q['mag']} a {d} km")
        elif q["mag"] >= sm["alto_mag"] and d <= sm["alto_km"]:
            sube(2, f"Sismo M{q['mag']} a {d} km")
        elif q["mag"] >= sm["medio_mag"] and d <= sm["medio_km"]:
            sube(1, f"Sismo M{q['mag']} a {d} km")
    motivos.sort(key=lambda x: -x[0])
    flags = {
        "lloviendo": bool(c and c["mm_ahora"] >= 0.1) or bool(apto and apto.get("obs") and apto["obs"]["lluvia"]
                                                              and apto["km"] <= um["aeropuerto_radio_km"]),
        "tormenta": bool(c and c["tormenta_6h"]) or bool(apto and apto.get("obs") and apto["obs"]["tormenta"]
                                                         and apto["km"] <= um["aeropuerto_radio_km"]),
        "granizo": bool(c and c["granizo_24h"]),
        "viento": bool(c and (c["rafaga_max_kmh"] or 0) >= u["alto_viento"]),
    }
    return nivel, [m[1] for m in motivos], flags


def aeropuerto_cercano(lat, lon, obs):
    mejor = None
    for o in obs.values():
        d = km(lat, lon, o["lat"], o["lon"])
        if mejor is None or d < mejor["km"]:
            mejor = {"icao": o["icao"], "nombre": o["nombre"], "km": round(d), "obs": o}
    return mejor


# ---------------------------------------------------------------- demo
def demo_fuentes(stores, coords):
    import random
    random.seed(11)
    cl = {}
    for s in stores:
        mm = random.choice([0, 0, 0.3, 2, 6, 14, 38])
        horas = [{"h": f"{(datetime.now(LIMA).hour + k) % 24:02d}", "mm": round(max(0, mm / 6 * random.random() * 2), 1),
                  "prob": random.randint(0, 95)} for k in range(24)]
        cl[s["id"]] = {"mm_24h": mm, "mm_6h": round(mm / 3, 1), "mm_ahora": random.choice([0, 0, 0, 0.6, 3.1]),
                       "prob_max_24h": random.randint(0, 95), "prob_max_6h": random.randint(0, 95),
                       "rafaga_max_kmh": random.randint(15, 80), "rafaga_ahora_kmh": random.randint(5, 40),
                       "temp_c": random.randint(14, 30), "cape_max": random.randint(0, 1500),
                       "tormenta_6h": random.random() < .12, "tormenta_24h": random.random() < .25,
                       "granizo_24h": random.random() < .1, "codigo_ahora": 3, "horas": horas}
    ob = {}
    for k, (n, la, lo) in {"SPJC": ("Jorge Chávez, Lima", -12.02, -77.11), "SPUR": ("Piura", -5.21, -80.62),
                           "SPHI": ("Chiclayo", -6.79, -79.83), "SPRU": ("Trujillo", -8.08, -79.11),
                           "SPQU": ("Arequipa", -16.34, -71.57), "SPQT": ("Iquitos", -3.78, -73.31)}.items():
        ts = random.random() < .3
        ob[k] = {"icao": k, "nombre": n, "lat": la, "lon": lo, "hora_utc": datetime.now(timezone.utc).isoformat(timespec="minutes"),
                 "temp_c": 22, "viento_kt": 8, "rafaga_kt": 15 if ts else None, "vis_mi": 6, "fenomeno": "TSRA" if ts else "",
                 "raw": f"{k} DEMO", "tormenta": ts, "lluvia": ts}
    sis = [{"mag": 5.1, "lugar": "DEMO 40 km W of Pisco", "hora_utc": datetime.now(timezone.utc).isoformat(),
            "lat": -13.7, "lon": -76.6, "prof_km": 40, "url": ""}]
    return cl, ob, sis


# ---------------------------------------------------------------- main
def main():
    stores = load_stores()
    um = load_json("umbrales.json", {})
    cache = load_json("coords.json", {})
    cache = geocode(stores, cache)
    if DEMO and not cache:
        for i, s in enumerate(stores):
            cache[s["id"]] = {"lat": -12.0 - i * 0.2, "lon": -77.0 + (i % 6) * 0.3, "precision": "demo"}

    if DEMO:
        cl, ob, sis = demo_fuentes(stores, cache)
        ts, est = [], {"clima": "demo", "metar": "demo", "sismos": "demo", "tsunami": "demo"}
    else:
        cl, e1 = clima(stores, cache)
        ob, e2 = metar()
        sis, e3 = sismos()
        ts, e4 = tsunami()
        est = {"clima": e1, "metar": e2, "sismos": e3, "tsunami": e4}

    ahora = datetime.now(timezone.utc)
    tiendas = []
    for s in stores:
        c = cache.get(s["id"])
        t = {"id": s["id"], "nombre": s["nombre"], "zona": s["zona"], "region": s["region"], "ciudad": s["ciudad"],
             "confianza": s["confianza"], "lat": c["lat"] if c else None, "lon": c["lon"] if c else None,
             "precision": c["precision"] if c else None, "clima": cl.get(s["id"])}
        apto, cerca = None, []
        if c:
            apto = aeropuerto_cercano(c["lat"], c["lon"], ob) if ob else None
            for q in sis:
                d = round(km(c["lat"], c["lon"], q["lat"], q["lon"]))
                if q["mag"] and d <= 200:
                    h = round((ahora - datetime.fromisoformat(q["hora_utc"])).total_seconds() / 3600, 1)
                    cerca.append({"mag": q["mag"], "km": d, "lugar": q["lugar"], "hace_h": h})
            cerca.sort(key=lambda x: -x["mag"])
        t["aeropuerto"] = apto
        t["sismos_cerca"] = cerca[:3]
        if t["clima"] is None and not (apto and apto.get("obs")):
            t["nivel"], t["motivos"], t["flags"] = None, ["Sin datos en esta actualización"], {}
        else:
            n, mot, fl = evaluar(s, t["clima"], apto, cerca, um)
            t["nivel"], t["motivos"], t["flags"] = n, mot, fl
        t["nivel_txt"] = NIVELES[t["nivel"]] if t["nivel"] is not None else "Sin datos"
        tiendas.append(t)

    cuenta = {k: sum(1 for t in tiendas if t["nivel"] == i) for i, k in enumerate(NIVELES)}
    cuenta["Sin datos"] = sum(1 for t in tiendas if t["nivel"] is None)
    status = {
        "generado_utc": ahora.isoformat(timespec="seconds"),
        "generado_lima": ahora.astimezone(LIMA).strftime("%d/%m/%Y %H:%M"),
        "demo": DEMO,
        "fuentes": {
            "clima": {"nombre": "Open-Meteo (pronóstico por tienda)", "estado": est["clima"]},
            "metar": {"nombre": "NOAA (METAR de aeropuertos)", "estado": est["metar"]},
            "sismos": {"nombre": "USGS (sismos M4.0+ en 24 h)", "estado": est["sismos"]},
            "tsunami": {"nombre": "NOAA/PTWC (boletines Pacífico)", "estado": est["tsunami"]},
        },
        "enfen": load_json("enfen.json", {}),
        "acciones": load_json("acciones.json", {}),
        "resumen": cuenta,
        "tiendas": tiendas,
        "sismos": sis,
        "tsunami": ts,
    }
    with open(os.path.join(DATA, "status.json"), "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=1)
    print(f"status.json: {len(tiendas)} tiendas | {cuenta} | fuentes: {est}")


if __name__ == "__main__":
    main()
