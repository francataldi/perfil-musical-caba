# Especificación: Perfil musical de los barrios de CABA
### Regresión composicional de la oferta de música en vivo sobre covariables socioterritoriales

**Versión:** 1.0
**Autor:** Franco Cataldi
**Estado:** Especificación — ninguna fase ejecutada

---

## 0. Resumen ejecutivo

Construyo, para cada barrio de la Ciudad Autónoma de Buenos Aires, un **vector composicional** que describe qué proporción de la oferta de música en vivo corresponde a cada macrogénero, y modelo ese vector en función de covariables censales y territoriales.

**No es un clasificador de gustos individuales.** La unidad de análisis es el barrio, el target vive en el símplex, y la conclusión legítima es sobre oferta territorial, no sobre preferencia personal. Esta distinción es el eje metodológico del proyecto y se documenta explícitamente (ver Fase 8).

**Qué demuestra el proyecto:**
- Pipeline completo: scraping → geocodificación → etiquetado → modelado → despliegue
- Estadística composicional (geometría de Aitchison), que es matemáticamente no trivial y está prácticamente ausente de los portfolios de DS
- Manejo correcto de autocorrelación espacial y validación cruzada espacial
- Honestidad metodológica sobre falacia ecológica y MAUP

---

## 1. Restricción central del diseño: el tamaño muestral

**El problema.** CABA tiene 48 barrios y 15 comunas. Con n = 48 y un target de dimensión D−1, cualquier modelo con más de ~4 covariables sobreajusta. Esto no se arregla con regularización sola: hay que generar observaciones.

**La solución: estructura de panel.** La unidad de observación no es el barrio, es el **barrio × trimestre**. Si cubro 3 años de eventos, obtengo:

```
n = 48 barrios × 12 trimestres = 576 observaciones
```

Esto habilita:
- Modelos con más covariables sin sobreajustar
- Efectos aleatorios por barrio (modelo multinivel), que separan varianza entre-barrios de varianza intra-barrio
- Estacionalidad como señal (¿el folklore se concentra en invierno? ¿los festivales al aire libre en verano?)

**Regla dura:** los barrios con menos de 10 eventos en un trimestre se marcan como observación de baja confianza y se ponderan o excluyen según lo definido en Fase 3. No se imputan silenciosamente.

**Chequeo de viabilidad obligatorio (gate de Fase 1):** si tras el scraping tengo menos de 3.000 eventos totales geolocalizados, el diseño de panel trimestral no cierra y hay que degradar a panel semestral o anual. Este chequeo se hace **antes** de escribir una línea de modelado.

---

## 2. Fase 0 — Definición del problema y protocolo de validación

**Se completa antes de descargar un solo dato.** Escribo esto primero y no lo modifico después de ver resultados.

### 2.1 Pregunta de investigación

> ¿En qué medida la composición por género de la oferta de música en vivo de un barrio de CABA es explicable por sus características demográficas, socioeconómicas y de accesibilidad?

### 2.2 Taxonomía de géneros (D categorías)

Defino de antemano una taxonomía cerrada y mutuamente excluyente. Propuesta inicial (D = 8):

| Código | Macrogénero | Incluye |
|---|---|---|
| `ROCK` | Rock / indie / punk | rock nacional, indie, punk, hardcore, post-punk |
| `TROP` | Tropical / urbano | cumbia, reggaetón, trap, RKT, cuarteto |
| `FOLK` | Folklore / raíz | folklore argentino, chacarera, peña, música andina |
| `TANG` | Tango | tango, milonga, orquesta típica |
| `JAZZ` | Jazz / blues | jazz, blues, fusión, improvisada |
| `ELEC` | Electrónica | techno, house, drum & bass, ambient |
| `CLAS` | Clásica / contemporánea | orquestal, cámara, ópera, contemporánea |
| `OTRO` | Otros | reggae, metal, pop internacional, world, no clasificable |

**Justificación de D = 8:** con D categorías, el espacio ILR tiene D−1 = 7 dimensiones. Con n = 576 observaciones de panel, la relación observaciones/parámetros es holgada. Si `OTRO` supera el 25% del total, la taxonomía está mal calibrada y se revisa antes de seguir.

