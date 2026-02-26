# Sistema Anti-Spam para Laura

## Descripción General

Sistema robusto de detección y bloqueo de usuarios que realizan comportamientos abusivos o spam. Protege al agente Laura de:

- 🚫 **Flooding** - Mensajes muy seguidos
- 🤬 **Lenguaje ofensivo** - Insultos y groserías
- 🔤 **Gibberish** - Mensajes sin sentido
- 🔁 **Repetición** - Mensajes idénticos repetidos

## Sistema de Strikes

### Funcionamiento

El sistema asigna "strikes" (faltas) según la gravedad del comportamiento:

| Comportamiento | Strikes | Descripción |
|---|---|---|
| **Flooding (10 seg)** | 2 | 4+ mensajes en 10 segundos |
| **Flooding (1 min)** | 1 | 8+ mensajes en 1 minuto |
| **Lenguaje ofensivo** | 3 | Insultos, groserías, agresiones |
| **Gibberish** | 1 | Mensajes sin sentido (aaaaa, 12345, etc) |
| **Repetición** | 2 | Mismo mensaje 3+ veces |

### Umbrales

```
0-2 strikes: Usuario normal ✅
3-4 strikes: ADVERTENCIA ⚠️
5+ strikes: BLOQUEADO 🚫
```

## Flujo de Detección

### 1. Usuario Normal (0-2 strikes)

```
Cliente: "Hola, estoy interesado en una propiedad"
Sistema: ✅ Procesa normalmente
```

### 2. Primera Advertencia (3-4 strikes)

```
Cliente: [envía 5 mensajes en 5 segundos]
Sistema: ⚠️ Advertencia automática
Laura: "⚠️ Advertencia: Por favor, evita enviar mensajes muy seguidos..."
Sistema: ✅ Continúa procesando el mensaje
```

### 3. Bloqueo (5+ strikes)

```
Cliente: [insulta al agente]
Sistema: 🚫 Usuario BLOQUEADO
Laura: "Lo sentimos, pero tu cuenta ha sido bloqueada temporalmente..."
Sistema: ❌ Rechaza todos los mensajes futuros
```

## Detección de Spam

### Flooding (Mensajes muy seguidos)

**Límites configurables:**
- Máximo 4 mensajes en 10 segundos
- Máximo 8 mensajes por minuto

**Ejemplo bloqueado:**
```
[00:00] Cliente: Hola
[00:02] Cliente: Hola
[00:04] Cliente: Responde
[00:06] Cliente: Por favor
[00:08] Cliente: Urgente
→ 🚨 5 mensajes en 8 segundos = 2 strikes
```

### Lenguaje Ofensivo

**Lista de palabras bloqueadas:**
- Insultos comunes (idiota, estúpido, imbécil, etc.)
- Groserías (vulgaridades diversas)
- Palabras agresivas (cállate, lárgate, etc.)

**Ejemplo bloqueado:**
```
Cliente: "Eres una idiota"
→ 🚨 Lenguaje ofensivo detectado = 3 strikes
```

### Gibberish (Mensajes sin sentido)

**Patrones detectados:**
- Solo vocales repetidas: `aaaaa`, `eeeee`
- Solo consonantes: `bcdfgh`
- Caracteres repetidos: `jaaaaaaaa`
- Solo números: `123456`
- Solo símbolos: `!@#$%`
- Mensajes de 1-2 letras no válidos

**Mensajes cortos válidos:** `si`, `no`, `ok`, `ya`, `a`

**Ejemplo bloqueado:**
```
Cliente: "aaaaaaaaa"
→ 🚨 Gibberish detectado = 1 strike
```

### Repetición

**Detección:**
- Guarda últimos 10 mensajes del usuario
- Cuenta repeticiones del mismo mensaje normalizado

**Ejemplo bloqueado:**
```
Cliente: "Hola"
Cliente: "Hola"
Cliente: "Hola"
Cliente: "Hola"
→ 🚨 Mensaje repetido 4 veces = 2 strikes
```

## Endpoints Administrativos

### 1. Consultar Estado de Usuario

```bash
GET http://localhost:3000/admin/spam/status/{phone_number}
```

**Ejemplo Request:**
```bash
curl http://localhost:3000/admin/spam/status/5491155555555
```

