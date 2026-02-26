# Guía de Instalación en WSL/Linux

## Problema: Errores de Importación

Si ves errores como:
```
ModuleNotFoundError: No module named 'src'
ImportError: cannot import name 'Agent' from 'src.support.agent.agent'
```

Es porque el proyecto no está instalado en modo editable en tu venv.

## Solución Rápida

### Opción 1: Usar el script de instalación (Recomendado)

```bash
# Dentro de WSL, en el directorio del proyecto
chmod +x install.sh
./install.sh
```

### Opción 2: Instalación Manual

```bash
# 1. Activa tu venv (si usas uno)
source .venv/bin/activate

# 2. Instala el proyecto en modo editable
pip install -e .

# 3. Verifica que funciona
python -c "from src.support.agent.agent import Agent; print('✅ Imports funcionan!')"
```

## ¿Qué hace `pip install -e .`?

- **`-e`** = modo editable (editable mode)
- **`.`** = instala el proyecto actual

Esto crea un enlace simbólico en tu venv que permite a Python encontrar los módulos `src.*` sin necesidad de modificar `PYTHONPATH`.

## Verificación

Después de instalar, prueba ejecutar:

```bash
# Probar el webhook
python -m src.support.api.vapi_webhook

# O probar el agente directamente
python -c "from src.support.agent.agent import Agent; agent = Agent(); print('✅ Agente inicializado!')"
```

## Si sigues teniendo problemas

1. **Verifica que estás en WSL**, no en PowerShell:
   ```bash
   # Deberías ver algo como: /home/tu_usuario/nagaki_agent
   pwd
   ```

2. **Verifica que el venv está activado**:
   ```bash
   which python
   # Debería mostrar: /home/tu_usuario/nagaki_agent/.venv/bin/python
   ```

3. **Reinstala desde cero**:
   ```bash
   # Elimina el venv anterior (opcional)
   rm -rf .venv
   
   # Crea un nuevo venv
   python3 -m venv .venv
   source .venv/bin/activate
   
   # Instala todo
   pip install --upgrade pip
   pip install -e .
   ```

## Error: `ImportError: no pq wrapper available`

Si ves este error:
```
ImportError: no pq wrapper available.
Attempts made:
- couldn't import psycopg 'c' implementation: No module named 'psycopg_c'
- couldn't import psycopg 'binary' implementation: No module named 'psycopg_binary'
- couldn't import psycopg 'python' implementation: libpq library not found
```

### Solución (ya incluida en pyproject.toml)

El proyecto ya incluye `psycopg[binary]` en las dependencias. Solo necesitas reinstalar:

```bash
# Si usas uv
uv pip install -e . --link-mode=copy

# O si usas pip normal
pip install -e .
```

### Alternativa: Instalar libpq del sistema

Si prefieres usar la implementación del sistema:

```bash
# En Ubuntu/Debian
sudo apt-get update
sudo apt-get install libpq-dev

# Luego reinstala psycopg
pip install --force-reinstall psycopg
```

