# Protocolo de estudio — Perfil musical de los barrios de CABA

**Autor:** Franco Cataldi
**Congelado el:** 2026-08-01
**Estado:** congelado. No se modifica sin agregar una nota al pie con qué cambió, cuándo y por qué.

> Este documento se escribe **antes** de descargar un solo dato. Su función es fijar cómo
> se va a evaluar el resultado antes de conocerlo, para que la elección de métrica no
> pueda ser contaminada por lo que los datos terminen mostrando.

---

## 1. Pregunta de investigación

> **¿En qué medida la composición por macrogénero de la oferta de música en vivo de un
> barrio de CABA es explicable por sus características demográficas, socioeconómicas y
> de accesibilidad?**

Tres precisiones que la pregunta lleva adentro y que no se relajan en ningún momento:

- **El objeto medido es la oferta**, es decir, los eventos que ocurren dentro del polígono
  del barrio. No es lo que escuchan sus residentes, ni lo que consumen, ni lo que prefieren.
- **La unidad es el barrio**, no la persona. Ninguna conclusión de este trabajo autoriza a
  inferir el gusto de un individuo a partir de dónde vive (falacia ecológica).
- **La respuesta es cuantitativa y admite el "casi nada"**: si las covariables no explican
  nada por encima de los baselines, la pregunta queda respondida igual, en negativo.

---

## 2. Unidad de observación

Una fila del dataset final es un par **(barrio, trimestre)**.

**Por qué no el barrio solo.** CABA tiene 48 barrios. Con n = 48 y un target de dimensión
D−1 = 7, cualquier modelo con más de ~4 covariables sobreajusta, y eso no se arregla solo
con regularización: hay que generar observaciones. Cubriendo 3 años:

```
n = 48 barrios × 12 trimestres = 576 observaciones
```

**Por qué trimestre y no mes.** El mes daría 48 × 36 = 1.728 filas, tres veces más. Pero el
target de cada fila es un vector de 8 proporciones, y estimar 8 proporciones requiere un
mínimo de eventos en esa celda. Con ~3.000 eventos repartidos en 1.728 celdas quedan menos
de 2 eventos por celda en promedio: la composición resultante sería ruido, no señal, y
además casi todas las celdas tendrían ceros en casi todos los géneros. El trimestre es el
grano más fino que mantiene celdas estimables. **Más filas no es más información si cada
fila es peor.**

**Regla de baja confianza.** Las celdas con menos de 10 eventos se marcan con un flag
`baja_confianza`. No se imputan ni se borran en silencio: la decisión (excluirlas o
ponderarlas) se toma y se documenta en la Etapa 4.

<!-- REVISAR: decidir en Etapa 4 si las celdas de baja confianza se excluyen o se ponderan
     por raiz(n_eventos). Escribir la decision aca cuando este tomada. -->

**Ventana temporal: se excluyen 2020 y 2021.** *(Enmienda del 2026-08-05, ver registro
al pie.)* La pandemia no es variación normal de la oferta cultural: es un shock exógeno
que la suprimió casi por completo durante meses por decisión administrativa. Incluir esos
trimestres rompería el supuesto central del estudio — que la composición de la oferta se
explica por características del barrio — porque durante ese período se explica por el
estado de las restricciones sanitarias, que es idéntico para los 48 barrios.

Se excluye el bloque completo 2020Q1–2021Q4 (8 trimestres). El panel se arma con
2017–2019 más 2022 en adelante. Las series temporales quedan **discontinuas**, lo cual
tiene una consecuencia concreta: el baseline B2 (persistencia respecto del trimestre
anterior) no se puede calcular para el primer trimestre posterior al hueco, y esas
observaciones se excluyen del cómputo de B2 en vez de compararse contra un trimestre
separado por dos años.

**Plan de degradación.** Si tras la Etapa 1 hay menos de 3.000 eventos geolocalizados, o
si la cobertura efectiva tras excluir la pandemia no llega a 36 meses, el panel trimestral
no cierra y se degrada a semestral (n = 48 × 6 = 288), dejando nota en este documento. La
degradación se decide por el conteo, no por lo que convenga al modelo.

---

## 3. Taxonomía de géneros

Cerrada, mutuamente excluyente, D = 8. Fuente única de verdad:
`config/taxonomia_generos.yaml`. Nunca se hardcodean estas categorías en un notebook.

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