**Ejemplo Response:**
```json
{
  "phone": "5491155555555",
  "status": {
    "phone": "5491155555555",
    "strikes": 3,
    "blocked": false,
    "warnings": 1,
    "blocked_since": null,
    "blocked_since_formatted": null
  },
  "message": "Usuario activo"
}
```

### 2. Desbloquear Usuario

```bash
POST http://localhost:3000/admin/spam/unblock/{phone_number}
```

**Ejemplo Request:**
```bash
curl -X POST http://localhost:3000/admin/spam/unblock/5491155555555
```

**Ejemplo Response:**
```json
{
  "success": true,
  "message": "Usuario 5491155555555 desbloqueado exitosamente",
  "phone": "5491155555555"
}
```

### 3. Resetear Strikes

```bash
POST http://localhost:3000/admin/spam/reset-strikes/{phone_number}
```

Resetea los strikes sin desbloquear al usuario.

**Ejemplo Request:**
```bash
curl -X POST http://localhost:3000/admin/spam/reset-strikes/5491155555555
```

**Ejemplo Response:**
```json
{
  "success": true,
  "message": "Strikes reseteados para 5491155555555",
  "phone": "5491155555555",
  "new_status": {
    "strikes": 0,
    "blocked": false,
    "warnings": 0
  }
}
```

### 4. Listar Usuarios Bloqueados

```bash
GET http://localhost:3000/admin/spam/blocked-users
```

**Ejemplo Request:**
```bash
curl http://localhost:3000/admin/spam/blocked-users
```

**Ejemplo Response:**
```json
{
  "total_blocked": 2,
  "blocked_users": [
    {
      "phone": "5491155555555",
      "strikes": 7,
      "blocked_since": "2026-01-15 23:15:30",
      "blocked_timestamp": 1737859530.123
    },
    {
      "phone": "5491166666666",
      "strikes": 6,
      "blocked_since": "2026-01-15 22:45:12",
      "blocked_timestamp": 1737857712.456
    }
  ]
}
```

## Mensajes al Usuario

### Mensaje de Advertencia (3-4 strikes)

```
⚠️ *Advertencia*: Por favor, evita enviar mensajes muy seguidos o contenido 
inapropiado. Continuaremos la conversación de manera respetuosa. 
Gracias por tu comprensión.
```

### Mensaje de Bloqueo (5+ strikes)

```
Lo sentimos, pero tu cuenta ha sido bloqueada temporalmente debido a 
comportamiento inapropiado. Si crees que esto es un error, por favor 
contacta a soporte.
```

## Logs del Sistema

### Detección de Spam

```
🚨 Spam detectado de 549115***: Flooding: 5 mensajes en 10 segundos (+2 strikes, total: 5)
```

### Primera Advertencia

```
⚠️ Usuario 549115*** recibió advertencia: ADVERTENCIA: Flooding: 5 mensajes en 10 segundos
```

### Bloqueo

```
🚫 Usuario 549115*** ha sido BLOQUEADO por spam
🚫 Usuario 549115*** está BLOQUEADO: BLOQUEADO: Lenguaje ofensivo detectado
```

### Desbloqueo Manual

```
✅ Usuario 549115*** ha sido desbloqueado
```

### Reset de Strikes

```
🔄 Strikes reseteados para 549115***
```

## Configuración

### Parámetros del SpamDetector

En `/src/support/utils/spam_detector.py`:

```python
spam_detector = SpamDetector(
    max_messages_per_minute=8,      # Máximo mensajes por minuto
    max_messages_per_10_seconds=4,  # Máximo mensajes en 10 segundos
    strike_threshold=5,              # Strikes para bloqueo
    warning_threshold=3              # Strikes para advertencia
)
```

### Personalizar Lista de Palabras Ofensivas

Edita `OFFENSIVE_WORDS` en el mismo archivo:

```python
OFFENSIVE_WORDS = [
    "idiota", "estúpid", "imbécil",
    # Agrega más palabras aquí
]
```

### Personalizar Mensajes Cortos Válidos

Edita `VALID_SHORT_MESSAGES`:

```python
VALID_SHORT_MESSAGES = ["si", "no", "ok", "ya", "ah", "oh", "eh", "a"]
```

## Casos de Uso

### Caso 1: Cliente Ansioso

