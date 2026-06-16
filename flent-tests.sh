#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Variables configurables
# ============================================================
FLENT_SERVER="${FLENT_SERVER:-10.64.21.21}"
DURATION="${DURATION:-20}"

# ============================================================
# Firmwares y radios a testear
# ============================================================
FIRMWARES=("cudystock" "owrtredesnat")
RADIOS=("24g" "5g")

# ============================================================
# Tests de flent a ejecutar por combinación
# Cada elemento: "test_name arg1=val1 arg2=val2 ..."
# ============================================================

# para anova usaremos rrul_be
TESTS=(
  "rrul_be_nflows upload_streams=1 download_streams=1"
  "rrul_be_nflows upload_streams=50 download_streams=50"
  "rrul_be_nflows upload_streams=100 download_streams=100"
  "rrul_be_nflows upload_streams=150 download_streams=150"
)

# ============================================================
# Argumentos de línea de comandos (filtros parciales)
# ============================================================
FILTER_FW=""
FILTER_RADIO=""
FILTER_TESTS=()
SUFFIX=""
REPEAT=1

usage() {
  echo "Uso: $0 [-f <firmware>] [-r <radio>] [-t <test>] [-s <suffix>] [-h]"
  echo ""
  echo "Opciones:"
  echo "  -f <firmware>   Ejecutar solo este firmware (por ej. cudystock)"
  echo "  -r <radio>      Ejecutar solo esta banda (por ej. 5g)"
  echo "  -t <test>       Ejecutar solo este test (repetible, por ej. rrul_be)"
  echo "  -n <N>          Repetir cada test N veces (por defecto 1)"
  echo "  -s <suffix>     Sufijo opcional para añadir al título de cada test"
  echo "  -h              Muestra esta ayuda y sale"
  echo ""
  echo "Sin filtros se ejecutan todas las combinaciones."
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -f|--firmware)
      FILTER_FW="$2"
      shift 2
      ;;
    -r|--radio)
      FILTER_RADIO="$2"
      shift 2
      ;;
    -t|--test)
      FILTER_TESTS+=("$2")
      shift 2
      ;;
    -n|--repeat)
      REPEAT="$2"
      shift 2
      ;;
    -s|--suffix)
      SUFFIX="$2"
      shift 2
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "Error: argumento desconocido: $1"
      usage
      ;;
  esac
done

# ============================================================
# Función auxiliar: determina si un test debe ejecutarse
# ============================================================
should_run_test() {
  local test_name="$1"
  if [[ ${#FILTER_TESTS[@]} -eq 0 ]]; then
    return 0
  fi
  for ft in "${FILTER_TESTS[@]}"; do
    if [[ "$test_name" == "$ft" ]]; then
      return 0
    fi
  done
  return 1
}

# ============================================================
# Función auxiliar: ejecuta un test de flent con tag
# ============================================================
run_flent() {
  local fw="$1"
  local radio="$2"
  local test_name="$3"
  local params="$4"
  local run_num="${5:-}"
  local tag="${fw}-${radio}"

  local cmd=("flent" "$test_name" "-l" "$DURATION" "-H" "$FLENT_SERVER")

  # Construir tag basado en el tipo de test
  local title=""
  case "$test_name" in
    rrul_be)
      title="${tag}-rrulbe"
      ;;
    rrul_be_nflows)
      local u=0 d=0
      for p in $params; do
        case "$p" in
          upload_streams=*) u="${p#*=}" ;;
          download_streams=*) d="${p#*=}" ;;
        esac
      done
      cmd+=("--test-parameter=upload_streams=$u" "--test-parameter=download_streams=$d")
      title="${tag}-${d}d-${u}u"
      ;;
    rtt_fair_var_mixed)
      title="${tag}-rttfair"
      ;;
  esac

  # Añadir sufijo opcional al título
  if [[ -n "$SUFFIX" ]]; then
    title="${title}-${SUFFIX}"
  fi

  # Añadir número de repetición si corresponde
  if [[ "$REPEAT" -gt 1 && -n "$run_num" ]]; then
    title="${title}-run${run_num}"
  fi

  cmd+=("-t" "$title")

  echo ""
  echo ">>> Ejecutando: ${cmd[*]}"
  echo ""
  "${cmd[@]}"
}

# ============================================================
# Bucle principal: firmware × radio × tests
# ============================================================
for fw in "${FIRMWARES[@]}"; do
  [[ -n "$FILTER_FW" && "$fw" != "$FILTER_FW" ]] && continue

  for radio in "${RADIOS[@]}"; do
    [[ -n "$FILTER_RADIO" && "$radio" != "$FILTER_RADIO" ]] && continue

    echo ""
    echo "======================================================"
    echo "  CAMBIO DE CONFIGURACIÓN REQUERIDO"
    echo "======================================================"
    echo "  Firmware : $fw"
    echo "  Radio    : $radio"
    echo ""
    echo "  Configura el router con estos parámetros manualmente"
    echo "======================================================"

    if [[ -z "$FILTER_FW" || -z "$FILTER_RADIO" ]]; then
      while true; do
        echo "  Escribe 'done' y presiona ENTER cuando esté listo:"
        read -r input
        if [[ "$input" == "done" ]]; then
          break
        fi
        echo "  Entrada inválida. Debes escribir 'done' exactamente."
      done
    else
      echo "  (Omitiendo confirmación: firmware y banda especificados)"
    fi

    for test_spec in "${TESTS[@]}"; do
      # Separar nombre del test del resto de argumentos
      test_name="${test_spec%% *}"
      params=""
      if [[ "$test_spec" == *" "* ]]; then
        params="${test_spec#* }"
      fi

      # Saltar si no corresponde al filtro de tests
      should_run_test "$test_name" || continue

      for ((run=1; run<=REPEAT; run++)); do
        run_flent "$fw" "$radio" "$test_name" "$params" "$run"
        sleep 10
      done
    done

  done
done

# ============================================================
# Fin
# ============================================================
echo ""
echo "======================================================"
echo "  TODOS LOS TESTS COMPLETADOS"
echo "======================================================"
