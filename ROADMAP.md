# ROADMAP — Perfil musical de los barrios de CABA

> Estado de avance del proyecto. **Se actualiza al cerrar cada tarea, no al final.**
> La spec técnica está en
> [docs/especificacion_v1.md](docs/especificacion_v1.md).
>
> **Regla de oro:** no se avanza de etapa sin cumplir el gate. Si un gate falla, no se
> parchea: se degrada el diseño y se documenta el cambio.

**Última actualización:** 2026-08-07
**Estado:** en pausa
**Etapa actual:** 3 — Etiquetado de géneros (la de mayor riesgo del proyecto)
**Próximo paso:** verificar a mano los top 30 venues (pendiente de la Etapa 2) y armar
`config/taxonomia_generos.yaml`.

**Entorno:** `musica-caba` creado desde `environment.yml`. Activar con
`conda activate musica-caba`. Pendiente antes de la Etapa 1: `playwright install chromium`.

---

## Etapa 0 — Diseño del estudio ✅

**Entregable:** `docs/00_protocolo.md` · **Estado:** completa (congelado 2026-08-01)

- [x] Pregunta de investigación en una oración
- [x] Unidad de observación decidida y justificada (barrio × trimestre)
- [x] Taxonomía cerrada de D = 8 macrogéneros
- [x] Métricas primaria, interpretable y de comunicación, con justificación
- [x] Tres baselines definidos (B0, B1, B2)
- [x] Esquema de validación con criterio operativo de los 5 bloques
- [x] Criterio de éxito **y** de fracaso escritos
- [x] Commiteado antes de tocar datos

**Pendientes marcados `<!-- REVISAR -->` en el protocolo:**
- [ ] Política de celdas de baja confianza (se decide en Etapa 4)
- [ ] Semilla del test de permutación (se fija en Etapa 7)

---

## Etapa 1 — Adquisición ✅

**Entregables:** `data/raw/eventos_YYYYMMDD.parquet`, `scripts/`, `docs/01_fuentes.md`

- [x] `docs/01_fuentes.md` con la tabla de inventario y **volumen estimado por fuente**
- [x] Esquema unificado `Evento` en `src/esquema.py` (`id` hash SHA-256 estable + `scraped_at`)
- [x] Fuente 1 — BA Data / `actividades-culturales` → `scripts/01_descarga_ba_data.py`
- [ ] Fuente 2 — Alternativa Teatral (opcional: el gate ya se cumple sin ella)
- [ ] Fuente 3 — Songkick, si llega la API key (solicitud pendiente)
- [ ] Deduplicación entre fuentes + tasa de solapamiento reportada *(pendiente solo si se suma una segunda fuente)*

**Gate de salida — ✅ CUMPLIDO con BA Data sola**

| Criterio | Requerido | Obtenido |
|---|---|---|
| Eventos únicos | ≥ 3.000 | **4.550** |
| Meses de cobertura | ≥ 36 | **36** |
| Barrios con evento | ≥ 40 | **45** (declarado; se confirma en Etapa 2) |
| Scripts sin intervención manual | sí | sí, idempotente verificado |

- [x] ≥ 3.000 eventos únicos tras deduplicación
- [x] ≥ 36 meses de cobertura temporal
- [x] ≥ 40 de los 48 barrios con al menos un evento
- [x] Los scripts corren de cero sin intervención manual (2 corridas → 5.397 ambas)

> **Datos obtenidos:** `data/raw/ba_data_actividades_20260805.parquet` — 5.397 eventos de
> música 2018-2022 (4.550 excluyendo la pandemia), 466 venues, 98,5 % con coordenadas.
>
> **Sesgo conocido a documentar:** la fuente es programación del Ministerio de Cultura,
> así que omite el circuito comercial. Y La Boca + San Nicolás concentran el 41 % de la
> muestra. Ver `docs/01_fuentes.md`.
>
> Sumar Alternativa Teatral sigue siendo valioso para corregir el sesgo de circuito, pero
> ya no es condición para avanzar.

