# Riesgo climático y sismos · Tiendas Falabella Perú

Página pública que se actualiza sola cada 2 horas. Muestra, por tienda y por zona:

- Nivel de riesgo (bajo, medio, alto, crítico) con filtros por nivel, zona, lluvia en curso, tormenta y viento fuerte
- Lluvia prevista (ahora, 6 h, 24 h), probabilidad, ráfagas, tormenta eléctrica y granizo (Open-Meteo)
- Observación del aeropuerto más cercano, con METAR (NOAA Aviation Weather)
- Sismos M4.0+ de las últimas 24 h y cuáles están cerca de cada tienda (USGS)
- Boletines de tsunami del Pacífico (NOAA/PTWC)
- Estado de El Niño costero según el último comunicado ENFEN
- Frase simple para el gerente de tienda, pronóstico de 3 días y lluvia acumulada de 7 días
- Plan de acción sugerido por nivel, en fases (antes, durante y después), con responsable por acción
- Enlace y QR por tienda (`?t=id`), que abre solo la ficha de esa tienda
- Botón para copiar un resumen para WhatsApp

No usa IA ni consume tokens: es un script que corre en GitHub.

## Cómo funciona

1. `.github/workflows/update.yml` corre cada 2 horas y en cada cambio al repositorio.
2. `scripts/update.py` consulta las fuentes, calcula el nivel de riesgo y genera `data/status.json`.
3. El workflow publica `index.html` y `status.json` en GitHub Pages.

## Archivos que se pueden editar

| Archivo | Para qué sirve |
| --- | --- |
| `data/stores.csv` | Lista de tiendas. Agregar o quitar filas. Las coordenadas se buscan solas en OpenStreetMap |
| `data/coords.json` | Coordenadas guardadas. Si una tienda está mal ubicada, corrige aquí su `lat` y `lon` |
| `data/umbrales.json` | Umbrales que definen cada nivel (lluvia, viento, sismo). Costa y sierra/selva tienen valores distintos |
| `data/acciones.json` | Plan de acción por nivel. Es un borrador para validar por Mantenimiento y Prevención |
| `data/enfen.json` | Estado de El Niño costero. Se actualiza a mano cuando ENFEN publica un comunicado nuevo |

## Qué no cubre

- No hay fuente gratuita y oficial de descargas eléctricas en vivo para Perú. La tormenta eléctrica es probable según el pronóstico y las observaciones de aeropuertos.
- Tornados: casi no ocurren en Perú y no hay fuente oficial. Se muestran ráfagas fuertes y granizo.
- Avisos de SENAMHI, INDECI/COEN y huaicos o desborde de ríos: solo enlaces. No hay datos que se puedan leer de forma automática.

## Qué no subir a este repositorio

Este repositorio es público. No pongas aquí nombres, teléfonos de guardia, contratistas, análisis de vulnerabilidad por tienda ni datos de Faldama o SAP. Los roles de `data/acciones.json` deben ser genéricos.

## Aviso

Herramienta informativa de apoyo. No reemplaza los avisos oficiales de SENAMHI, INDECI, DHN e IGP.
