# Inventario de fuentes — Etapa 1

**Última actualización:** 2026-08-05

> El propósito de este documento es dejar escrito el **volumen estimado de cada fuente
> antes de invertir tiempo en escribir su scraper**. La lección se aprendió en carne
> propia con BA Data: parecía la fuente principal y aporta el 7% del gate.
>
> Regla de acceso: se prueba siempre el escalón más alto primero.
> `API oficial → dataset descargable → scraping HTML → navegador automatizado`.
> Cada escalón es más frágil que el anterior.

---

## Tabla de inventario

| Fuente | Método | Key | Cobertura **real** | Coords | Barrio | Eventos de música (est.) | Estado |
|---|---|---|---|---|---|---|---|
| BA Data — `actividades-culturales` | API CKAN + CSV | no | 2017–2022, parcial | sí | sí | ~150–200 | ✅ verificada |
| BA Data — `eventos-direccion-general-musica` | CSV | no | solo 2017 | sí | sí | 80 | ✅ verificada |
| BA Data — `espacios-culturales` | API CKAN + CSV | no | padrón vigente | sí | sí | — (venues, no eventos) | 🔍 sin explorar |
| Alternativa Teatral | scraping HTML | no | archivo histórico por sala | no | no | **a medir** | 🔍 sondeo pendiente |
| Songkick | API oficial | **sí** | histórico por venue | sí | no | a medir | ⏳ key solicitada |
| Bandsintown | API / scraping | sí | histórico por artista | sí | no | a medir | ⬜ sin evaluar |
| Passline / Venti | scraping (probable JS) | no | probablemente solo futuro | no | no | a medir | ⬜ sin evaluar |

Leyenda: ✅ verificada · 🔍 pendiente de sondeo · ⏳ bloqueada por terceros · ⬜ sin evaluar

---

## 1. BA Data (Gobierno de la Ciudad)

**Portal:** `data.buenosaires.gob.ar` · **Software:** CKAN · **Sin key, sin login.**

### Endpoints de la API

```
https://data.buenosaires.gob.ar/api/3/action/package_list
https://data.buenosaires.gob.ar/api/3/action/package_show?id=<slug>
https://data.buenosaires.gob.ar/api/3/action/package_search?q=<query>
```

Lo que se aprende acá sirve para cualquier portal CKAN, incluido `datos.gob.ar`.

**Detalle técnico:** las URLs del tipo `/dataset/<slug>/resource/<id>/download` responden
**302** y redirigen al CDN (`cdn.buenosaires.gob.ar`). `requests` sigue redirects por
defecto, así que no hay que hacer nada especial — pero conviene saberlo para no
confundirse al depurar.

### `actividades-culturales` — fuente de práctica y control

21 recursos, un archivo por año en CSV, XLSX, GeoJSON y shapefile.

**Cobertura real, medida:** 2017, 2018, 2019, 2020, 2021, 2022. **No hay 2023 en adelante.**

Columnas del CSV:

```
Modalidad, actividad, descripcion_actividad, lugar, direccion, calle, altura,
barrio, comuna, fecha_ini, fecha_fin, tipo, tipo_actividad, disciplina,
publico_objetivo, se_suspende_por_lluvia, Gratuita, long, lat, Links, id
```

Lo relevante:
- **`disciplina`** toma valores como `MÚSICA`, `ARTES VISUALES`, `ARTES ESCÉNICAS`,
  `CINE Y AUDIOVISUAL`, `LITERATURA`, `MIXTO`, `OTROS`. Permite filtrar a música
  directamente.
- **`barrio` y `comuna` ya vienen asignados.** No se van a usar como verdad: se re-derivan
  por *point-in-polygon* en la Etapa 2, y este campo queda como **control cruzado** del
  propio spatial join. Es una validación gratis.
- `fecha_ini` / `fecha_fin`: **ojo, muchas filas son actividades de larga duración**
  (una muestra de tres meses), no eventos puntuales. Decisión pendiente en el Paso 3.

**Volumen medido:** 2019 tiene 275 filas totales, ~40–50 de música, **todas de enero**
(programación de verano). 2022 tiene ~600 filas cubriendo ago-2021 a oct-2022.

> ⚠️ **Este dataset no es la agenda cultural de la ciudad.** Es la programación propia del
> Ministerio de Cultura: ciclos de verano, actividades gratuitas, espacios públicos.
> Sobrerrepresenta lo gratuito y estatal, y **omite por completo el circuito comercial**
> (Niceto, La Trastienda, clubes, milongas privadas, peñas). Esto es sesgo sistemático,
> no ruido, y va derecho a la sección de limitaciones del README.