---

## Etapa 2 — Geocodificación y asignación espacial ✅

**Entregables:** `data/interim/eventos_geolocalizados.parquet`,
`data/processed/bloques_cv.csv`, `data/interim/mapa_de_control.png`
**Script:** `scripts/02_asignar_barrio.py`

- [x] GeoJSON oficial de barrios descargado e inspeccionado (48 polígonos, EPSG:4326)
- [x] Spatial join *point-in-polygon* con GeoPandas (`predicate="within"`, `how="left"`)
- [x] Control cruzado contra el barrio declarado por la fuente: **97,1 % de acuerdo**
- [x] Matriz de contigüidad *queen* `W` calculada (5,2 vecinos promedio, sin islas)
- [x] `data/processed/bloques_cv.csv` — bloques de CV espacial, contiguos, persistidos
- [ ] Cascada de geocodificación USIG → Nominatim *(no hizo falta: BA Data ya trae
      coordenadas para el 98,5 %. Queda pendiente si se suma una fuente sin coordenadas)*

**Gate de salida — ✅ CUMPLIDO**

| Criterio | Requerido | Obtenido |
|---|---|---|
| Eventos geocodificados | ≥ 85 % | **98,5 %** |
| Barrios con evento (panel) | ≥ 40 | **43** |
| Eventos dentro de CABA | — | 5.315 de 5.315 (100 %) |
| Mapa de control inspeccionado | sí | sí, 3 paneles |

- [x] ≥ 85 % de eventos geocodificados
- [x] Mapa de control inspeccionado visualmente
- [x] Diagnósticos automáticos de venues (`scripts/03_verificar_venues.py`)
- [x] Top 30 venues verificados por **dos métodos independientes**
      (`scripts/04_verificar_venues_con_geocoder.py`)

**Verificación de venues — 93 % del top 30 confirmado**

| Método | Venues | Eventos | Qué detecta |
|---|---|---|---|
| Manual | 9 | 2.955 (72,6 %) | nombres que agrupan varias sedes |
| Geocoder Nominatim | 21 | 1.115 (27,4 %) | coordenadas mal puestas |
| **Confirmados** | — | **3.785 (93,0 %)** | |
| Pendientes | 5 | 285 (7,0 %) | |

La columna `metodo_de_verificacion` distingue ambos: una celda verificada por el geocoder
**no** cuenta como verificada a mano. Los dos métodos fallan en casos distintos, así que
no son intercambiables.

Pendientes (285 eventos, 7 %): `ANFITEATRO EVA PERON` (esquina sin altura),
`ESPACIO CULTURAL RESURGIMIENTO` y `MARCO DEL PONT` (formato catastral que Nominatim no
resuelve), `PARQUE DE LA CIUDAD` y `CENTRO CULTURAL ADAN BUENOS AIRES` (Nominatim los
ubica mal: 6 km y 506 m de la coordenada de BA Data respectivamente).

> **Los 30 venues más frecuentes concentran 4.070 de 5.315 eventos: el 76,6 %.**
> Verificarlos cubre tres cuartos del riesgo de error de toda la etapa.
>
> **Hallazgo mayor:** la Usina del Arte sola tiene **1.315 eventos, el 24,7 % del total**.
> El "perfil musical de La Boca" es, en los hechos, la programación de un único centro
> cultural municipal. Es un problema de validez, no de datos: va a la sección de
> limitaciones y hay que decidir cómo tratarlo antes de modelar.
>
> **Casos ambiguos, resueltos e investigados (2026-08-05):**
> - `MUSEO SIVORI` — la alerta de 323 m era ruido de geocodificación sobre una única
>   dirección (Infanta Isabel Av. 555). Los 36 eventos cayeron en Palermo. Sin acción.
> - `PARQUE DE LA CIUDAD` — 33 eventos con dos accesos reales, uno de cada lado del
>   límite Lugano/Soldati (Av. Escalada 4501 → 32 eventos en Lugano;
>   Av. F. Fernández de la Cruz 4000 → 1 evento en Soldati). **Se deja como está:** el
>   barrio es propiedad de dónde ocurrió el evento, no del nombre del venue, y el
>   point-in-polygon por evento ya aplica el criterio correcto y homogéneo. Es el MAUP
>   en miniatura y afecta a 1 evento sobre 5.315.
>
> Duplicados de nombre detectados que hay que fusionar antes de la Etapa 4:
> `CENTRO CULTURAL SAN MARTIN` / `CENTRO CULTURAL GENERAL SAN MARTIN` (182 eventos),
> `CENTRO CULTURAL ADAN BUENOSAYRES` / `... BUENOS AIRES` (65),
> `TEATRO MONTE VIEJO` / `TEATRO MONTEVIEJO`,
> `ESPACIO CULTURAL JULIAN CENTEYA` / `CENTRO CULTURAL JULIAN CENTEYA`.

