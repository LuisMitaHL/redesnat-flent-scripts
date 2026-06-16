# REDesNat Flent Scripts

Conjunto de scripts para la ejecución automatizada de pruebas de rendimiento de red con [Flent](https://flent.org/) y el posterior análisis estadístico de los resultados. Este proyecto se enmarca en el trabajo de REDesNat para la comparativa de _firmwares_ de routers en redes domésticas.

## Objetivo

Comparar el rendimiento de dos _firmwares_ de router:

| Firmware | Descripción |
|---|---|
| `cudystock` | _Firmware_ stock del fabricante |
| `owrtredesnat` | _Firmware_ REDesNat basado en OpenWrt |

Las pruebas se realizan en dos bandas de frecuencia (2.4 GHz y 5 GHz) y con distintos niveles de conexiones TCP concurrentes (1, 50, 100 y 150 pares subida/bajada).

## Estructura del proyecto

```
├── flent-tests.sh          # Lanzador de pruebas Flent
├── flent-csv.sh            # Conversión de resultados .flent a .csv
├── anova_latency.py        # ANOVA de dos vías sobre latencia bajo carga
├── anova_loss.py           # ANOVA de dos vías sobre pérdida de paquetes
├── chisquare_dead.py       # Test χ² de independencia sobre conexiones TCP estancadas
└── README.md
```

## Requisitos

- **Flent** ≥ 2.0 — herramienta de pruebas de red (`pip install flent` o paquete del sistema).
- **Python** ≥ 3.8 con las dependencias listadas en cada script (ver sección [Dependencias Python](#dependencias-python)).
- Acceso a un servidor Flent (por defecto `10.64.21.21`).

## Scripts

### 1. `flent-tests.sh` — Ejecución de pruebas

Lanza pruebas `rrul_be_nflows` con distintas cargas de conexiones TCP, iterando sobre todas las combinaciones de _firmware_ y banda de radio.

```bash
# Ejecutar todas las combinaciones (pide confirmación antes de cada cambio de configuración)
./flent-tests.sh

# Filtrar por firmware y banda
./flent-tests.sh -f owrtredesnat -r 5g

# Repetir cada test N veces
./flent-tests.sh -n 5

# Ver ayuda completa
./flent-tests.sh -h
```

**Opciones:**

| Opción | Descripción |
|---|---|
| `-f <firmware>` | Solo este _firmware_ (`cudystock` / `owrtredesnat`) |
| `-r <radio>` | Solo esta banda (`24g` / `5g`) |
| `-t <test>` | Solo este test (repetible; ej. `rrul_be`) |
| `-n <N>` | Repetir cada test N veces (por defecto 1) |
| `-s <sufijo>` | Sufijo opcional para el título de cada test |
| `-h` | Muestra la ayuda |

El script genera archivos `.flent` (o `.flent.gz`) cuyo nombre sigue el patrón:

```
.<firmware>-<banda>-<descargas>d-<subidas>u-<potencia>dbm-run<N>.flent[.gz]
```

> **Nota:** El script se pausa antes de cada cambio de _firmware_ o banda para que el operador configure el router manualmente.

### 2. `flent-csv.sh` — Conversión a CSV

Convierte todos los archivos `.flent` y `.flent.gz` del directorio actual a CSV, omitiendo aquellos que ya existan.

```bash
./flent-csv.sh
```

### 3. `anova_latency.py` — ANOVA de latencia

Realiza un **ANOVA de dos vías** (Two-Way ANOVA) sobre las métricas de latencia (media y P99) obtenidas de los pings ICMP que se ejecutan concurrentemente con tráfico TCP.

**Modelo:** `latencia ~ firmware + conexiones + firmware:conexiones`

```bash
# Analizar banda de 5 GHz
./anova_latency.py --band 5g

# Analizar banda de 2.4 GHz
./anova_latency.py --band 24g

# Especificar directorio con los CSV
./anova_latency.py --band 5g --csv-dir ./resultados
```

La salida es _markdown_ con:
- Estadísticos descriptivos (media, desviación, mínimo, máximo) agrupados por _firmware_ y nivel de conexiones.
- Tabla ANOVA con efectos principales e interacción.
- Coeficientes del modelo.

### 4. `anova_loss.py` — ANOVA de pérdida de paquetes

Realiza un **ANOVA de dos vías** sobre las tasas de pérdida de paquetes de dos flujos de ping independientes que coexisten con la carga TCP:
- **ICMP ping** — _echo requests_ ICMP estándar.
- **UDP BE ping** — UDP _Best Effort_ (DSCP 0), compitiendo en la cola del cuello de botella con los flujos TCP.

La tasa de pérdida se calcula como:

```
loss_rate = conteo de filas NaN en la columna de ping bajo carga TCP / total de filas bajo carga TCP
```

```bash
./anova_loss.py --band 5g
./anova_loss.py --band 24g --csv-dir ./resultados
```

### 5. `chisquare_dead.py` — Test χ² de conexiones estancadas

Clasifica cada prueba como **exitosa** o **fallida** en función del porcentaje de conexiones TCP que se estancan (_stall_) después de haber comenzado a transmitir. Aplica un **test χ² de independencia** para determinar si la tasa de fallos depende del _firmware_.

**Criterios configurables:**
- `--stall-gap`: número de muestras consecutivas vacías para considerar una conexión estancada (por defecto 5).
- `--stall-threshold`: porcentaje de conexiones estancadas a partir del cual la prueba se considera fallida (por defecto 0.5 = 50 %).

```bash
./chisquare_dead.py --band 5g
./chisquare_dead.py --band 24g --stall-gap 10 --stall-threshold 0.3
```

**Salida:** tabla de contingencia _firmware_ × resultado, estadístico χ², valor _p_ y residuos ajustados.

## Flujo de trabajo típico

```bash
# 1. Ejecutar las pruebas
./flent-tests.sh -n 3

# 2. Convertir resultados a CSV
./flent-csv.sh

# 3. Analizar latencia
./anova_latency.py --band 5g  > resultados-latencia-5g.md
./anova_latency.py --band 24g > resultados-latencia-24g.md

# 4. Analizar pérdida
./anova_loss.py --band 5g  > resultados-perdida-5g.md
./anova_loss.py --band 24g > resultados-perdida-24g.md

# 5. Analizar estancamiento TCP
./chisquare_dead.py --band 5g  > resultados-estancamiento-5g.md
./chisquare_dead.py --band 24g > resultados-estancamiento-24g.md
```

## Dependencias Python

Los scripts de análisis requieren las siguientes librerías:

```
numpy
pandas
scipy
statsmodels
tabulate        # para tablas markdown en ANOVA
```

Instalación rápida:

```bash
pip install numpy pandas scipy statsmodels tabulate
```

## Convención de nombres de archivo

Los archivos CSV generados siguen el patrón:

```
<test>-<fecha>.<firmware>-<banda>-<descargas>d-<subidas>u-<potencia>dbm-run<N>.csv
```

Ejemplo: `rrul_be_nflows-2026-05-20T104313.970833.owrtredesnat-5g-100d-100u-30dbm-run2.csv`

Este patrón es interpretado por los scripts de análisis para extraer automáticamente los factores (_firmware_, banda, número de conexiones, réplica).

## Licencia

Este proyecto se distribuye bajo la licencia MIT. Consulte el archivo [LICENSE](LICENSE) para más detalles.