### 2.3 Métricas definidas ex ante

**Métrica primaria:** RMSE en coordenadas ILR (error euclídeo en el espacio transformado).

**Métrica interpretable:** distancia de Aitchison media entre composición predicha y observada.

$$d_A(\mathbf{x}, \mathbf{y}) = \sqrt{\sum_{i=1}^{D}\left(\log\frac{x_i}{g(\mathbf{x})} - \log\frac{y_i}{g(\mathbf{y})}\right)^2}$$

donde $g(\cdot)$ es la media geométrica.

**Métrica de negocio/comunicación:** error absoluto medio en puntos porcentuales por género, para el README.

### 2.4 Baselines obligatorios (se implementan ANTES que cualquier modelo)

| Baseline | Descripción | Rol |
|---|---|---|
| B0 | Composición global cerrada (media geométrica de todos los barrios) para todos | Piso absoluto |
| B1 | Composición de la comuna a la que pertenece el barrio | Test de si el barrio agrega algo sobre la comuna |
| B2 | Composición del barrio en el trimestre anterior (persistencia) | Test de si las covariables agregan algo sobre la inercia |

**Criterio de éxito:** el modelo debe superar B0, B1 **y** B2 en validación espacial. Si solo supera B0, el proyecto no encontró señal y eso se reporta como tal.

### 2.5 Esquema de validación

**Prohibido k-fold aleatorio.** Hay autocorrelación espacial (barrios vecinos se parecen) y temporal (panel). Uso:

- **CV espacial por bloques:** agrupo barrios en 5 bloques geográficamente contiguos; cada fold deja un bloque afuera completo. Esto es el análogo espacial del walk-forward de series temporales.
- **CV temporal:** para evaluar B2 y el componente dinámico, hold-out de los últimos 2 trimestres.
- **Test de permutación:** permuto aleatoriamente la asignación de covariables a barrios 1.000 veces y comparo el error del modelo real contra la distribución nula. Si el modelo real no está en la cola, no hay señal.

---

## 3. Fase 1 — Adquisición de datos

### 3.1 Fuentes de eventos

| Fuente | URL | Método | Prioridad |
|---|---|---|---|
| Agenda cultural GCBA | `data.buenosaires.gob.ar` | API / CSV | Alta |
| Agentes culturales georreferenciados | `datos.gob.ar` | CSV | Alta |
| Songkick | `songkick.com` | API oficial | Alta |
| Bandsintown | `bandsintown.com` | API / scraping | Media |
| Alternativa Teatral | `alternativateatral.com` | Playwright | Media |
| Passline / Venti | — | Playwright | Media |
| Google Places (venues) | Places API | API | Complemento |

### 3.2 Esquema de datos crudo

```python
Evento = {
    "id": str,                 # hash estable de (fuente, id_fuente)
    "fuente": str,
    "fecha": datetime,
    "titulo": str,
    "artistas": list[str],
    "venue_nombre": str,
    "venue_direccion": str,
    "venue_lat": float | None,
    "venue_lon": float | None,
    "descripcion": str | None,
    "url": str,
    "scraped_at": datetime,
}
```

### 3.3 Deduplicación

El mismo recital aparece en varias fuentes. Clave de deduplicación: `(fecha, venue_normalizado, artista_principal_normalizado)`. Normalización con `unidecode` + lowercase + eliminación de sufijos societarios. Fuzzy matching con `rapidfuzz` a umbral 90 para nombres de venue.

**Métrica a reportar:** tasa de duplicados detectados por par de fuentes. Es un dato interesante en sí para el EDA.

### 3.4 Nota de entorno

Playwright con API síncrona **no corre dentro de Jupyter** (conflicto de event loop). Todo el scraping va en scripts standalone ejecutados desde terminal, que persisten a `data/raw/*.parquet`. Los notebooks solo leen.

### 3.5 Gate de fase

