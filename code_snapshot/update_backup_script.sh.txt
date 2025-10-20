#!/bin/bash
# Патч для добавления поддержки manual бекапов

echo "Обновление скрипта field-service-backup.sh..."

# Создаём обновлённую версию скрипта
cat > /tmp/field-service-backup-new.sh << 'EOF'
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
        "manual")
            BACKUP_FILE="field_service_manual_${DATE}.sql.gz"
            ;;
    esac
    
    echo "[$(date)] Creating $BACKUP_TYPE backup: $BACKUP_FILE"
    
    cd "$PROJECT_DIR"
    docker compose exec -T postgres pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_DIR/$BACKUP_FILE"
    
    if [ $? -eq 0 ]; then
        SIZE=$(du -h "$BACKUP_DIR/$BACKUP_FILE" | cut -f1)
        echo "[$(date)] Backup created successfully: $BACKUP_FILE ($SIZE)"
        
        # Cleanup old backups (only for automated types)
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
if [ "$1" == "manual" ]; then
    create_backup "manual"
    exit 0
fi

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

# Заменяем старый скрипт
sudo cp /tmp/field-service-backup-new.sh /usr/local/bin/field-service-backup.sh
sudo chmod +x /usr/local/bin/field-service-backup.sh

# Создаём директорию для manual бекапов если её нет
sudo mkdir -p /opt/backups/manual
sudo chmod 755 /opt/backups/manual

echo "✅ Скрипт успешно обновлён!"
echo "Тестируем manual бекап..."
/usr/local/bin/field-service-backup.sh manual

echo ""
echo "Проверяем созданный бекап:"
ls -lh /opt/backups/manual/ | tail -5
