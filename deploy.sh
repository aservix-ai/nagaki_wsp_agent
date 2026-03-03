#!/bin/bash
# =============================================================================
# Script de Despliegue - Nagaki WSP Agent
# =============================================================================
# Uso: sudo ./deploy.sh
# =============================================================================

set -e

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Nagaki WSP Agent - Despliegue VPS    ${NC}"
echo -e "${GREEN}========================================${NC}"

# Verificar que se ejecuta como root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: Este script debe ejecutarse como root (sudo)${NC}"
    exit 1
fi

# Variables de configuración
APP_USER="nagaki"
APP_DIR="/opt/nagaki_wsp_agent"
VENV_DIR="$APP_DIR/.venv"
SERVICE_NAME="nagaki-agent"
PYTHON_VERSION="python3.11"

# =============================================================================
# 1. Instalar dependencias del sistema
# =============================================================================
echo -e "\n${YELLOW}[1/6] Instalando dependencias del sistema...${NC}"

apt update
apt install -y \
    software-properties-common \
    curl \
    git \
    build-essential \
    libpq-dev \
    ffmpeg \
    $PYTHON_VERSION \
    $PYTHON_VERSION-venv \
    $PYTHON_VERSION-dev \
    postgresql \
    postgresql-contrib

# =============================================================================
# 2. Crear usuario del sistema (si no existe)
# =============================================================================
echo -e "\n${YELLOW}[2/6] Configurando usuario del sistema...${NC}"

if ! id "$APP_USER" &>/dev/null; then
    useradd -r -s /bin/false -d $APP_DIR $APP_USER
    echo -e "${GREEN}Usuario '$APP_USER' creado${NC}"
else
    echo -e "${GREEN}Usuario '$APP_USER' ya existe${NC}"
fi

# =============================================================================
# 3. Configurar directorio de la aplicación
# =============================================================================
echo -e "\n${YELLOW}[3/6] Configurando directorio de la aplicación...${NC}"

# Crear directorio si no existe
mkdir -p $APP_DIR

# Copiar archivos del proyecto (asume que estás en el directorio del proyecto)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ "$SCRIPT_DIR" != "$APP_DIR" ]; then
    echo "Copiando archivos desde $SCRIPT_DIR a $APP_DIR..."
    cp -r "$SCRIPT_DIR"/* $APP_DIR/
fi

# Crear directorios necesarios
mkdir -p $APP_DIR/temp_audio
mkdir -p $APP_DIR/logs

# Ajustar permisos
chown -R $APP_USER:$APP_USER $APP_DIR
chmod -R 755 $APP_DIR

# =============================================================================
# 4. Crear entorno virtual e instalar dependencias
# =============================================================================
echo -e "\n${YELLOW}[4/6] Creando entorno virtual e instalando dependencias...${NC}"

# Crear venv
$PYTHON_VERSION -m venv $VENV_DIR

# Instalar dependencias
$VENV_DIR/bin/pip install --upgrade pip
$VENV_DIR/bin/pip install -e $APP_DIR

# Ajustar permisos del venv
chown -R $APP_USER:$APP_USER $VENV_DIR

echo -e "${GREEN}Dependencias instaladas correctamente${NC}"

# =============================================================================
# 5. Crear archivo de servicio systemd
# =============================================================================
echo -e "\n${YELLOW}[5/6] Configurando servicio systemd...${NC}"

cat > /etc/systemd/system/$SERVICE_NAME.service << EOF
[Unit]
Description=Nagaki WSP Agent - WhatsApp AI Assistant
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
Environment="PATH=$VENV_DIR/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=$APP_DIR/.env
ExecStart=$VENV_DIR/bin/uvicorn src.support.api.evolution_webhook:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
StandardOutput=append:$APP_DIR/logs/agent.log
StandardError=append:$APP_DIR/logs/agent-error.log

# Seguridad
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

# Recargar systemd
systemctl daemon-reload

echo -e "${GREEN}Servicio systemd configurado${NC}"

# =============================================================================
# 6. Verificar configuración
# =============================================================================
echo -e "\n${YELLOW}[6/6] Verificando configuración...${NC}"

# Verificar archivo .env
if [ ! -f "$APP_DIR/.env" ]; then
    echo -e "${RED}ADVERTENCIA: No se encontró archivo .env${NC}"
    echo -e "${YELLOW}Copia .env.example a .env y configura las variables:${NC}"
    echo -e "  cp $APP_DIR/.env.example $APP_DIR/.env"
    echo -e "  nano $APP_DIR/.env"
else
    echo -e "${GREEN}Archivo .env encontrado${NC}"
fi

# =============================================================================
# Resumen final
# =============================================================================
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}  Instalación completada!              ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Comandos útiles:"
echo -e "  ${YELLOW}sudo systemctl start $SERVICE_NAME${NC}    - Iniciar servicio"
echo -e "  ${YELLOW}sudo systemctl stop $SERVICE_NAME${NC}     - Detener servicio"
echo -e "  ${YELLOW}sudo systemctl restart $SERVICE_NAME${NC}  - Reiniciar servicio"
echo -e "  ${YELLOW}sudo systemctl status $SERVICE_NAME${NC}   - Ver estado"
echo -e "  ${YELLOW}sudo journalctl -u $SERVICE_NAME -f${NC}   - Ver logs en vivo"
echo ""
echo -e "Archivos de log:"
echo -e "  $APP_DIR/logs/agent.log"
echo -e "  $APP_DIR/logs/agent-error.log"
echo ""
echo -e "${YELLOW}PRÓXIMOS PASOS:${NC}"
echo -e "1. Configura el archivo .env:"
echo -e "   ${YELLOW}nano $APP_DIR/.env${NC}"
echo ""
echo -e "2. Configura PostgreSQL (si no lo has hecho):"
echo -e "   ${YELLOW}sudo -u postgres psql${NC}"
echo -e "   CREATE USER nagaki_user WITH PASSWORD 'tu_contraseña';"
echo -e "   CREATE DATABASE nagaki_agent OWNER nagaki_user;"
echo -e "   \\q"
echo ""
echo -e "3. Inicia el servicio:"
echo -e "   ${YELLOW}sudo systemctl start $SERVICE_NAME${NC}"
echo -e "   ${YELLOW}sudo systemctl enable $SERVICE_NAME${NC}  (para inicio automático)"
echo ""