- [ ] ≥ 3.000 eventos únicos tras deduplicación
- [ ] ≥ 36 meses de cobertura temporal
- [ ] ≥ 40 de los 48 barrios con al menos un evento

Si falla, se degrada la granularidad temporal antes de seguir.

---

## 4. Fase 2 — Geocodificación y asignación a barrio

### 4.1 Pipeline

1. Descargar el shapefile oficial de barrios: `data.buenosaires.gob.ar/dataset/barrios`
2. Geocodificar direcciones sin coordenadas: **USIG (GCBA)** como primera opción — es el geocodificador oficial de la Ciudad y funciona mucho mejor con el formato de direcciones porteñas que Nominatim. Nominatim como fallback.
3. Point-in-polygon con GeoPandas `sjoin`
4. Proyección: EPSG:5347 (POSGAR 2007 / Argentina Faja 5) para cualquier cálculo métrico. **No calcular distancias en EPSG:4326.**

### 4.2 Control de calidad

- Tasa de geocodificación exitosa por fuente (reportar)
- Revisión manual de los 30 venues con más eventos (concentran la mayor parte de la señal; un error ahí contamina todo)
- Eventos fuera del polígono de CABA → descartar y contar

---

## 5. Fase 3 — Etiquetado de géneros

Esta es la fase de mayor riesgo de error silencioso. Los eventos no vienen con género limpio.

### 5.1 Estrategia en cascada

1. **Spotify Web API:** buscar cada artista → obtener el campo `genres` (microgéneros, ~5.000 etiquetas)
2. **Mapeo microgénero → macrogénero:** diccionario explícito versionado en `config/taxonomia_generos.yaml`. Este archivo es la única fuente de verdad y lo usan todos los notebooks y el dashboard.
3. **Fallback MusicBrainz / Last.fm tags** para artistas locales sin presencia en Spotify (va a ser frecuente con folklore y tango)
4. **Fallback por venue:** un venue con perfil consistente (una milonga, un club de jazz) aporta un prior fuerte
5. **Clasificador de texto** sobre título + descripción para el resto: TF-IDF + regresión logística, o BETO fine-tuneado si el volumen lo justifica
6. **Sin clasificar** → `OTRO`, y se reporta el porcentaje

### 5.2 Validación del etiquetado (obligatoria)

Etiqueto **a mano** una muestra aleatoria estratificada de 200 eventos y mido:
- Accuracy del pipeline automático contra mi etiqueta
- Kappa de Cohen
- Matriz de confusión por macrogénero

**Umbral:** si accuracy < 0.75, el etiquetado no es apto y hay que mejorar la cascada antes de modelar. Un error sistemático acá (por ejemplo, que todo el folklore caiga en `OTRO`) invalida todas las conclusiones posteriores.

---

## 6. Fase 4 — Construcción de la composición

### 6.1 Agregación

Para cada celda (barrio $b$, trimestre $t$):

$$c_{bt} = (c_{bt,1}, \dots, c_{bt,D}), \quad c_{bt,g} = \#\{\text{eventos de género } g\}$$

**Decisión de ponderación a documentar:** ¿cada evento pesa igual? Alternativas: ponderar por capacidad del venue, o por número de funciones. Empiezo con peso uniforme y dejo la alternativa como ablación en Fase 7.

### 6.2 Cierre al símplex

$$\mathcal{C}[c] = \left(\frac{c_1}{\sum_j c_j}, \dots, \frac{c_D}{\sum_j c_j}\right)$$

### 6.3 Tratamiento de ceros — crítico

Los ceros rompen las transformaciones log-ratio. Los ceros acá son **de conteo** (no observé eventos de tango en Lugano ese trimestre), no estructurales.

Uso **reemplazo multiplicativo bayesiano** (equivalente al método de `zCompositions::cmultRepl` en R): reemplazo el cero por un valor pequeño derivado de un prior Dirichlet y reescalo el resto para preservar el cierre y las razones entre partes no nulas.

**No usar** el atajo de sumar una constante arbitraria a todas las celdas: distorsiona las razones, que es justamente la información que la geometría de Aitchison preserva.

---

