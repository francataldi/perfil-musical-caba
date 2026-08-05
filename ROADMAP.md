# ROADMAP — Perfil musical de los barrios de CABA

> Estado de avance del proyecto. **Se actualiza al cerrar cada tarea, no al final.**
> La spec técnica está en
> [docs/especificacion_v1.md](docs/especificacion_v1.md).
>
> **Regla de oro:** no se avanza de etapa sin cumplir el gate. Si un gate falla, no se
> parchea: se degrada el diseño y se documenta el cambio.

**Última actualización:** 2026-08-05
**Etapa actual:** 5 — EDA composicional (adelantada; no depende de tener datos)
**Próximo paso:** Etapa 1 — adquisición. El núcleo matemático ya está cerrado y verificado;
las visualizaciones de la Etapa 5 necesitan datos reales para tener sentido.

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

## Etapa 1 — Adquisición ⬜

**Entregables:** `data/raw/eventos_YYYYMMDD.parquet`, `scripts/`, `docs/01_fuentes.md`

- [ ] `docs/01_fuentes.md` con la tabla de inventario de fuentes
- [ ] Esquema unificado `Evento` definido (con `id` hash estable y `scraped_at`)
- [ ] Fuente 1 — agenda cultural GCBA (la más fácil, victoria temprana)
- [ ] Fuente 2 — Songkick (API oficial)
- [ ] Fuente 3 — al menos una vía Playwright (standalone, **no** Jupyter)
- [ ] Deduplicación entre fuentes + tasa de solapamiento reportada

**Gate de salida**
- [ ] ≥ 3.000 eventos únicos tras deduplicación
- [ ] ≥ 36 meses de cobertura temporal
- [ ] ≥ 40 de los 48 barrios con al menos un evento
- [ ] Los scripts corren de cero sin intervención manual

> Si falla: degradar a panel semestral y anotarlo en el protocolo. No parchear.

---

## Etapa 2 — Geocodificación y asignación espacial ⬜

**Entregable:** `data/interim/eventos_geolocalizados.parquet` + notebook con mapa de control

- [ ] Shapefile oficial de barrios descargado e inspeccionado (¿48 polígonos? ¿qué CRS?)
- [ ] Cascada de geocodificación: USIG → Nominatim → manual
- [ ] Spatial join *point-in-polygon* con GeoPandas
- [ ] Tasa de geocodificación **por fuente** reportada
- [ ] Matriz de contigüidad *queen* `W` calculada y persistida (se reusa en Etapas 6 y 7)
- [ ] `data/processed/bloques_cv.csv` — los 5 bloques de CV espacial, persistidos

**Gate de salida**
- [ ] ≥ 85 % de eventos geocodificados
- [ ] Top 30 venues verificados **a mano**
- [ ] Mapa de control inspeccionado visualmente

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
