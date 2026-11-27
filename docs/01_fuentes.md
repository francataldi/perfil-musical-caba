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

| Fuente | Método | Key | Cobertura **real** | Coords | Barrio | Eventos de música | Estado |
|---|---|---|---|---|---|---|---|
| BA Data — `actividades-culturales` | API CKAN + CSV | no | 2018–2022 | 98,5 % | sí | **5.397** (4.550 sin 2020-21) | ✅ **descargada** |
| BA Data — `eventos-direccion-general-musica` | CSV | no | solo 2017 | sí | sí | 80 | ✅ verificada, no usada |
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

### Volumen real, medido descargando los archivos completos

| Año | Filas totales | De música | Con fecha y venue | Columna disciplina | Columna fecha | `fecha_fin` |
|---|---|---|---|---|---|---|
| 2017 | 752 | — | — | *no tiene* | *no tiene* | no |
| 2018 | 11.920 | 1.574 | 1.449 | `disciplina_artistica` | `fecha_inicio` | no |
| 2019 | 15.066 | 2.129 | 2.117 | `disciplina_artistica` | `fecha_inicio` | no |
| 2020 | 5.682 | 755 | 650 | `disciplina` | `fecha_ini` | sí |
| 2021 | 2.920 | 502 | 392 | `disciplina` | `fecha_ini` | sí |
| 2022 | 15.007 | 1.337 | 1.269 | `disciplina` | `fecha_ini` | sí |

**Resultado tras deduplicar: 5.397 eventos de música (2018-01 a 2022-12), 466 venues
distintos, 98,5 % con coordenadas.** Excluyendo 2020–2021: **4.550 eventos, 36 meses,
45 barrios**. El gate de la Etapa 1 se cumple con esta sola fuente.

> ⚠️ **Corrección registrada (2026-08-05).** La primera estimación de este documento decía
> "~150–200 eventos de música". Estaba mal por un factor de 25: se había estimado leyendo
> un *preview* del CSV en vez de descargar el archivo. **Lección: nunca estimes el volumen
> de una fuente desde un preview. Bajá el archivo y contá.**

### Trampas del dataset, verificadas al descargarlo

1. **El esquema cambia entre años.** 2018–2019 usan `disciplina_artistica`,
   `fecha_inicio` y `establecimiento`; 2020–2022 usan `disciplina`, `fecha_ini`,
   `fecha_fin` y `lugar`. Es la misma serie con nombres distintos. Se resuelve con el
   diccionario `NOMBRES_ALTERNATIVOS_POR_CAMPO` del script.
2. **`'barrio '` en 2019 tiene un espacio al final del nombre de la columna.**
   `df["barrio"]` tira `KeyError` y el espacio es invisible al imprimir las columnas.
3. **Los archivos anuales se solapan.** El de 2019 llega hasta diciembre de 2020 y el de
   2022 arranca en enero de 2021: 480 eventos aparecen dos veces.
4. **La columna `id` es un número de fila** (1, 2, 3, … N), no un identificador estable.
   Si el GCBA republica el archivo reordenado, todos los ids cambian. Por eso el hash del
   proyecto se construye del contenido (`fecha` + `titulo` + `venue`), no de esa columna.
5. **Los faltantes vienen como el string `"NA"`**, no como campo vacío.

### Sesgos conocidos de esta fuente

> **No es la agenda cultural de la ciudad.** Es la programación propia del Ministerio de
> Cultura: ciclos, actividades gratuitas, espacios públicos y estatales. Sobrerrepresenta
> lo gratuito y estatal, y **omite el circuito comercial** (Niceto, La Trastienda, clubes,
> milongas privadas, peñas). Es sesgo sistemático, no ruido: va a la sección de
> limitaciones del README.

**Concentración territorial a vigilar:** La Boca tiene 1.245 de los 4.550 eventos (27 %),
casi con seguridad por la Usina del Arte. San Nicolás suma 619. Dos barrios concentran el
41 % de la muestra. Esto va a dominar cualquier modelo si no se trata, y conecta
directamente con el riesgo "Palermo/Recoleta aplastan la señal" del documento de
especificación — solo que el barrio que aplasta resultó ser otro.

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

- **Solicitada el:** _(completar al pedirla)_
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
