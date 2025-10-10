#!/bin/bash
# =============================================================================
# Field Service Deployment Script for Ubuntu 24.04
# =============================================================================

set -e  # Exit on error

echo "========================================="
echo "Field Service Server Setup"
echo "========================================="

# 1. Update system
echo "[1/10] Updating system packages..."
apt-get update
apt-get upgrade -y

# 2. Install basic tools
echo "[2/10] Installing basic tools..."
apt-get install -y \
    curl \
    wget \
    git \
    htop \
    nano \
    vim \
    unzip \
    ca-certificates \
    gnupg \
    lsb-release

# 3. Install Docker
echo "[3/10] Installing Docker..."
if ! command -v docker &> /dev/null; then
    # Add Docker's official GPG key
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    
    # Add Docker repository
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    
    # Start and enable Docker
    systemctl start docker
    systemctl enable docker
    echo "Docker installed successfully"
else
    echo "Docker already installed"
fi

# 4. Verify Docker installation
echo "[4/10] Verifying Docker installation..."
docker --version
docker compose version

# 5. Create project directory
echo "[5/10] Creating project directory..."
mkdir -p /opt/field-service
cd /opt/field-service

# 6. Create .env file
echo "[6/10] Creating .env configuration..."
cat > .env << 'EOF'
# Database Configuration
DATABASE_URL=postgresql+asyncpg://fs_user:fs_password@postgres:5432/field_service

# Bot Tokens (REPLACE WITH YOUR ACTUAL TOKENS!)
MASTER_BOT_TOKEN=8423680284:AAHXBq-Lmtn5cVwUoxMwhJPOAoCMVGz4688
ADMIN_BOT_TOKEN=7531617746:AAGvHQ0RySGtSSMAYenNdwyenZFkTZA6xbQ

# Timezone
TIMEZONE=Europe/Moscow

# Channels (OPTIONAL - set to your channel IDs)
# LOGS_CHANNEL_ID=-1001234567890
# ALERTS_CHANNEL_ID=-1001234567891
# REPORTS_CHANNEL_ID=-1001234567892

# Distribution settings
DISTRIBUTION_SLA_SECONDS=120
DISTRIBUTION_ROUNDS=2
HEARTBEAT_SECONDS=60

# Finance settings
COMMISSION_DEADLINE_HOURS=3
GUARANTEE_COMPANY_PAYMENT=2500

# Working hours
WORKDAY_START=10:00
WORKDAY_END=20:00
ASAP_LATE_THRESHOLD=19:30

# Admin superusers (comma-separated Telegram user IDs)
ADMIN_BOT_SUPERUSERS=
GLOBAL_ADMINS_TG_IDS=[]

# Other settings
ACCESS_CODE_TTL_HOURS=24
OVERDUE_WATCHDOG_MIN=10
EOF

echo ".env file created. IMPORTANT: Update bot tokens and channel IDs!"

# 7. Create docker-compose.yml
echo "[7/10] Creating docker-compose.yml..."
cat > docker-compose.yml << 'EOF'
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
    driver: local
EOF

echo "docker-compose.yml created"

# 8. Start PostgreSQL
echo "[8/10] Starting PostgreSQL..."
docker compose up -d postgres

echo "Waiting for PostgreSQL to be ready..."
sleep 10

# 9. Configure firewall
echo "[9/10] Configuring firewall..."
if command -v ufw &> /dev/null; then
    ufw --force enable
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow 22/tcp    # SSH
    ufw allow 80/tcp    # HTTP (for future if needed)
    ufw allow 443/tcp   # HTTPS (for future if needed)
    echo "Firewall configured"
else
    echo "UFW not found, skipping firewall configuration"
fi

# 10. Create project upload instructions
echo "[10/10] Creating instructions..."
cat > /root/NEXT_STEPS.txt << 'EOF'
=============================================================================
FIELD SERVICE - Next Steps
=============================================================================

1. UPLOAD PROJECT FILES
   You need to upload your field-service project to /opt/field-service/
   
   From your local machine, run:
   scp -r C:\ProjectF\field-service root@217.199.254.27:/opt/field-service/
   
   Or use WinSCP/FileZilla to upload the files.

2. UPDATE .ENV FILE
   Edit /opt/field-service/.env and set:
   - Your actual bot tokens
   - Channel IDs for logs/alerts
   - Admin superuser IDs
   
   nano /opt/field-service/.env

3. BUILD AND RUN BOTS
   cd /opt/field-service
   
   # Build Docker images
   docker compose build
   
   # Run database migrations
   docker compose run --rm admin-bot alembic upgrade head
   
   # Start all services
   docker compose up -d
   
   # Check logs
   docker compose logs -f

4. VERIFY DEPLOYMENT
   # Check running containers
   docker compose ps
   
   # Check bot logs
   docker compose logs admin-bot
   docker compose logs master-bot
   
   # Check PostgreSQL
   docker compose exec postgres psql -U fs_user -d field_service

5. SETUP SYSTEMD AUTO-START (Optional)
   Create /etc/systemd/system/field-service.service
   See documentation for details.

6. REGULAR MAINTENANCE
   # Backup database
   bash /opt/field-service/ops/backup_db.sh
   
   # View logs
   docker compose logs -f
   
   # Restart services
   docker compose restart
   
   # Stop services
   docker compose down

=============================================================================
Server IP: 217.199.254.27
SSH: ssh root@217.199.254.27
Project: /opt/field-service
=============================================================================
EOF

echo "========================================="
echo "Server setup completed!"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Read /root/NEXT_STEPS.txt for deployment instructions"
echo "2. Upload your project files to /opt/field-service/"
echo "3. Update .env with your actual configuration"
echo "4. Build and run the bots"
echo ""
echo "PostgreSQL is running on port 5432"
echo "Project directory: /opt/field-service"
echo ""
