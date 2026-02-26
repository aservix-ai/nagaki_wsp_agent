#!/bin/bash
# Script de instalación para WSL/Linux

echo "🔧 Instalando proyecto nagaki-agent en modo editable..."

# Activar el venv si existe
if [ -d ".venv" ]; then
    echo "📦 Activando venv..."
    source .venv/bin/activate
fi

# Instalar el proyecto en modo editable
echo "📥 Instalando dependencias y proyecto..."
pip install -e .

echo "✅ Instalación completada!"
echo ""
echo "💡 Para verificar que todo funciona, ejecuta:"
echo "   python -c 'from src.support.agent.agent import Agent; print(\"✅ Imports funcionan!\")'"