### `eventos-direccion-general-musica` — dataset de práctica

Un solo CSV útil: `calendario-de-eventos-dir-gral-de-musica.csv`. **80 filas, todas de
2017.** Inútil como fuente, ideal para practicar: es chico y ya trae dos defectos típicos.

```
long, lat, evento, fecha_desde, fecha_hasta, dia_sem, descripcion, direccion,
piso_dpto, barrio, comuna, codigo_postal, codigo_postal_arg, observaciones
```

Defectos detectados, que sirven de ejercicio:
1. Los faltantes vienen como el **string `"NA"`**, no como null. Sin `na_values=["NA"]`,
   pandas cree que `observaciones` está llena de datos.
2. Las primeras filas repiten la **misma `lat` con `long` distintas** para el mismo venue
   (Sarmiento 1551). Es un error de la fuente y es exactamente lo que un mapa detecta en
   cinco segundos y una tabla esconde durante días.

### `espacios-culturales` — sin explorar

Padrón de espacios culturales de la ciudad con coordenadas y barrio. No aporta eventos,
pero sirve para la covariable **venues per cápita** de la Etapa 6 y como catálogo de
salas a recorrer en el scraping de Alternativa Teatral.

---

## 2. Alternativa Teatral — fuente de volumen

**URL:** `alternativateatral.com` · **Método:** scraping HTML · **Sin key.**

**El hallazgo clave:** tiene **archivo histórico por sala**, accesible con el patrón

```
https://www.alternativateatral.com/teatroNNN-<slug>?archivo=t
```

Ejemplos verificados: `teatro54-espacio-ift`, `teatro94-patio-de-actores`,
`teatro467-centro-cultural-de-la-cooperacion`, `teatro509-teatro-nacional-cervantes`.

Es la única vía identificada hasta ahora que da **profundidad temporal real**. Por eso
pasa a ser la fuente principal de volumen.

**Pendientes antes de escribir el scraper:**
- [ ] Leer `alternativateatral.com/robots.txt`
- [ ] Ctrl+U sobre una página de archivo: ¿el contenido está en el HTML crudo, o lo
      genera JavaScript? Define si es escalón 3 (`beautifulsoup4`) o 4 (`playwright`).
- [ ] Sondeo sobre 2–3 salas: cuántos eventos hay, qué campos, cuán atrás llega
- [ ] Verificar si distingue música de teatro, o si hay que inferirlo del título

**Sesgo esperado:** el sitio es de artes escénicas. La música aparece pero no es su foco,
así que sobrerrepresenta salas y centros culturales por sobre bares, clubes y boliches.

---

## 3. Songkick — bloqueada por terceros

**API oficial**, requiere key. La solicitud tarda **hasta 30 días hábiles**.

- **Solicitada el:** _(completar cuando Franco aplique)_
- **Reclamar a partir del:** _(30 días hábiles después)_

Decisión tomada: se aplica y se sigue sin ella. El proyecto no depende de esta fuente.

Si la key llega, la API expone gigografías por venue y por artista, lo cual daría
histórico limpio y con coordenadas. Sería la mejor fuente del proyecto — pero no se puede
planificar contando con ella.

---

## 4. Bandsintown, Passline, Venti — sin evaluar

Candidatas de segunda ronda. Passline y Venti son ticketeras: probablemente solo publican
eventos **futuros**, lo cual las vuelve inútiles para un panel histórico salvo que se
empiece a recolectar hacia adelante. Verificarlo antes de invertir tiempo.

---

## Riesgo abierto principal

El gate de la Etapa 1 pide **3.000 eventos, 36 meses, 40 barrios**. BA Data aporta ~200
eventos de música y termina en 2022. Todo el resto depende de que el archivo histórico de
Alternativa Teatral tenga volumen — cosa que **todavía no está medida**.

**Plan B, decidido de antemano** (2026-08-05): si no se llega a 3.000, se mantiene el
objeto de estudio (música, macrogéneros) y se degrada el grano temporal a semestral o
anual, bajando el umbral de eventos por celda. Se anota como enmienda al protocolo, igual
que se hizo con la exclusión de la pandemia. **No se relaja el umbral a ojo ni se cambia
la pregunta de investigación para que dé.**