## 7. Fase 5 — EDA composicional

Acá es donde el proyecto se diferencia de un EDA genérico.

### 7.1 Por qué la estadística clásica no aplica

Los datos composicionales viven en el símplex $S^D$, no en $\mathbb{R}^D$. Las consecuencias:

- **La correlación de Pearson es espuria por construcción.** Pearson lo señaló en 1897: si las partes suman 1, un aumento en una fuerza una disminución en las otras. Una correlación negativa entre `ROCK` y `TROP` no significa nada.
- La media aritmética de composiciones no es una composición representativa; hay que usar el **centro** (media geométrica cerrada).
- La distancia euclídea no respeta la escala relativa; hay que usar la distancia de Aitchison.

**Sustituto correcto de la matriz de correlación:** la **matriz de variación**, con entradas $\tau_{ij} = \text{Var}[\log(x_i/x_j)]$. Valores bajos indican proporcionalidad entre partes.

### 7.2 Transformaciones

**CLR** (centered log-ratio), útil para visualización, singular por construcción:

$$\text{clr}(\mathbf{x}) = \left(\log\frac{x_1}{g(\mathbf{x})}, \dots, \log\frac{x_D}{g(\mathbf{x})}\right), \quad \sum_i \text{clr}_i = 0$$

**ILR** (isometric log-ratio), la que uso para modelar. Es una isometría $S^D \to \mathbb{R}^{D-1}$, así que en coordenadas ILR puedo usar toda la estadística multivariada estándar y volver con la inversa.

**Implementación desde cero (tarea explícita del proyecto):** construir la base ortonormal de ILR vía una **secuencia de particiones binarias (SBP)** y Gram-Schmidt sobre la matriz de contrastes. Verificar contra `composition_stats` o `scikit-bio`. Esto es álgebra lineal numérica aplicada y es exactamente el tipo de implementación que quiero hacer a mano.

La SBP se elige con sentido sustantivo, por ejemplo:
```
Balance 1: {TANG, FOLK} vs {ROCK, TROP, JAZZ, ELEC, CLAS, OTRO}   # raíz vs. resto
Balance 2: TANG vs FOLK                                            # dentro de raíz
Balance 3: {TROP, ELEC} vs {ROCK, JAZZ, CLAS, OTRO}                # baile vs. escucha
...
```
Cada balance es interpretable, lo cual es una ventaja enorme sobre una base arbitraria.

### 7.3 Visualizaciones

- **Biplot composicional** (PCA sobre datos CLR)
- **Diagramas ternarios** para subcomposiciones de 3 géneros
- **Mapa coroplético** por género dominante y por balance
- **Dendrograma** de barrios con distancia de Aitchison

---

## 8. Fase 6 — Covariables

### 8.1 Fuentes

- **Censo 2022 (INDEC)** — `censo.gob.ar`: población, densidad, estructura etaria, IPMH (índice de privación material de los hogares)
- **IDECBA** — `estadisticaciudad.gob.ar`: indicadores por comuna, hogares, vivienda, educación
- **BA Data**: subte y transporte, espacios verdes, oferta gastronómica

### 8.2 Set inicial de covariables (mantener acotado)

| Variable | Fuente | Hipótesis |
|---|---|---|
| Edad mediana | Censo | Barrios más jóvenes → más `ELEC`/`TROP` |
| % con educación superior | Censo | → más `JAZZ`/`CLAS` |
| Densidad poblacional | Censo | → más eventos en general |
| IPMH (privación) | Censo | → más `TROP`, menos `CLAS` |
| Distancia al microcentro | Calculada | Centralidad de la oferta |
| Estaciones de subte per cápita | BA Data | Accesibilidad nocturna |
| Venues per cápita | Propia | Densidad de infraestructura cultural |

**Regla:** máximo 7 covariables en el modelo principal. Cualquier agregado requiere justificación y test de mejora en CV espacial.

### 8.3 El problema MAUP (documentar, no ignorar)

Los datos censales vienen por **comuna** (15 unidades); la oferta la mido por **barrio** (48). Esta desalineación es el *modifiable areal unit problem*.

