# Sistema Anti-Spam - Guía Rápida

## Inicio Rápido

### 1. Probar el Sistema

```bash
# Ejecutar tests interactivos
python test_spam_detector.py
```

O con uv:
```bash
uv run python test_spam_detector.py
```

### 2. Gestionar Usuarios Bloqueados

**Ver estado de un usuario:**
```bash
curl http://localhost:3000/admin/spam/status/5491155555555
```

**Listar todos los bloqueados:**
```bash
curl http://localhost:3000/admin/spam/blocked-users
```

**Desbloquear un usuario:**
```bash
curl -X POST http://localhost:3000/admin/spam/unblock/5491155555555
```

**Resetear strikes:**
```bash
curl -X POST http://localhost:3000/admin/spam/reset-strikes/5491155555555
```

## Configuración Actual

```
Flooding:
  - 4 mensajes en 10 segundos = 2 strikes
  - 8 mensajes en 1 minuto = 1 strike

Lenguaje Ofensivo:
  - Insultos/groserías = 3 strikes

Gibberish:
  - Mensajes sin sentido = 1 strike

Repetición:
  - Mismo mensaje 3+ veces = 2 strikes

Umbrales:
  - 3 strikes = ADVERTENCIA
  - 5 strikes = BLOQUEADO
```

## Funcionamiento

### Usuario Normal
```
✅ Mensajes normales → Sin strikes
```

### Usuario con Advertencia
```
⚠️ 3-4 strikes → Recibe advertencia automática
✅ Puede seguir usando el servicio
```

### Usuario Bloqueado
```
🚫 5+ strikes → Bloqueado automáticamente
❌ No puede enviar más mensajes
📧 Recibe mensaje de bloqueo
```

## Archivos Importantes

- **Detector:** `/src/support/utils/spam_detector.py`
- **Integración:** `/src/support/api/evolution_webhook.py`
- **Documentación:** `/docs/ANTI_SPAM_SYSTEM.md`
- **Tests:** `/test_spam_detector.py`

## Logs

```bash
# Ver eventos de spam en tiempo real
tail -f logs/*.log | grep "🚨\|⚠️\|🚫"
```

## Ajustar Configuración

Edita `/src/support/utils/spam_detector.py`:

```python
spam_detector = SpamDetector(
    max_messages_per_minute=8,      # Ajustar límite
    max_messages_per_10_seconds=4,  # Ajustar límite
    strike_threshold=5,              # Ajustar para bloqueo
    warning_threshold=3              # Ajustar para advertencia
)
```

## Soporte

Ver documentación completa: `/docs/ANTI_SPAM_SYSTEM.md`