```
[10:00:00] Cliente: Hola
[10:00:05] Cliente: Estoy interesado
[10:00:10] Cliente: ¿Me pueden ayudar?
[10:00:15] Cliente: Por favor
→ ✅ 4 mensajes en 15 segundos = Dentro del límite
```

### Caso 2: Spammer

```
[10:00:00] Cliente: Hola
[10:00:02] Cliente: Hola
[10:00:04] Cliente: Hola  
[10:00:06] Cliente: Hola
[10:00:08] Cliente: Hola
→ 🚨 5 mensajes en 8 segundos = 2 strikes
→ 🚨 Mensaje repetido 5 veces = 2 strikes
→ Total: 4 strikes = ADVERTENCIA
```

### Caso 3: Usuario Agresivo

```
Cliente: "Esto es una basura"
→ 🚨 Lenguaje ofensivo = 3 strikes = ADVERTENCIA

Cliente: "Son unos estafadores"
→ 🚨 Lenguaje ofensivo = 3 strikes
→ Total: 6 strikes = BLOQUEADO 🚫
```

## Gestión de Bloqueos

### Política Recomendada

1. **Revisión diaria** de usuarios bloqueados
2. **Investigar** casos con muchos strikes
3. **Desbloquear** si fue un falso positivo
4. **Mantener bloqueados** usuarios claramente abusivos

### Proceso de Desbloqueo

```bash
# 1. Verificar estado
curl http://localhost:3000/admin/spam/status/549115XXXXX

# 2. Si es falso positivo, desbloquear
curl -X POST http://localhost:3000/admin/spam/unblock/549115XXXXX

# 3. Verificar que quedó limpio
curl http://localhost:3000/admin/spam/status/549115XXXXX
```

## Persistencia

⚠️ **Nota Importante:** Actualmente, los datos de spam se almacenan **en memoria**.

**Implicaciones:**
- ✅ Muy rápido y eficiente
- ❌ Se pierde al reiniciar el servidor
- ❌ No compartido entre múltiples instancias

**Mejora Futura:**
- Implementar persistencia en Redis
- Compartir estado entre múltiples workers
- Mantener historial de bloqueos

## Monitoreo

### Logs a Observar

```bash
# Ver todos los eventos de spam
tail -f logs/webhook.log | grep "🚨\|⚠️\|🚫"

# Ver solo bloqueos
tail -f logs/webhook.log | grep "BLOQUEADO"

# Ver advertencias
tail -f logs/webhook.log | grep "ADVERTENCIA"
```

### Métricas Útiles

- **Usuarios con strikes activos:** Revisar periódicamente
- **Usuarios bloqueados:** Investigar patterns
- **Palabras ofensivas más comunes:** Ajustar lista
- **Tasa de falsos positivos:** Optimizar umbrales

## Troubleshooting

### Falso Positivo: Cliente Legítimo Bloqueado

**Problema:** Un cliente válido fue bloqueado por error.

**Solución:**
```bash
curl -X POST http://localhost:3000/admin/spam/unblock/PHONE_NUMBER
```

### Usuario Sigue Haciendo Spam Después de Desbloquearlo

**Problema:** El usuario vuelve a hacer spam inmediatamente.

**Solución:**
1. No desbloquear más veces
2. Considerar bloqueo permanente a nivel de WhatsApp
3. Agregar a blacklist manual si se implementa

### Mensajes Legítimos Detectados como Gibberish

**Problema:** Mensajes válidos cortos son marcados como spam.

**Solución:**
1. Agregar a `VALID_SHORT_MESSAGES`
2. Ajustar patrones de gibberish
3. Reducir strikes por gibberish de 1 a 0.5

## Seguridad

- 🔒 Los endpoints admin NO tienen autenticación (agregar en producción)
- 🔒 Validar números de teléfono antes de procesar
- 🔒 Rate limiting a nivel de API (implementar con middleware)
- 🔒 Logs de auditoría para desbloqueos manuales

## Próximas Mejoras

- [ ] Persistencia en Redis
- [ ] Autenticación en endpoints admin
- [ ] Dashboard web para gestión visual
- [ ] Análisis de patrones con ML
- [ ] Bloqueo temporal con auto-desbloqueo
- [ ] Notificaciones a admin cuando hay bloqueos
- [ ] Whitelist de números VIP
- [ ] Integración con Evolution API para bloqueo real