**Por qué D = 8.** Con D categorías el espacio ILR tiene D−1 = 7 dimensiones. Con n = 576
la relación observaciones/parámetros es holgada. D más grande fragmentaría celdas ya
escasas; D más chico borraría distinciones sustantivas (tango vs. folklore es exactamente
la distinción que hace interesante a esta ciudad).

**Condición de calibración.** Si `OTRO` supera el 25% del total, la taxonomía está mal
calibrada o el etiquetado está fallando, y se revisa **antes** de seguir. Un `OTRO` inflado
significa que el proyecto no está midiendo lo que dice medir.

---

## 4. Métricas — definidas antes de ver los datos

### Primaria: RMSE en coordenadas ILR

Es la métrica de **optimización y comparación de modelos**. Se elige como primaria porque
ILR es una isometría del símplex a ℝ^(D−1): en ese espacio el error euclídeo es un objeto
estadístico legítimo, los residuos son comparables entre coordenadas, y toda la maquinaria
multivariada estándar aplica sin corrección. Sobre las proporciones crudas, en cambio, el
RMSE está mal definido conceptualmente: un error de 0.05 sobre una parte que vale 0.50 y
uno sobre una parte que vale 0.01 no son el mismo error, y la métrica euclídea los trata
igual.

### Interpretable: distancia de Aitchison media

$$d_A(\mathbf{x},\mathbf{y}) = \sqrt{\sum_{i=1}^{D}\Big(\log\tfrac{x_i}{g(\mathbf{x})} - \log\tfrac{y_i}{g(\mathbf{y})}\Big)^2}$$

con $g(\cdot)$ la media geométrica. Es la distancia euclídea en el espacio CLR y mide
"cuán lejos" está la composición predicha de la observada **en la geometría correcta**.

*Por qué no es la primaria:* es monótonamente equivalente al error en ILR (ambas son la
misma distancia en bases distintas), así que como criterio de optimización no agrega nada,
pero como número único a reportar es más comunicable que 7 RMSE por coordenada.

### De comunicación: error absoluto medio en puntos porcentuales, por género

Para el README y para cualquier lector no técnico. "El modelo se equivoca en promedio 4
puntos porcentuales al estimar la proporción de tango de un barrio" es una frase que se
entiende sin saber qué es el símplex. **No se usa para seleccionar modelos** — vive fuera
de la geometría de Aitchison y penaliza mal a las partes chicas.

---

## 5. Baselines

Se implementan **antes** que cualquier modelo. Sin ellos ningún número significa nada:
un error de 0.15 en distancia de Aitchison es excelente o es basura según cuánto dé lo tonto.

| ID | Qué predice | Qué se testea si le gano |
|---|---|---|
| **B0** | La composición global cerrada (media geométrica de todos los barrio-trimestres), igual para todos | Piso absoluto. Que haya *alguna* variación territorial. |
| **B1** | La composición de la comuna a la que pertenece el barrio | Que el **barrio** agregue información por encima de la comuna. Crítico, porque las covariables censales tienen resolución de comuna. |
| **B2** | La composición del mismo barrio en el trimestre anterior (persistencia) | Que las **covariables** agreguen algo por encima de la pura inercia temporal. Es el baseline más duro. |

---

## 6. Esquema de validación

### Por qué el k-fold aleatorio está prohibido acá

El k-fold aleatorio supone que las filas son independientes. Acá no lo son, por dos vías:

- **Espacial.** Barrios contiguos se parecen (comparten público, transporte, circuito de
  venues, y directamente comparten covariables si están en la misma comuna). Si Palermo
  queda en train y Villa Crespo en test, el modelo ya vio casi la respuesta: el test mide
  memorización, no generalización, y la performance sale inflada.
- **Temporal.** Es un panel. El mismo barrio aparece 12 veces. Si el Q1-2024 de Almagro
  está en train y el Q2-2024 de Almagro en test, hay fuga directa por B2 (persistencia).

### Esquema adoptado

**a) CV espacial por bloques (esquema principal).**
Los 48 barrios se parten en 5 bloques geográficamente contiguos. Cada fold deja **un bloque
entero afuera**, con todos sus trimestres. Análogo espacial del walk-forward temporal.

*Criterio operativo para definir los bloques* — tiene que ser ejecutable y reproducible,
no "los agrupo a ojo":

1. Se toman los centroides de los 48 barrios, proyectados en **EPSG:5347** (POSGAR 2007
   Faja 5), porque el agrupamiento es por distancia y en EPSG:4326 la distancia está en
   grados, que no es una unidad métrica.
