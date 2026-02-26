# Sistema de Notificación de Clientes Cualificados

## Descripción General

Cuando un cliente alcanza el estado de **"cualificado"** (≥7 puntos), el agente Laura automáticamente:

1. ✅ Envía un mensaje cortés al cliente informándole que será remitido a un asesor profesional
2. ✅ Notifica al encargado designado con la información completa del cliente

## Configuración

### Variables de Entorno

En el archivo `.env`, configura el número del encargado que recibirá las notificaciones:

```bash
# Número del encargado para clientes cualificados (formato: 5491155555555)
QUALIFIED_MANAGER_PHONE=5491155555555
```

**Importante:** 
- El número debe incluir el código de país (ej: 549 para Argentina)
- No incluyas espacios, guiones ni paréntesis
- No incluyas el prefijo `@s.whatsapp.net` (se agrega automáticamente)

## Flujo de Trabajo

### 1. Cliente Alcanza Estado "Cualificado"

Cuando un cliente:
- Acumula 7 o más puntos de cualificación
- Es redirigido al nodo `qualified`

### 2. Mensaje al Cliente

Laura envía automáticamente un mensaje cortés y profesional como:

```
¡Excelente! Muchas gracias por toda la información que me has compartido. 
Veo que tienes un perfil muy interesante para nuestras propiedades. 

En este momento voy a derivar tu contacto a uno de nuestros asesores 
profesionales especializados, quien te brindará una atención personalizada 
y te presentará las mejores opciones de acuerdo a tus necesidades. 
Te contactarán muy pronto. ¡Fue un placer asistirte! 😊
```

### 3. Notificación al Encargado

El encargado recibe un mensaje con:

```
🌟 *NUEVO CLIENTE CUALIFICADO* 🌟

📱 *Cliente:* 5491155555555
⭐ *Puntos:* 8
🏢 *Tipo de propiedad:* cesion_remate
💼 *Interesado:* Sí

📝 *Últimos mensajes:*
Cliente: Hola, estoy interesado en una cesión de remate...
Laura: ¡Excelente! Permíteme hacerte algunas preguntas...
Cliente: Sí, tengo capacidad de inversión inmediata...
Laura: Perfecto, confirmo que tienes un perfil ideal...
Cliente: ¿Cuándo podemos avanzar?

---
Este cliente ha sido cualificado exitosamente y está listo para atención personalizada.
```

## Estructura Técnica

### Archivos Modificados

1. **`.env`** - Variable de entorno `QUALIFIED_MANAGER_PHONE`
2. **`src/support/agent/state.py`** - Agregado campo `thread_id` al AgentState
3. **`src/support/agent/nodes/qualified/node.py`** - Lógica de notificación
4. **`src/support/api/evolution_webhook.py`** - Pasa `thread_id` al estado inicial

### Función Principal: `notify_manager()`

```python
async def notify_manager(client_phone: str, state: AgentState) -> None:
    """
    Notifica al encargado sobre un cliente cualificado.
    
    Args:
        client_phone: Número de teléfono del cliente
        state: Estado actual del agente con información del cliente
    """
```

**Características:**
- ✅ Ejecuta de forma asíncrona (no bloquea el agente)
- ✅ Extrae información relevante del estado (puntos, tipo de propiedad, etc.)
- ✅ Incluye contexto de los últimos 5 mensajes
- ✅ Manejo robusto de errores con logging detallado
- ✅ Validación de configuración (advierte si falta el número del encargado)

## Logs y Monitoreo

### Logs Exitosos

```
🌟 QUALIFIED NODE - Cliente cualificado, generando mensaje de derivación
📲 Notificando al encargado (5491***) sobre cliente cualificado: 549115***
✅ Mensaje enviado a 5491***
✅ Encargado notificado exitosamente sobre cliente 549115***
```

### Logs de Advertencia

```
⚠️ QUALIFIED_MANAGER_PHONE no está configurado en .env
```

### Logs de Error

```
❌ No se pudo notificar al encargado sobre cliente 549115***
❌ Error al notificar al encargado: [detalle del error]
```

## Pruebas

### Probar la Funcionalidad

1. Configura `QUALIFIED_MANAGER_PHONE` en `.env`
2. Inicia el servidor: `uv run uvicorn src.support.api.evolution_webhook:app --reload --port 3000`
3. Simula un cliente llegando a 7+ puntos
4. Verifica:
   - ✅ Cliente recibe mensaje de derivación cortés
   - ✅ Encargado recibe notificación con datos del cliente
   - ✅ Logs muestran ejecución exitosa

### Validar sin Configuración

Si `QUALIFIED_MANAGER_PHONE` no está configurado:
- ✅ El agente continúa funcionando normalmente
- ✅ El cliente recibe el mensaje de derivación
- ⚠️ Se registra advertencia en logs
- ❌ No se envía notificación al encargado

## Personalización

### Modificar el Mensaje al Cliente

Edita `QUALIFIED_SYSTEM_PROMPT` en `src/support/agent/nodes/qualified/node.py`:

```python
QUALIFIED_SYSTEM_PROMPT = """Eres Laura, de Grupo Nagaki.
[Tu prompt personalizado aquí]
"""
```

### Modificar el Mensaje al Encargado

Edita la función `notify_manager()` en el mismo archivo:

```python
notification_message = f"""🌟 *NUEVO CLIENTE CUALIFICADO* 🌟
[Tu formato personalizado aquí]
"""
```

### Añadir Más Información

Puedes incluir más datos del estado en la notificación:

```python
# Ejemplo: agregar última fecha de contacto
last_contact = state.get("last_contact", "No disponible")

notification_message = f"""...
📅 *Último contacto:* {last_contact}
..."""
```

## Seguridad y Privacidad

- ⚠️ El archivo `.env` NO debe subirse a git (ya está en `.gitignore`)
- ⚠️ Los números de teléfono se ocultan parcialmente en los logs (ej: `5491***`)
- ⚠️ Solo se comparte información relevante para el seguimiento comercial

## Soporte

Si encuentras problemas:

1. Verifica que `QUALIFIED_MANAGER_PHONE` esté configurado correctamente
2. Revisa los logs del servidor para mensajes de error
3. Confirma que Evolution API esté funcionando correctamente
4. Verifica que el número del encargado pueda recibir mensajes de WhatsApp
