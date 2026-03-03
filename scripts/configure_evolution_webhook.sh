#!/bin/bash
# ============================================================
# Script para configurar el Webhook en Evolution API
# ============================================================

# Configuración (modificar según tu entorno)
EVOLUTION_API_URL="${EVOLUTION_API_URL:-http://localhost:8080}"
INSTANCE_NAME="${EVOLUTION_INSTANCE:-Nagaki_test}"
API_KEY="${EVOLUTION_API_KEY:-1036448838}"
WEBHOOK_URL="${WEBHOOK_URL:-https://shena-overtender-derivationally.ngrok-free.dev/webhook/message}"

echo "============================================================"
echo "Configurando Webhook en Evolution API"
echo "============================================================"
echo "  Evolution API: $EVOLUTION_API_URL"
echo "  Instance: $INSTANCE_NAME"
echo "  Webhook URL: $WEBHOOK_URL"
echo "============================================================"

# Configurar webhook con todos los eventos necesarios
curl -X POST "${EVOLUTION_API_URL}/webhook/set/${INSTANCE_NAME}" \
  -H "Content-Type: application/json" \
  -H "apikey: ${API_KEY}" \
  -d '{
    "webhook": {
      "enabled": true,
      "url": "'"${WEBHOOK_URL}"'",
      "webhookByEvents": false,
      "webhookBase64": true,
      "events": [
        "MESSAGES_UPSERT",
        "MESSAGES_UPDATE",
        "SEND_MESSAGE",
        "CONNECTION_UPDATE",
        "PRESENCE_UPDATE",
        "CONTACTS_UPSERT",
        "CHATS_UPSERT"
      ]
    }
  }'

echo ""
echo ""
echo "============================================================"
echo "Verificando configuración del webhook..."
echo "============================================================"

# Verificar configuración
curl -s -X GET "${EVOLUTION_API_URL}/webhook/find/${INSTANCE_NAME}" \
  -H "apikey: ${API_KEY}" | python3 -m json.tool 2>/dev/null || \
  curl -s -X GET "${EVOLUTION_API_URL}/webhook/find/${INSTANCE_NAME}" \
  -H "apikey: ${API_KEY}"

echo ""
echo ""
echo "✅ Configuración completada!"
