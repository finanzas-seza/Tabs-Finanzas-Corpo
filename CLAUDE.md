# CLAUDE.md

## Reglas

- Responde en español.
- No modifiques datos, cifras, fórmulas ni cálculos. Solo diseño y estructura.
- No quites la etiqueta `<meta name="robots" content="noindex, nofollow">` de `index.html`.
- No agregues librerías externas sin preguntar primero.
- Haz cambios pequeños, uno por vez, e indica qué archivo y qué líneas se tocaron.
- No hagas `git push`, force push ni cambies de rama.

## Estructura del proyecto

Sitio estático de tableros financieros de Grupo SEZA (HTML autocontenido, sin build).

- `index.html`: portada. Es HTML + CSS en línea, sin JavaScript. Tiene un grid de 4 tarjetas que enlazan con rutas relativas a los tableros. La insignia "4 tableros" está escrita a mano, y el color de cada tarjeta depende de su orden (`nth-child`).
- `Auditoria_Nomina_Facturado_GSG.html`: auditoría de nómina vs. facturado de GSG.
- `Auditoria_Nomina_Facturado_SEZA.html`: auditoría de nómina vs. facturado de SEZA. Usa Chart.js.
- `Auditoria_Nomina_Facturado_SHIP.html`: auditoría de nómina vs. facturado de SHIP. Usa Chart.js.
- `Tablero_Cobranza_Calendario_VF.html`: tablero de cobranza con calendario de seguimiento (~2.5 MB, datos incrustados).
- `assets/chart.umd.js`: copia local de Chart.js. Si no carga, las páginas SEZA y SHIP usan el CDN de cdnjs (Chart.js 4.4.1) como respaldo.
