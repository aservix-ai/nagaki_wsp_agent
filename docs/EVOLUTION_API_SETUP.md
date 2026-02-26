# Evolution API Setup - WhatsApp Integration

Este documento describe cómo configurar la integración con Evolution API para WhatsApp.

## Variables de Entorno Requeridas

Añade estas variables a tu archivo `.env`:

```bash
# ============================================================================
# CONFIGURACIÓN DE EVOLUTION API - WhatsApp (Puerto 3000)
# ============================================================================

# URL base de Evolution API
EVOLUTION_API_URL=http://localhost:8080

# API Key de Evolution API
EVOLUTION_API_KEY=your_evolution_api_key_here

# Nombre de la instancia de Evolution API
EVOLUTION_INSTANCE=your_instance_name

# Puerto del webhook de Evolution API
EVOLUTION_WEBHOOK_PORT=3000
```

## Iniciar el Webhook

```bash
# Activar el entorno virtual
source .venv/bin/activate

# Iniciar el webhook de Evolution API
uvicorn src.support.api.evolution_webhook:app --host 0.0.0.0 --port 3000
```

O directamente:

```bash
python -m src.support.api.evolution_webhook
```

## Configurar Webhook en Evolution API

1. Accede al panel de Evolution API
2. Ve a la configuración de tu instancia
3. En la sección de Webhooks, configura:
   - **URL**: `http://tu-servidor:3000/webhook/message`
   - **Eventos**: `messages.upsert`
   
## Endpoints Disponibles

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/` | GET | Health check básico |
| `/health` | GET | Health check detallado |
| `/webhook/message` | POST | Recibe mensajes de WhatsApp |
| `/webhook/message` | GET | Verificación de webhook |

## Flujo de Mensajes

```
Usuario WhatsApp
      │
      ▼
Evolution API (Puerto 8080)
      │
      ▼ POST /webhook/message
Nagaki Webhook (Puerto 3000)
      │
      ├── Procesa mensaje con el Agente
      │
      ├── POST /message/sendText
      ▼
Evolution API
      │
      ▼
Usuario WhatsApp (Respuesta)
```

## Tipos de Mensajes Soportados

| Tipo | Soportado | Notas |
|------|-----------|-------|
| Texto simple | ✅ | Procesado completamente |
| Texto extendido | ✅ | Procesado completamente |
| Imagen con caption | ✅ | Solo se procesa el caption |
| Video con caption | ✅ | Solo se procesa el caption |
| Audio | ❌ | Responde pidiendo texto |
| Documento | ✅ | Solo se procesa el caption |
| Mensajes de grupo | ❌ | Ignorados |

## Notas Importantes

1. **Thread ID**: Se usa el número de teléfono como `thread_id` para mantener el contexto de la conversación y los puntos.

2. **Mensajes propios**: Los mensajes enviados por el bot (`fromMe: true`) son ignorados para evitar loops.

3. **Grupos**: Los mensajes de grupos (`@g.us`) son ignorados.

4. **Background Tasks**: La suma de puntos se ejecuta en segundo plano, igual que en Vapi.

5. **Concurrencia**: El webhook puede manejar múltiples conversaciones simultáneas ya que usa el número de teléfono como identificador único.

## Ejecutar Ambos Servicios

Para ejecutar Vapi y Evolution API al mismo tiempo:

```bash
# Terminal 1 - Vapi (Puerto 8000)
uvicorn src.support.api.vapi_webhook:app --host 0.0.0.0 --port 8000

# Terminal 2 - Evolution API (Puerto 3000)
uvicorn src.support.api.evolution_webhook:app --host 0.0.0.0 --port 3000
```

O usando un script:

```bash
#!/bin/bash
# start_all.sh

# Iniciar Vapi en background
uvicorn src.support.api.vapi_webhook:app --host 0.0.0.0 --port 8000 &
VAPI_PID=$!

# Iniciar Evolution API en background
uvicorn src.support.api.evolution_webhook:app --host 0.0.0.0 --port 3000 &
EVOLUTION_PID=$!

echo "Vapi PID: $VAPI_PID"
echo "Evolution API PID: $EVOLUTION_PID"

# Esperar a que terminen
wait $VAPI_PID $EVOLUTION_PID
```