> **Hallazgos de esta etapa:**
> - El control cruzado dio 71,8 % en la primera corrida. Investigado: 1.310 de los 1.458
>   desacuerdos eran **diferencias de nomenclatura**, no errores espaciales — el shapefile
>   dice `LA BOCA` y los CSV del GCBA dicen `BOCA`. Con el mapa de alias, 97,1 %.
>   El número era un diagnóstico, no un veredicto.
> - Con 5 bloques de CV el más chico quedaba con 4 barrios (< 6). Se aplicó la regla ya
>   escrita en el protocolo y **el esquema final usa 4 bloques** (17, 16, 9, 6).
> - Ningún evento cayó fuera de CABA, coherente con que la fuente sea programación
>   municipal. Cuando se sume una fuente comercial habrá que volver a mirar esto.

---

## Etapa 3 — Etiquetado de géneros ⬜

**Etapa de mayor riesgo del proyecto.**
**Entregables:** `data/interim/eventos_etiquetados.parquet`, `notebooks/02_validacion_etiquetado.ipynb`

- [ ] `config/taxonomia_generos.yaml` — fuente única de verdad, sin categorías hardcodeadas
- [ ] Cascada: Spotify → MusicBrainz/Last.fm → prior por venue → clasificador de texto → `OTRO`
- [ ] Muestra aleatoria estratificada de 200 eventos etiquetada **a mano**, sin ver la predicción
- [ ] Accuracy, kappa de Cohen y matriz de confusión calculadas

**Gate de salida**
- [ ] Accuracy ≥ 0.75 contra la muestra manual
- [ ] Ningún macrogénero con recall < 0.5
- [ ] `OTRO` < 25 % del total
- [ ] Matriz de confusión documentada y accuracy publicada en el README

> Innegociable: la validación manual no se saltea. Un modelo perfecto sobre etiquetas malas
> es basura elegante.

---

## Etapa 4 — Panel composicional ⬜

**Entregable:** `data/processed/panel_composicional.parquet`

- [ ] Agregación (barrio, trimestre, género) → matriz de conteos
- [ ] Diagnóstico de escasez: celdas con < 10 eventos, celdas con ceros, histograma
- [ ] Cierre al símplex aplicado
- [ ] Ceros tratados con reemplazo multiplicativo bayesiano (**no** sumar constante)
- [ ] Decisión sobre celdas de baja confianza tomada y escrita en el protocolo

**Gate de salida**
- [ ] Todas las filas suman 1
- [ ] Sin ceros tras el tratamiento
- [ ] Celdas de baja confianza flageadas
- [ ] Decisión de ponderación documentada

---

## Etapa 5 — EDA composicional 🔄

**Entregables:** `src/composicional.py` (con tests), `notebooks/03_eda_composicional.ipynb`