2. Se construye la matriz de contigüidad **queen** sobre el shapefile oficial (dos barrios
   son vecinos si comparten al menos un punto de frontera). Esta misma matriz `W` se
   reutiliza después para la I de Moran en la Etapa 7 — se calcula una vez.
3. Se corre un clustering **con restricción de contigüidad** sobre los centroides —
   `AgglomerativeClustering(n_clusters=5, connectivity=W, linkage="ward")` de scikit-learn.
   El parámetro `connectivity` es lo que garantiza que ningún bloque salga geográficamente
   partido en dos pedazos.
4. Se verifica que ningún bloque tenga menos de 6 barrios (si lo tiene, el fold es
   demasiado chico para estimar error). Si pasa, se baja a 4 bloques.
5. La asignación resultante se **persiste** en `data/processed/bloques_cv.csv` y se
   commitea. No se recalcula en cada corrida: si cambia la partición, cambian los
   resultados, y eso los volvería incomparables entre sí.

**b) Hold-out temporal.** Los últimos 2 trimestres se reservan enteros. Sirve para evaluar
B2 y cualquier componente dinámico sin fuga hacia el futuro.

**c) Test de permutación.** 1.000 permutaciones aleatorias de la asignación
covariables ↔ barrios, reajustando el modelo en cada una. Si el error real no cae en la
cola de la distribución nula, no hay señal — por bien que se vea cualquier otra métrica.
Es la prueba más honesta disponible y la más difícil de engañarse a uno mismo.

<!-- REVISAR: fijar la semilla aleatoria del test de permutacion y anotarla aca,
     para que el resultado sea reproducible exactamente. -->

---

## 7. Criterio de éxito

El modelo M1 (regresión lineal multivariada en coordenadas ILR) debe superar a **B0, B1 y
B2 simultáneamente** en CV espacial por bloques, **y** el test de permutación debe dar
significativo (p < 0.05).

Superar solo a B0 no cuenta: significa apenas que hay variación territorial, cosa que ya se
sabe. Superar a B0 y B1 pero no a B2 significa que la composición de un barrio se predice
mejor con su propio pasado que con sus características — un resultado interesante, pero
que **no** responde afirmativamente la pregunta de investigación.

---

## 8. Criterio de fracaso

Escrito ahora, antes de estar emocionalmente invertido en el resultado:

> Si ningún modelo supera los tres baselines en validación espacial, o si el test de
> permutación no da significativo, **reporto resultado negativo**. No busco una métrica
> alternativa que dé mejor, no cambio el esquema de validación, no recorto la muestra a
> los barrios donde funciona. Escribo qué se probó, qué no funcionó y las hipótesis de por
> qué (covariables a resolución de comuna, sesgo de plataforma, ruido del etiquetado), y
> el ICC del modelo multinivel queda igualmente como resultado sustantivo.

Un proyecto que reporta un resultado negativo bien fundamentado es un proyecto válido.
Uno que busca hasta encontrar un número lindo, no.

---

## 9. Amenazas a la validez asumidas desde el diseño

Se listan acá para que ninguna aparezca después como "hallazgo":

1. **Oferta ≠ demanda ≠ preferencia individual.** Palermo concentra oferta que consume toda
   la ciudad.
2. **Falacia ecológica.** Robinson (1950): correlaciones de 0.77 entre estados y 0.20 entre
   individuos para las mismas variables.
3. **Sesgo de plataforma.** Songkick y ticketeras sobrerrepresentan el circuito formal.
   Peñas, milongas barriales y fiestas informales faltan de forma **sistemática**, no
   aleatoria — es decir, sesgan, no solo agregan ruido.
4. **MAUP.** Covariables a resolución de comuna (15), target a resolución de barrio (48).
5. **Etiquetado construido, no observado.** El género es una variable que fabrico yo. Su
   accuracy medida contra muestra manual se reporta en el README, sea cual sea.

---

## Registro de modificaciones

| Fecha | Qué cambió | Por qué |
|---|---|---|
| 2026-08-01 | Versión inicial congelada | — |
| 2026-08-05 | § 2: se excluyen 2020Q1–2021Q4 del panel | Al inventariar fuentes (Etapa 1) se confirmó que los datos históricos disponibles cubren la pandemia. Es un shock exógeno común a los 48 barrios, no variación explicable por covariables territoriales. La decisión se toma **antes** de ver ninguna composición, así que no está contaminada por resultados. |
