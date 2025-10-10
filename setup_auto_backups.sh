#!/bin/bash
# ========================================
# Field Service - Auto Backup Setup
# ========================================

set -e

echo "========================================="
echo "Setting up automatic database backups"
echo "========================================="

# Configuration
BACKUP_ROOT="/opt/backups"
PROJECT_DIR="/opt/field-service"
DB_CONTAINER="field-service-postgres-1"
DB_USER="fs_user"
DB_NAME="field_service"

# Create backup directories
mkdir -p "$BACKUP_ROOT"/{daily,weekly,monthly,manual}
chmod 755 "$BACKUP_ROOT"

echo "[1/4] Creating backup script..."

# Create backup script
cat > /usr/local/bin/field-service-backup.sh << 'EOF'
#!/bin/bash

BACKUP_ROOT="/opt/backups"
PROJECT_DIR="/opt/field-service"
DB_USER="fs_user"
DB_NAME="field_service"
DATE=$(date +%Y%m%d_%H%M%S)
DAY_OF_WEEK=$(date +%u)
DAY_OF_MONTH=$(date +%d)

# Function to create backup
create_backup() {
    local BACKUP_TYPE=$1
    local BACKUP_DIR="$BACKUP_ROOT/$BACKUP_TYPE"
    local BACKUP_FILE=""
    
    case $BACKUP_TYPE in
        "daily")
            BACKUP_FILE="field_service_${DATE}.sql.gz"
            ;;
        "weekly")
            BACKUP_FILE="field_service_week_$(date +%U)_$(date +%Y).sql.gz"
            ;;
        "monthly")
            BACKUP_FILE="field_service_$(date +%Y_%m).sql.gz"
            ;;
    esac
    
    echo "[$(date)] Creating $BACKUP_TYPE backup: $BACKUP_FILE"
    
    cd "$PROJECT_DIR"
    docker compose exec -T postgres pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_DIR/$BACKUP_FILE"
    
    if [ $? -eq 0 ]; then
        SIZE=$(du -h "$BACKUP_DIR/$BACKUP_FILE" | cut -f1)
        echo "[$(date)] Backup created successfully: $BACKUP_FILE ($SIZE)"
        
        # Cleanup old backups
        case $BACKUP_TYPE in
            "daily")
                find "$BACKUP_DIR" -name "field_service_*.sql.gz" -mtime +7 -delete
                echo "[$(date)] Cleaned up daily backups older than 7 days"
                ;;
            "weekly")
                find "$BACKUP_DIR" -name "field_service_week_*.sql.gz" -mtime +28 -delete
                echo "[$(date)] Cleaned up weekly backups older than 4 weeks"
                ;;
            "monthly")
                find "$BACKUP_DIR" -name "field_service_*.sql.gz" -mtime +365 -delete
                echo "[$(date)] Cleaned up monthly backups older than 12 months"
                ;;
        esac
    else
        echo "[$(date)] ERROR: Backup failed!"
        exit 1
    fi
}

# Determine which backup to create
if [ "$1" == "daily" ] || [ -z "$1" ]; then
    create_backup "daily"
fi

if [ "$DAY_OF_WEEK" -eq 7 ] && ([ "$1" == "weekly" ] || [ -z "$1" ]); then
    create_backup "weekly"
fi

if [ "$DAY_OF_MONTH" -eq 01 ] && ([ "$1" == "monthly" ] || [ -z "$1" ]); then
    create_backup "monthly"
fi

echo "[$(date)] Backup completed successfully"
EOF

chmod +x /usr/local/bin/field-service-backup.sh

echo "[2/4] Creating restore script..."

# Create restore script
cat > /usr/local/bin/field-service-restore.sh << 'EOF'
#!/bin/bash

if [ -z "$1" ]; then
    echo "Usage: field-service-restore.sh <backup_file>"
    echo "Available backups:"
    ls -lh /opt/backups/*/
    exit 1
fi

BACKUP_FILE=$1
PROJECT_DIR="/opt/field-service"
DB_USER="fs_user"
DB_NAME="field_service"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "========================================="
echo "DATABASE RESTORE"
echo "========================================="
echo "Backup file: $BACKUP_FILE"
echo "WARNING: This will overwrite the current database!"
read -p "Continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Restore cancelled"
    exit 0
fi

echo "Stopping bots..."
cd "$PROJECT_DIR"
docker compose stop admin-bot master-bot

echo "Restoring database..."
gunzip -c "$BACKUP_FILE" | docker compose exec -T postgres psql -U "$DB_USER" -d "$DB_NAME"

if [ $? -eq 0 ]; then
    echo "Database restored successfully!"
    echo "Starting bots..."
    docker compose start admin-bot master-bot
    echo "Restore complete!"
else
    echo "ERROR: Restore failed!"
    exit 1
fi
EOF

chmod +x /usr/local/bin/field-service-restore.sh

echo "[3/4] Setting up cron jobs..."

# Add cron jobs
(crontab -l 2>/dev/null | grep -v field-service-backup; cat << CRON
# Field Service Database Backups
0 2 * * * /usr/local/bin/field-service-backup.sh daily >> /var/log/field-service-backup.log 2>&1
0 3 * * 0 /usr/local/bin/field-service-backup.sh weekly >> /var/log/field-service-backup.log 2>&1
0 4 1 * * /usr/local/bin/field-service-backup.sh monthly >> /var/log/field-service-backup.log 2>&1
CRON
) | crontab -

echo "[4/4] Creating initial backup..."
/usr/local/bin/field-service-backup.sh daily

echo ""
echo "========================================="
echo "SETUP COMPLETE!"
echo "========================================="
echo ""
echo "Backup schedule:"
echo "  Daily:   2:00 AM (kept for 7 days)"
echo "  Weekly:  3:00 AM Sunday (kept for 4 weeks)"
echo "  Monthly: 4:00 AM 1st day (kept for 12 months)"
echo ""
echo "Backup locations:"
echo "  Daily:   $BACKUP_ROOT/daily/"
echo "  Weekly:  $BACKUP_ROOT/weekly/"
echo "  Monthly: $BACKUP_ROOT/monthly/"
echo "  Manual:  $BACKUP_ROOT/manual/"
echo ""
echo "Manual backup:"
echo "  /usr/local/bin/field-service-backup.sh daily"
echo ""
echo "Restore:"
echo "  /usr/local/bin/field-service-restore.sh <backup_file>"
echo ""
echo "View logs:"
echo "  tail -f /var/log/field-service-backup.log"
echo ""
