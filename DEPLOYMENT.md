# Guía de Despliegue - Nagaki WSP Agent

## Requisitos del VPS

- Ubuntu 22.04 LTS (recomendado) o Debian 11+
- Mínimo 2GB RAM
- 20GB de disco
- Acceso root/sudo

---

## Instalación Rápida

### 1. Subir el proyecto al VPS

```bash
# Opción A: Clonar desde Git
git clone https://tu-repo.git /root/nagaki_wsp_agent
cd /root/nagaki_wsp_agent

# Opción B: Subir con scp desde tu máquina local
scp -r /ruta/local/nagaki_wsp_agent root@tu-vps-ip:/root/
```

### 2. Ejecutar el script de despliegue

```bash
cd /root/nagaki_wsp_agent
chmod +x deploy.sh
sudo ./deploy.sh
```

---

## Configuración Manual (si prefieres hacerlo paso a paso)

### 1. Instalar dependencias

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev \
    postgresql postgresql-contrib libpq-dev ffmpeg git curl
```

### 2. Configurar PostgreSQL

```bash
# Acceder a PostgreSQL
sudo -u postgres psql

# Crear usuario y base de datos
CREATE USER nagaki_user WITH PASSWORD 'tu_contraseña_segura';
CREATE DATABASE nagaki_agent OWNER nagaki_user;
GRANT ALL PRIVILEGES ON DATABASE nagaki_agent TO nagaki_user;
\q

# Si hay problemas de autenticación, editar pg_hba.conf:
sudo nano /etc/postgresql/*/main/pg_hba.conf
# Cambiar 'peer' por 'md5' en las líneas de autenticación local
sudo systemctl restart postgresql
```

### 3. Configurar la aplicación

```bash
# Ir al directorio
cd /opt/nagaki_wsp_agent

# Crear entorno virtual
python3.11 -m venv .venv
source .venv/bin/activate

# Instalar dependencias
pip install --upgrade pip
pip install -e .
```

### 4. Configurar variables de entorno

```bash
cp .env.example .env
nano .env
```

Variables importantes a configurar:

```env
# OpenAI
OPENAI_API_KEY=sk-...

# PostgreSQL
POSTGRES_CONNECTION_STRING=postgresql://nagaki_user:tu_contraseña@localhost:5432/nagaki_agent

# Evolution API
EVOLUTION_API_URL=http://localhost:8080
EVOLUTION_API_KEY=tu_api_key
EVOLUTION_INSTANCE=tu_instancia

# Redis (opcional, para buffer de mensajes)
REDIS_URL=redis://localhost:6379

# Inmobigrama API
INMOBIGRAMA_API_URL=https://api.inmobigrama.com
INMOBIGRAMA_API_KEY=tu_api_key

# ElevenLabs (para audio)
ELEVENLABS_API_KEY=tu_api_key
```

### 5. Crear servicio systemd

```bash
sudo nano /etc/systemd/system/nagaki-agent.service
```

Contenido:

```ini
[Unit]
Description=Nagaki WSP Agent
After=network.target postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/nagaki_wsp_agent
Environment="PATH=/opt/nagaki_wsp_agent/.venv/bin"
EnvironmentFile=/opt/nagaki_wsp_agent/.env
ExecStart=/opt/nagaki_wsp_agent/.venv/bin/uvicorn src.support.api.evolution_webhook:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 6. Habilitar e iniciar el servicio

```bash
sudo systemctl daemon-reload
sudo systemctl enable nagaki-agent
sudo systemctl start nagaki-agent
```

---

## Comandos Útiles

```bash
# Ver estado del servicio
sudo systemctl status nagaki-agent

# Ver logs en tiempo real
sudo journalctl -u nagaki-agent -f

# Reiniciar servicio
sudo systemctl restart nagaki-agent

# Detener servicio
sudo systemctl stop nagaki-agent

# Ver logs de la aplicación
tail -f /opt/nagaki_wsp_agent/logs/agent.log
```

---

## Configurar Nginx (Opcional - Reverse Proxy)

Si quieres usar un dominio con SSL:

```bash
sudo apt install nginx certbot python3-certbot-nginx

sudo nano /etc/nginx/sites-available/nagaki-agent
```

```nginx
server {
    listen 80;
    server_name tu-dominio.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_cache_bypass $http_upgrade;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/nagaki-agent /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# Obtener SSL con Let's Encrypt
sudo certbot --nginx -d tu-dominio.com
```

---

## Configurar Webhook en Evolution API

Una vez que el servicio esté corriendo, configura el webhook en Evolution API:

```bash
curl -X POST "http://localhost:8080/webhook/set/TU_INSTANCIA" \
  -H "Content-Type: application/json" \
  -H "apikey: TU_API_KEY" \
  -d '{
    "webhook": {
      "enabled": true,
      "url": "http://localhost:8000/webhook/message",
      "webhookByEvents": false,
      "events": ["MESSAGES_UPSERT", "CONNECTION_UPDATE"]
    }
  }'
```

O si usas dominio con SSL:

```bash
curl -X POST "http://localhost:8080/webhook/set/TU_INSTANCIA" \
  -H "Content-Type: application/json" \
  -H "apikey: TU_API_KEY" \
  -d '{
    "webhook": {
      "enabled": true,
      "url": "https://tu-dominio.com/webhook/message",
      "webhookByEvents": false,
      "events": ["MESSAGES_UPSERT", "CONNECTION_UPDATE"]
    }
  }'
```

---

## Solución de Problemas

### Error de conexión a PostgreSQL

```bash
# Verificar que PostgreSQL está corriendo
sudo systemctl status postgresql

# Probar conexión
psql postgresql://nagaki_user:tu_contraseña@localhost:5432/nagaki_agent -c "SELECT 1;"

# Si falla, revisar pg_hba.conf
sudo nano /etc/postgresql/*/main/pg_hba.conf
# Cambiar 'peer' por 'md5'
sudo systemctl restart postgresql
```

### El servicio no inicia

```bash
# Ver logs detallados
sudo journalctl -u nagaki-agent -n 50 --no-pager

# Verificar que el .env existe y tiene las variables correctas
cat /opt/nagaki_wsp_agent/.env
```

### Permisos

```bash
# Asegurar permisos correctos
sudo chown -R root:root /opt/nagaki_wsp_agent
sudo chmod -R 755 /opt/nagaki_wsp_agent
```
