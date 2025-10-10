# После назначения мастера - проверьте:

docker exec field-service-postgres-1 psql -U fs_user -d field_service -c "
SELECT 
    id, 
    order_id, 
    master_id, 
    state, 
    sent_at,
    expires_at 
FROM offers 
WHERE order_id = 15 
ORDER BY id DESC;
"
