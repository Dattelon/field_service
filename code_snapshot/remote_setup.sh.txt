#!/bin/bash
# Auto-setup script for Field Service
set -e

echo "=== Field Service Server Setup ==="
echo "Starting at: $(date)"

# Update system
echo "[1/9] Updating system..."
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y

# Install basic tools
echo "[2/9] Installing tools..."
apt-get install -y curl wget git htop nano vim unzip ca-certificates gnupg lsb-release

# Install Docker
echo "[3/9] Installing Docker..."
if ! command -v docker &> /dev/null; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl start docker
    systemctl enable docker
fi

docker --version
docker compose version

# Create directories
echo "[4/9] Creating directories..."
mkdir -p /opt/field-service
mkdir -p /opt/backups

# Create .env
echo "[5/9] Creating .env..."
cat > /opt/field-service/.env << 'ENVEOF'
DATABASE_URL=postgresql+asyncpg://fs_user:fs_password@postgres:5432/field_service
MASTER_BOT_TOKEN=8423680284:AAHXBq-Lmtn5cVwUoxMwhJPOAoCMVGz4688
ADMIN_BOT_TOKEN=7531617746:AAGvHQ0RySGtSSMAYenNdwyenZFkTZA6xbQ
TIMEZONE=Europe/Moscow
DISTRIBUTION_SLA_SECONDS=120
DISTRIBUTION_ROUNDS=2
HEARTBEAT_SECONDS=60
COMMISSION_DEADLINE_HOURS=3
GUARANTEE_COMPANY_PAYMENT=2500
WORKDAY_START=10:00
WORKDAY_END=20:00
ASAP_LATE_THRESHOLD=19:30
ADMIN_BOT_SUPERUSERS=
GLOBAL_ADMINS_TG_IDS=[]
ACCESS_CODE_TTL_HOURS=24
OVERDUE_WATCHDOG_MIN=10
ENVEOF

# Create docker-compose.yml
echo "[6/9] Creating docker-compose.yml..."
cat > /opt/field-service/docker-compose.yml << 'DCEOF'
version: '3.8'
services:
  postgres:
    image: postgres:15-alpine
    container_name: fs_postgres
    environment:
      POSTGRES_DB: field_service
      POSTGRES_USER: fs_user
      POSTGRES_PASSWORD: fs_password
    ports:
      - "5432:5432"
    volumes:
      - fs_pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U fs_user -d field_service"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
volumes:
  fs_pgdata:
DCEOF

# Start PostgreSQL only
echo "[7/9] Starting PostgreSQL..."
cd /opt/field-service
docker compose up -d postgres
sleep 15

# Configure firewall
echo "[8/9] Configuring firewall..."
if command -v ufw &> /dev/null; then
    ufw --force enable
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow 22/tcp
fi

# Final instructions
echo "[9/9] Setup complete!"
echo ""
echo "Next steps:"
echo "1. Upload project files to /opt/field-service/"
echo "2. Update .env with real tokens"
echo "3. Build and run: cd /opt/field-service && docker compose build && docker compose up -d"
echo ""
echo "PostgreSQL is running on port 5432"
echo "Setup completed at: $(date)"
