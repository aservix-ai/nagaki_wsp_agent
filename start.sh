#!/usr/bin/env bash
set -euo pipefail

NAGAKI_AGENT_DIR="${NAGAKI_AGENT_DIR:-/agents/nagaki_agent}"
NAGAKI_WSP_AGENT_DIR="${NAGAKI_WSP_AGENT_DIR:-/agents/nagaki_wsp_agent}"

if [[ ! -d "${NAGAKI_AGENT_DIR}" ]]; then
  echo "Missing directory: ${NAGAKI_AGENT_DIR}" >&2
  exit 1
fi

if [[ ! -d "${NAGAKI_WSP_AGENT_DIR}" ]]; then
  echo "Missing directory: ${NAGAKI_WSP_AGENT_DIR}" >&2
  exit 1
fi

# 1) Worker de qualification (unico para ambos bots)
(
  cd "${NAGAKI_WSP_AGENT_DIR}"
  python -m src.support.agent.qualification.worker
) &
PID_WORKER=$!

# 2) Bot de voz
(
  cd "${NAGAKI_AGENT_DIR}"
  python -m src.support.api.livekit_agent
) &
PID_VOICE=$!

# 3) Bot de WhatsApp
(
  cd "${NAGAKI_WSP_AGENT_DIR}"
  python -m src.support.api.evolution_webhook
) &
PID_WSP=$!

cleanup() {
  kill "${PID_WORKER}" "${PID_VOICE}" "${PID_WSP}" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

wait -n "${PID_WORKER}" "${PID_VOICE}" "${PID_WSP}"
STATUS=$?
cleanup
wait || true
exit ${STATUS}