**Decisión:** trabajo a nivel barrio, asignando a cada barrio los valores de su comuna, y **documento explícitamente** que las covariables tienen resolución de comuna. Los barrios de una misma comuna comparten covariables, lo que reduce la variación efectiva — motivo adicional para incluir efectos aleatorios por comuna en el modelo.

Alternativa a evaluar: reagregar todo a comuna y aceptar n = 15 × 12 = 180.

---

## 9. Fase 7 — Modelado

Orden estricto: **lineal antes que no lineal**.

### 9.1 M0 — Baselines
Los tres de la sección 2.4. Se implementan primero.

### 9.2 M1 — Regresión lineal multivariada en coordenadas ILR

$$\text{ilr}(\mathbf{c}_{bt}) = \mathbf{B}^\top \mathbf{z}_{bt} + \boldsymbol{\varepsilon}_{bt}$$

Ajusto D−1 = 7 regresiones. Los coeficientes se interpretan sobre los balances de la SBP, que elegí para que sean interpretables.

**Entregable:** tabla de coeficientes con intervalos de confianza y su lectura sustantiva.

### 9.3 M2 — Regresión Dirichlet

Modela directamente la composición con verosimilitud Dirichlet, sin transformación previa. En Python el ecosistema es pobre: implementar la log-verosimilitud y optimizar con `scipy.optimize`, verificando contra `DirichletReg` de R en un caso chico.

**Comparación clave contra M1:** Dirichlet modela la media pero impone una estructura de varianza rígida; ILR es más flexible. Discutir el trade-off.

### 9.4 M3 — Modelo multinivel

Efectos aleatorios por barrio (y/o comuna) sobre las coordenadas ILR. Esto:
- Separa varianza entre-barrios de intra-barrio (dato central del proyecto)
- Da el **coeficiente de correlación intraclase (ICC)**: qué fracción de la variación total es atribuible al barrio
- Regulariza barrios con pocos eventos vía *shrinkage* hacia la media

El ICC es probablemente el número más importante que va a producir el proyecto.

### 9.5 M4 — No lineal

Random Forest / gradient boosting multi-output sobre coordenadas ILR. Comparar contra M1 en CV espacial. **Hipótesis honesta:** con n moderado y 7 covariables, es probable que no supere al lineal. Si es así, se reporta — es un resultado válido.

### 9.6 Diagnóstico espacial

- **I de Moran** sobre los residuos de M1. Si hay autocorrelación residual significativa, el modelo omite estructura espacial.
- Si la hay: agregar *lag* espacial (composición media de barrios vecinos) o pasar a un modelo SAR/CAR.
- La matriz de pesos espaciales $W$ se define por contigüidad tipo *queen* sobre el shapefile.

---

## 10. Fase 8 — Clustering y honestidad metodológica

### 10.1 Clustering de barrios

- Distancia: **Aitchison**, no euclídea
- Método: Ward sobre la matriz de distancias
- Selección de k: silhouette en el espacio ILR + interpretabilidad
- Salida: mapa coroplético de "regiones musicales" de CABA

### 10.2 Sección de limitaciones (va en el README, no escondida)

Se escribe explícitamente:

1. **Oferta ≠ demanda ≠ preferencia individual.** El proyecto mide dónde ocurren los eventos, no qué escucha la gente que vive ahí. Un barrio con muchos venues concentra oferta que consume toda la ciudad (Palermo es el caso obvio).
2. **Falacia ecológica.** Ninguna conclusión de este trabajo permite inferir el gusto de un individuo a partir de su barrio. La correlación agregada y la individual son cantidades distintas.
3. **Sesgo de plataforma.** Los eventos que llegan a Songkick/Ticketek sobrerrepresentan circuitos formales. Peñas, milongas barriales y fiestas informales están subrepresentadas de forma sistemática y no aleatoria.
4. **MAUP.** Covariables a resolución de comuna, target a resolución de barrio.
5. **Etiquetado.** Accuracy medida del pipeline de géneros: reportar el número real.

