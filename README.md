# Mapa de clima y sismos · Tiendas Falabella Perú

Página pública que se actualiza sola cada 2 horas. Muestra, por tienda y por zona:

- Lluvia prevista (6 h y 24 h) y nivel de riesgo referencial (Open-Meteo)
- Sismos M4.0+ de las últimas 24 h en la región (USGS)
- Boletines de tsunami del Pacífico (NOAA/PTWC)
- Estado de El Niño costero según el último comunicado ENFEN (se edita a mano en `data/enfen.json`)

## Cómo funciona

1. `.github/workflows/update.yml` corre cada 2 horas (y en cada cambio al repositorio).
2. `scripts/update.py` consulta las fuentes y genera `data/status.json`.
3. El workflow publica `index.html` + `status.json` en GitHub Pages.

No usa IA ni consume tokens: es un script normal que corre en GitHub.

## Tiendas

La lista está en `data/stores.csv`. Para agregar o quitar una tienda, edita ese archivo.
Las coordenadas se buscan solas en OpenStreetMap la primera vez y se guardan en `data/coords.json`.
Son aproximadas (centro del mall o dirección geocodificada). Si alguna está mal ubicada,
corrígela en `data/coords.json`.

## Aviso

Herramienta informativa de apoyo. No reemplaza los avisos oficiales de SENAMHI, INDECI, DHN e IGP.