- [x] `closure()`, `geometric_mean()`, `center()` implementados a mano
- [x] `perturbation()` (⊕) y `powering()` (⊙), las operaciones del símplex
- [x] `clr()` y `clr_inv()` implementados a mano
- [x] SBP elegida con criterio sustantivo — 7 balances interpretables en `SBP_GENRES`
- [x] Base ortonormal ILR construida desde la SBP (`ilr_basis_from_sbp`)
- [x] `ilr()` e `ilr_inv()` implementados a mano
- [x] `aitchison_distance()` implementada
- [x] `variation_matrix()` — el sustituto correcto de la correlación de Pearson
- [ ] Biplot composicional (PCA sobre CLR)
- [ ] Diagramas ternarios de subcomposiciones
- [ ] Dendrograma de barrios con distancia de Aitchison
- [ ] Narrativa escrita en primera persona

**Gate de salida — `tests/`** (49 tests, todos pasando en el entorno `musica-caba`)
- [x] `ilr_inv(ilr(x)) == x` a tolerancia numérica
- [x] La base es ortonormal: `Vᵀ V = I`
- [x] La distancia de Aitchison es invariante ante perturbación
- [x] El cierre preserva las razones entre partes
- [x] ILR es una isometría: `‖ilr(x) − ilr(y)‖₂ == d_A(x, y)`
- [x] La covarianza en CLR es singular (rango D−1), lo que justifica modelar en ILR
- [x] Contrastado contra `composition-stats` (`tests/test_composicional_vs_libreria.py`)

---

## Etapa 6 — Covariables ⬜

**Entregable:** `docs/06_covariables.md` + tabla de features a nivel barrio

- [ ] Censo 2022 (INDEC) e IDECBA descargados
- [ ] Hipótesis escrita **antes** de incluir cada variable
- [ ] Distancia al microcentro calculada en EPSG:5347 (no en grados)
- [ ] MAUP documentado explícitamente

**Gate de salida**
- [ ] ≤ 7 covariables, cada una con su hipótesis
- [ ] MAUP documentado
- [ ] Sin nulos sin explicar

---

## Etapa 7 — Modelado ⬜

**Orden estricto. No se empieza por el modelo complejo.**

- [ ] **M0** — los tres baselines (B0, B1, B2). Primero, sin excepciones
- [ ] **M1** — regresión lineal multivariada en coordenadas ILR
- [ ] Tabla de coeficientes con IC y su lectura sustantiva ← el corazón del resultado
- [ ] **M2** — regresión Dirichlet (log-verosimilitud + `scipy.optimize`)
- [ ] **M3** — modelo multinivel → **ICC** (probablemente el número más importante)
- [ ] **M4** — no lineal (RF / boosting multi-output)
- [ ] I de Moran sobre residuos de M1
- [ ] Test de permutación, 1.000 iteraciones, semilla fijada

**Gate de salida**
- [ ] M1 supera B0, B1 **y** B2 en CV espacial
- [ ] Test de permutación significativo
- [ ] I de Moran sobre residuos reportada

> Si falla: resultado negativo, reportado con análisis. El criterio se escribió en la
> Etapa 0 justamente para este momento.

---

## Etapa 8 — Clustering y honestidad metodológica ⬜

- [ ] Clustering de barrios con distancia de **Aitchison** (no euclídea), Ward
- [ ] k elegido por silhouette en espacio ILR + interpretabilidad
- [ ] Mapa coroplético de "regiones musicales"
- [ ] Sección de limitaciones escrita: oferta≠demanda, falacia ecológica, sesgo de
      plataforma, MAUP, calidad del etiquetado

**Gate de salida**
- [ ] Sección de limitaciones escrita y **visible** en el README

---

## Etapa 9 — Producto y comunicación ⬜

- [ ] `README.md` completo: una oración → hallazgo con número → gráfico → reproducción →
      **limitaciones** → metodología
- [x] `environment.yml` reproducible (entorno `musica-caba`)
- [x] `pyproject.toml` con configuración de pytest y ruff
- [ ] `.env.example` con los nombres de las claves necesarias
- [ ] `app/dashboard.py` — Streamlit, mapa interactivo con selector de trimestre
- [ ] Todos los tests pasando

**Gate de salida**
- [ ] Se clona el repo, se sigue el README y funciona