Esta sección es un activo del proyecto, no una disculpa. Es lo que separa un análisis serio de un notebook bonito.

---

## 11. Fase 9 — Producto final

### 11.1 Estructura del repo

```
musica-barrios-caba/
├── README.md
├── ROADMAP.md
├── config/
│   └── taxonomia_generos.yaml      # fuente única de verdad
├── data/
│   ├── raw/                        # gitignored
│   ├── interim/
│   └── processed/
├── scripts/
│   ├── 01_scrape_songkick.py       # standalone, NO en Jupyter
│   ├── 02_scrape_gcba.py
│   ├── 03_geocode.py
│   └── 04_label_genres.py
├── notebooks/
│   ├── 01_eda_eventos.ipynb
│   ├── 02_validacion_etiquetado.ipynb
│   ├── 03_eda_composicional.ipynb
│   ├── 04_modelado.ipynb
│   └── 05_clustering_espacial.ipynb
├── src/
│   ├── composicional.py            # ILR/CLR implementados a mano
│   ├── espacial.py
│   └── modelos.py
├── tests/
│   └── test_composicional.py       # ILR ida y vuelta, propiedades de isometría
└── app/
    └── dashboard.py                # Streamlit
```

### 11.2 Tests mínimos

- `ilr_inv(ilr(x)) == x` a tolerancia numérica
- La base ILR es ortonormal: $\mathbf{V}^\top\mathbf{V} = \mathbf{I}$
- La distancia de Aitchison es invariante ante perturbación
- El cierre preserva las razones entre partes

### 11.3 Dashboard

Mapa interactivo de CABA: seleccionar barrio → composición observada vs. predicha, balances, cluster asignado. Selector de trimestre para ver dinámica temporal.

---

## 12. Orden de ejecución y gates

| Fase | Entregable | Gate para avanzar |
|---|---|---|
| 0 | Documento de protocolo | Métricas y baselines escritos y congelados |
| 1 | `data/raw/eventos.parquet` | ≥3.000 eventos, ≥40 barrios, ≥36 meses |
| 2 | Eventos con barrio asignado | ≥85% geocodificación exitosa |
| 3 | Eventos etiquetados | Accuracy ≥0.75 contra muestra manual de 200 |
| 4 | Panel composicional | `OTRO` <25%; ceros tratados |
| 5 | EDA composicional | Biplot y matriz de variación producidos |
| 6 | Tabla de covariables | ≤7 covariables, MAUP documentado |
| 7 | Modelos M0–M4 | M1 supera B0, B1 y B2 en CV espacial |
| 8 | Clusters + limitaciones | Sección de limitaciones escrita |
| 9 | Repo + dashboard | Tests pasando |

**Regla de oro:** no se avanza de fase sin pasar el gate. Si el gate de Fase 7 falla (ningún modelo supera los baselines), el proyecto se reporta como resultado negativo con el análisis de por qué. Eso sigue siendo un buen proyecto.

---

## 13. Estimación de esfuerzo

| Fase | Tiempo estimado |
|---|---|
| 0 | 1 día |
| 1 | 1–2 semanas (el scraping siempre tarda más) |
| 2 | 3–4 días |
| 3 | 1 semana (la validación manual es tediosa pero innegociable) |
| 4–5 | 1 semana |
| 6 | 3 días |
| 7 | 1,5 semanas |
| 8–9 | 1 semana |

**Total: 6–8 semanas** a tiempo parcial.

---

## 14. Riesgos principales

| Riesgo | Probabilidad | Mitigación |
|---|---|---|
| Volumen de eventos insuficiente | Media | Gate de Fase 1; degradar a panel semestral |
| Etiquetado de géneros poco fiable para artistas locales | **Alta** | Cascada con MusicBrainz + prior por venue; validación manual |
| Palermo/Recoleta dominan y aplastan la señal | Media | Normalizar por venues per cápita; efectos aleatorios |
| Ninguna covariable resulta significativa | Media | Es un resultado reportable; el ICC sigue siendo interesante |
| Autocorrelación espacial no modelada | Media | I de Moran sobre residuos en Fase 7 |
