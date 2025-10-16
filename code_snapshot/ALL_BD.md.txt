# База данных Field Service - Полная структура и данные

**Дата сбора:** 2025-10-16 00:54:28

---

## Обзор

Всего таблиц в базе: **26**


### Список таблиц:

1. `admin_audit_log`
2. `alembic_version`
3. `attachments`
4. `cities`
5. `commission_deadline_notifications`
6. `commissions`
7. `distribution_metrics`
8. `districts`
9. `geocache`
10. `master_districts`
11. `master_invite_codes`
12. `master_skills`
13. `masters`
14. `notifications_outbox`
15. `offers`
16. `order_autoclose_queue`
17. `order_status_history`
18. `orders`
19. `referral_rewards`
20. `referrals`
21. `settings`
22. `skills`
23. `staff_access_code_cities`
24. `staff_access_codes`
25. `staff_cities`
26. `staff_users`

---


## 1. Таблица: `admin_audit_log`

**Количество записей:** 0

### Структура таблицы

```sql
                                                                   Table "public.admin_audit_log"
    Column    |           Type           | Collation | Nullable |                   Default                   | Storage  | Compression | Stats target | Description 
--------------+--------------------------+-----------+----------+---------------------------------------------+----------+-------------+--------------+-------------
 id           | integer                  |           | not null | nextval('admin_audit_log_id_seq'::regclass) | plain    |             |              | 
 admin_id     | integer                  |           |          |                                             | plain    |             |              | 
 master_id    | integer                  |           |          |                                             | plain    |             |              | 
 action       | character varying(64)    |           | not null |                                             | extended |             |              | 
 payload_json | jsonb                    |           | not null | '{}'::jsonb                                 | extended |             |              | 
 created_at   | timestamp with time zone |           | not null | now()                                       | plain    |             |              | 
Indexes:
    "pk_admin_audit_log" PRIMARY KEY, btree (id)
    "ix_admin_audit_log_admin_id" btree (admin_id)
    "ix_admin_audit_log_created_at" btree (created_at)
    "ix_admin_audit_log_master_id" btree (master_id)
Foreign-key constraints:
    "fk_admin_audit_log__admin_id__staff_users" FOREIGN KEY (admin_id) REFERENCES staff_users(id) ON DELETE SET NULL
    "fk_admin_audit_log__master_id__masters" FOREIGN KEY (master_id) REFERENCES masters(id) ON DELETE SET NULL
Access method: heap


```

### Данные (до 1000 записей)

```
 id | admin_id | master_id | action | payload_json | created_at 
----+----------+-----------+--------+--------------+------------
(0 rows)


```


---


## 2. Таблица: `alembic_version`

**Количество записей:** 1

### Структура таблицы

```sql
                                               Table "public.alembic_version"
   Column    |         Type          | Collation | Nullable | Default | Storage  | Compression | Stats target | Description 
-------------+-----------------------+-----------+----------+---------+----------+-------------+--------------+-------------
 version_num | character varying(32) |           | not null |         | extended |             |              | 
Indexes:
    "alembic_version_pkc" PRIMARY KEY, btree (version_num)
Access method: heap


```

### Данные (до 1000 записей)

```
 version_num  
--------------
 4c2465ccb4e5
(1 row)


```


---


## 3. Таблица: `attachments`

**Количество записей:** 0

### Структура таблицы

```sql
                                                                       Table "public.attachments"
        Column         |           Type           | Collation | Nullable |                 Default                 | Storage  | Compression | Stats target | Description 
-----------------------+--------------------------+-----------+----------+-----------------------------------------+----------+-------------+--------------+-------------
 id                    | integer                  |           | not null | nextval('attachments_id_seq'::regclass) | plain    |             |              | 
 entity_type           | attachment_entity        |           | not null |                                         | plain    |             |              | 
 entity_id             | bigint                   |           | not null |                                         | plain    |             |              | 
 file_type             | attachment_file_type     |           | not null |                                         | plain    |             |              | 
 file_id               | character varying(256)   |           | not null |                                         | extended |             |              | 
 file_unique_id        | character varying(256)   |           |          |                                         | extended |             |              | 
 file_name             | character varying(256)   |           |          |                                         | extended |             |              | 
 mime_type             | character varying(128)   |           |          |                                         | extended |             |              | 
 size                  | integer                  |           |          |                                         | plain    |             |              | 
 caption               | text                     |           |          |                                         | extended |             |              | 
 uploaded_by_master_id | integer                  |           |          |                                         | plain    |             |              | 
 uploaded_by_staff_id  | integer                  |           |          |                                         | plain    |             |              | 
 created_at            | timestamp with time zone |           |          | now()                                   | plain    |             |              | 
 document_type         | character varying(32)    |           |          |                                         | extended |             |              | 
Indexes:
    "pk_attachments" PRIMARY KEY, btree (id)
    "ix_attachments__etype_eid" btree (entity_type, entity_id)
Foreign-key constraints:
    "fk_attachments__uploaded_by_master_id__masters" FOREIGN KEY (uploaded_by_master_id) REFERENCES masters(id) ON DELETE SET NULL
    "fk_attachments__uploaded_by_staff_id__staff_users" FOREIGN KEY (uploaded_by_staff_id) REFERENCES staff_users(id) ON DELETE SET NULL
Access method: heap


```

### Данные (до 1000 записей)

```
 id | entity_type | entity_id | file_type | file_id | file_unique_id | file_name | mime_type | size | caption | uploaded_by_master_id | uploaded_by_staff_id | created_at | document_type 
----+-------------+-----------+-----------+---------+----------------+-----------+-----------+------+---------+-----------------------+----------------------+------------+---------------
(0 rows)


```


---


## 4. Таблица: `cities`

**Количество записей:** 3

### Структура таблицы

```sql
                                                                   Table "public.cities"
    Column    |           Type           | Collation | Nullable |              Default               | Storage  | Compression | Stats target | Description 
--------------+--------------------------+-----------+----------+------------------------------------+----------+-------------+--------------+-------------
 id           | integer                  |           | not null | nextval('cities_id_seq'::regclass) | plain    |             |              | 
 name         | character varying(120)   |           | not null |                                    | extended |             |              | 
 is_active    | boolean                  |           | not null | true                               | plain    |             |              | 
 created_at   | timestamp with time zone |           |          | now()                              | plain    |             |              | 
 updated_at   | timestamp with time zone |           |          | now()                              | plain    |             |              | 
 timezone     | character varying(64)    |           |          |                                    | extended |             |              | 
 centroid_lat | double precision         |           |          |                                    | plain    |             |              | 
 centroid_lon | double precision         |           |          |                                    | plain    |             |              | 
Indexes:
    "pk_cities" PRIMARY KEY, btree (id)
    "uq_cities__name" UNIQUE CONSTRAINT, btree (name)
Referenced by:
    TABLE "distribution_metrics" CONSTRAINT "distribution_metrics_city_id_fkey" FOREIGN KEY (city_id) REFERENCES cities(id) ON DELETE CASCADE
    TABLE "districts" CONSTRAINT "fk_districts__city_id__cities" FOREIGN KEY (city_id) REFERENCES cities(id) ON DELETE CASCADE
    TABLE "master_invite_codes" CONSTRAINT "fk_master_invite_codes__city_id__cities" FOREIGN KEY (city_id) REFERENCES cities(id) ON DELETE SET NULL
    TABLE "masters" CONSTRAINT "fk_masters__city_id__cities" FOREIGN KEY (city_id) REFERENCES cities(id) ON DELETE SET NULL
    TABLE "orders" CONSTRAINT "fk_orders__city_id__cities" FOREIGN KEY (city_id) REFERENCES cities(id) ON DELETE RESTRICT
    TABLE "staff_access_code_cities" CONSTRAINT "fk_staff_access_code_cities__city_id__cities" FOREIGN KEY (city_id) REFERENCES cities(id) ON DELETE CASCADE
    TABLE "staff_access_codes" CONSTRAINT "fk_staff_access_codes__city_id__cities" FOREIGN KEY (city_id) REFERENCES cities(id) ON DELETE SET NULL
    TABLE "staff_cities" CONSTRAINT "fk_staff_cities__city_id__cities" FOREIGN KEY (city_id) REFERENCES cities(id) ON DELETE CASCADE
    TABLE "streets" CONSTRAINT "fk_streets__city_id__cities" FOREIGN KEY (city_id) REFERENCES cities(id) ON DELETE CASCADE
Access method: heap


```

### Данные (до 1000 записей)

```
   id    |       name       | is_active |          created_at           |          updated_at           |   timezone    | centroid_lat | centroid_lon 
---------+------------------+-----------+-------------------------------+-------------------------------+---------------+--------------+--------------
  999999 | ZZZ Seed City    | t         | 2025-10-15 13:18:42.463215+00 | 2025-10-15 13:18:42.463215+00 | Europe/Moscow |              |             
       1 | City #1          | t         | 2025-10-15 13:18:42.486757+00 | 2025-10-15 13:18:42.486757+00 | Europe/Moscow |              |             
 1000000 | Москва Load Test | t         | 2025-10-15 13:18:42.503813+00 | 2025-10-15 13:18:42.503813+00 | Europe/Moscow |              |             
(3 rows)


```


---


## 5. Таблица: `commission_deadline_notifications`

**Количество записей:** 0

### Структура таблицы

```sql
                                                                   Table "public.commission_deadline_notifications"
    Column     |           Type           | Collation | Nullable |                            Default                            | Storage | Compression | Stats target | Description 
---------------+--------------------------+-----------+----------+---------------------------------------------------------------+---------+-------------+--------------+-------------
 id            | integer                  |           | not null | nextval('commission_deadline_notifications_id_seq'::regclass) | plain   |             |              | 
 commission_id | integer                  |           | not null |                                                               | plain   |             |              | 
 hours_before  | smallint                 |           | not null |                                                               | plain   |             |              | 
 sent_at       | timestamp with time zone |           | not null | now()                                                         | plain   |             |              | 
Indexes:
    "commission_deadline_notifications_pkey" PRIMARY KEY, btree (id)
    "ix_commission_deadline_notifications__commission" btree (commission_id)
    "uq_commission_deadline_notifications__commission_hours" UNIQUE CONSTRAINT, btree (commission_id, hours_before)
Check constraints:
    "commission_deadline_notifications_hours_before_check" CHECK (hours_before = ANY (ARRAY[1, 6, 24]))
Foreign-key constraints:
    "commission_deadline_notifications_commission_id_fkey" FOREIGN KEY (commission_id) REFERENCES commissions(id) ON DELETE CASCADE
Access method: heap


```

### Данные (до 1000 записей)

```
 id | commission_id | hours_before | sent_at 
----+---------------+--------------+---------
(0 rows)


```


---


## 6. Таблица: `commissions`

**Количество записей:** 0

### Структура таблицы

```sql
                                                                     Table "public.commissions"
      Column       |           Type           | Collation | Nullable |                 Default                 | Storage  | Compression | Stats target | Description 
-------------------+--------------------------+-----------+----------+-----------------------------------------+----------+-------------+--------------+-------------
 id                | integer                  |           | not null | nextval('commissions_id_seq'::regclass) | plain    |             |              | 
 order_id          | integer                  |           | not null |                                         | plain    |             |              | 
 master_id         | integer                  |           | not null |                                         | plain    |             |              | 
 amount            | numeric(10,2)            |           | not null |                                         | main     |             |              | 
 percent           | numeric(5,2)             |           |          |                                         | main     |             |              | 
 status            | commission_status        |           | not null |                                         | plain    |             |              | 
 deadline_at       | timestamp with time zone |           | not null |                                         | plain    |             |              | 
 paid_at           | timestamp with time zone |           |          |                                         | plain    |             |              | 
 blocked_applied   | boolean                  |           | not null | false                                   | plain    |             |              | 
 blocked_at        | timestamp with time zone |           |          |                                         | plain    |             |              | 
 payment_reference | character varying(120)   |           |          |                                         | extended |             |              | 
 created_at        | timestamp with time zone |           |          | now()                                   | plain    |             |              | 
 updated_at        | timestamp with time zone |           |          | now()                                   | plain    |             |              | 
 rate              | numeric(5,2)             |           |          |                                         | main     |             |              | 
 paid_reported_at  | timestamp with time zone |           |          |                                         | plain    |             |              | 
 paid_approved_at  | timestamp with time zone |           |          |                                         | plain    |             |              | 
 paid_amount       | numeric(10,2)            |           |          |                                         | main     |             |              | 
 is_paid           | boolean                  |           | not null | false                                   | plain    |             |              | 
 has_checks        | boolean                  |           | not null | false                                   | plain    |             |              | 
 pay_to_snapshot   | jsonb                    |           |          |                                         | extended |             |              | 
Indexes:
    "pk_commissions" PRIMARY KEY, btree (id)
    "ix_commissions__ispaid_deadline" btree (is_paid, deadline_at)
    "ix_commissions__master_status" btree (master_id, status)
    "ix_commissions__status_deadline" btree (status, deadline_at)
    "uq_commissions__order_id" UNIQUE CONSTRAINT, btree (order_id)
Foreign-key constraints:
    "fk_commissions__master_id__masters" FOREIGN KEY (master_id) REFERENCES masters(id) ON DELETE CASCADE
    "fk_commissions__order_id__orders" FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
Referenced by:
    TABLE "commission_deadline_notifications" CONSTRAINT "commission_deadline_notifications_commission_id_fkey" FOREIGN KEY (commission_id) REFERENCES commissions(id) ON DELETE CASCADE
    TABLE "referral_rewards" CONSTRAINT "fk_referral_rewards__commission_id__commissions" FOREIGN KEY (commission_id) REFERENCES commissions(id) ON DELETE CASCADE
Access method: heap


```

### Данные (до 1000 записей)

```
 id | order_id | master_id | amount | percent | status | deadline_at | paid_at | blocked_applied | blocked_at | payment_reference | created_at | updated_at | rate | paid_reported_at | paid_approved_at | paid_amount | is_paid | has_checks | pay_to_snapshot 
----+----------+-----------+--------+---------+--------+-------------+---------+-----------------+------------+-------------------+------------+------------+------+------------------+------------------+-------------+---------+------------+-----------------
(0 rows)


```


---


## 7. Таблица: `distribution_metrics`

**Количество записей:** 0

### Структура таблицы

```sql
                                                                        Table "public.distribution_metrics"
         Column          |           Type           | Collation | Nullable |                     Default                      | Storage  | Compression | Stats target | Description 
-------------------------+--------------------------+-----------+----------+--------------------------------------------------+----------+-------------+--------------+-------------
 id                      | integer                  |           | not null | nextval('distribution_metrics_id_seq'::regclass) | plain    |             |              | 
 order_id                | integer                  |           | not null |                                                  | plain    |             |              | 
 master_id               | integer                  |           |          |                                                  | plain    |             |              | 
 assigned_at             | timestamp with time zone |           | not null | now()                                            | plain    |             |              | 
 round_number            | smallint                 |           | not null |                                                  | plain    |             |              | 
 candidates_count        | smallint                 |           | not null |                                                  | plain    |             |              | 
 time_to_assign_seconds  | integer                  |           |          |                                                  | plain    |             |              | 
 preferred_master_used   | boolean                  |           | not null | false                                            | plain    |             |              | 
 was_escalated_to_logist | boolean                  |           | not null | false                                            | plain    |             |              | 
 was_escalated_to_admin  | boolean                  |           | not null | false                                            | plain    |             |              | 
 city_id                 | integer                  |           | not null |                                                  | plain    |             |              | 
 district_id             | integer                  |           |          |                                                  | plain    |             |              | 
 category                | character varying(32)    |           |          |                                                  | extended |             |              | 
 order_type              | character varying(32)    |           |          |                                                  | extended |             |              | 
 metadata_json           | jsonb                    |           | not null | '{}'::jsonb                                      | extended |             |              | 
 created_at              | timestamp with time zone |           | not null | now()                                            | plain    |             |              | 
Indexes:
    "distribution_metrics_pkey" PRIMARY KEY, btree (id)
    "idx_distribution_metrics_city_id" btree (city_id)
    "idx_distribution_metrics_district_id" btree (district_id)
    "idx_distribution_metrics_master_id" btree (master_id)
    "idx_distribution_metrics_order_id" btree (order_id)
    "ix_distribution_metrics__assigned_at_desc" btree (assigned_at DESC)
    "ix_distribution_metrics__city_assigned" btree (city_id, assigned_at)
    "ix_distribution_metrics__performance" btree (round_number, time_to_assign_seconds)
Foreign-key constraints:
    "distribution_metrics_city_id_fkey" FOREIGN KEY (city_id) REFERENCES cities(id) ON DELETE CASCADE
    "distribution_metrics_district_id_fkey" FOREIGN KEY (district_id) REFERENCES districts(id) ON DELETE SET NULL
    "distribution_metrics_master_id_fkey" FOREIGN KEY (master_id) REFERENCES masters(id) ON DELETE SET NULL
    "distribution_metrics_order_id_fkey" FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
Access method: heap


```

### Данные (до 1000 записей)

```
 id | order_id | master_id | assigned_at | round_number | candidates_count | time_to_assign_seconds | preferred_master_used | was_escalated_to_logist | was_escalated_to_admin | city_id | district_id | category | order_type | metadata_json | created_at 
----+----------+-----------+-------------+--------------+------------------+------------------------+-----------------------+-------------------------+------------------------+---------+-------------+----------+------------+---------------+------------
(0 rows)


```


---


## 8. Таблица: `districts`

**Количество записей:** 2

### Структура таблицы

```sql
                                                                   Table "public.districts"
    Column    |           Type           | Collation | Nullable |                Default                | Storage  | Compression | Stats target | Description 
--------------+--------------------------+-----------+----------+---------------------------------------+----------+-------------+--------------+-------------
 id           | integer                  |           | not null | nextval('districts_id_seq'::regclass) | plain    |             |              | 
 city_id      | integer                  |           | not null |                                       | plain    |             |              | 
 name         | character varying(120)   |           | not null |                                       | extended |             |              | 
 created_at   | timestamp with time zone |           |          | now()                                 | plain    |             |              | 
 centroid_lat | double precision         |           |          |                                       | plain    |             |              | 
 centroid_lon | double precision         |           |          |                                       | plain    |             |              | 
Indexes:
    "pk_districts" PRIMARY KEY, btree (id)
    "ix_districts__city_id" btree (city_id)
    "uq_districts__city_name" UNIQUE CONSTRAINT, btree (city_id, name)
Foreign-key constraints:
    "fk_districts__city_id__cities" FOREIGN KEY (city_id) REFERENCES cities(id) ON DELETE CASCADE
Referenced by:
    TABLE "distribution_metrics" CONSTRAINT "distribution_metrics_district_id_fkey" FOREIGN KEY (district_id) REFERENCES districts(id) ON DELETE SET NULL
    TABLE "master_districts" CONSTRAINT "fk_master_districts__district_id__districts" FOREIGN KEY (district_id) REFERENCES districts(id) ON DELETE CASCADE
    TABLE "orders" CONSTRAINT "fk_orders__district_id__districts" FOREIGN KEY (district_id) REFERENCES districts(id) ON DELETE SET NULL
    TABLE "streets" CONSTRAINT "fk_streets__district_id__districts" FOREIGN KEY (district_id) REFERENCES districts(id) ON DELETE SET NULL
Access method: heap


```

### Данные (до 1000 записей)

```
   id   | city_id |       name        |          created_at           | centroid_lat | centroid_lon 
--------+---------+-------------------+-------------------------------+--------------+--------------
 999999 |  999999 | ZZZ Seed District | 2025-10-15 13:18:42.463215+00 |              |             
   3460 | 1000000 | Центральный       | 2025-10-15 13:18:42.527498+00 |              |             
(2 rows)


```


---


## 9. Таблица: `geocache`

**Количество записей:** 0

### Структура таблицы

```sql
                                                        Table "public.geocache"
   Column   |           Type           | Collation | Nullable |      Default      | Storage  | Compression | Stats target | Description 
------------+--------------------------+-----------+----------+-------------------+----------+-------------+--------------+-------------
 query      | character varying(255)   |           | not null |                   | extended |             |              | 
 lat        | double precision         |           |          |                   | plain    |             |              | 
 lon        | double precision         |           |          |                   | plain    |             |              | 
 provider   | character varying(32)    |           |          |                   | extended |             |              | 
 confidence | integer                  |           |          |                   | plain    |             |              | 
 created_at | timestamp with time zone |           | not null | CURRENT_TIMESTAMP | plain    |             |              | 
Indexes:
    "pk_geocache" PRIMARY KEY, btree (query)
    "ix_geocache_created_at" btree (created_at)
Access method: heap


```

### Данные (до 1000 записей)

```
 query | lat | lon | provider | confidence | created_at 
-------+-----+-----+----------+------------+------------
(0 rows)


```


---


## 10. Таблица: `master_districts`

**Количество записей:** 0

### Структура таблицы

```sql
                                               Table "public.master_districts"
   Column    |           Type           | Collation | Nullable | Default | Storage | Compression | Stats target | Description 
-------------+--------------------------+-----------+----------+---------+---------+-------------+--------------+-------------
 master_id   | integer                  |           | not null |         | plain   |             |              | 
 district_id | integer                  |           | not null |         | plain   |             |              | 
 created_at  | timestamp with time zone |           |          | now()   | plain   |             |              | 
Indexes:
    "pk_master_districts" PRIMARY KEY, btree (master_id, district_id)
    "ix_master_districts__district" btree (district_id)
Foreign-key constraints:
    "fk_master_districts__district_id__districts" FOREIGN KEY (district_id) REFERENCES districts(id) ON DELETE CASCADE
    "fk_master_districts__master_id__masters" FOREIGN KEY (master_id) REFERENCES masters(id) ON DELETE CASCADE
Access method: heap


```

### Данные (до 1000 записей)

```
 master_id | district_id | created_at 
-----------+-------------+------------
(0 rows)


```


---


## 11. Таблица: `master_invite_codes`

**Количество записей:** 0

### Структура таблицы

```sql
                                                                      Table "public.master_invite_codes"
       Column       |           Type           | Collation | Nullable |                     Default                     | Storage  | Compression | Stats target | Description 
--------------------+--------------------------+-----------+----------+-------------------------------------------------+----------+-------------+--------------+-------------
 id                 | integer                  |           | not null | nextval('master_invite_codes_id_seq'::regclass) | plain    |             |              | 
 code               | character varying(32)    |           | not null |                                                 | extended |             |              | 
 city_id            | integer                  |           |          |                                                 | plain    |             |              | 
 issued_by_staff_id | integer                  |           |          |                                                 | plain    |             |              | 
 used_by_master_id  | integer                  |           |          |                                                 | plain    |             |              | 
 expires_at         | timestamp with time zone |           |          |                                                 | plain    |             |              | 
 is_revoked         | boolean                  |           | not null | false                                           | plain    |             |              | 
 used_at            | timestamp with time zone |           |          |                                                 | plain    |             |              | 
 comment            | character varying(255)   |           |          |                                                 | extended |             |              | 
 created_at         | timestamp with time zone |           |          | now()                                           | plain    |             |              | 
 updated_at         | timestamp with time zone |           |          | now()                                           | plain    |             |              | 
Indexes:
    "pk_master_invite_codes" PRIMARY KEY, btree (id)
    "ix_master_invite_codes__available" UNIQUE, btree (code) WHERE used_by_master_id IS NULL AND is_revoked = false AND expires_at IS NULL
    "ix_master_invite_codes__code" UNIQUE, btree (code)
Foreign-key constraints:
    "fk_master_invite_codes__city_id__cities" FOREIGN KEY (city_id) REFERENCES cities(id) ON DELETE SET NULL
    "fk_master_invite_codes__issued_by_staff_id__staff_users" FOREIGN KEY (issued_by_staff_id) REFERENCES staff_users(id) ON DELETE SET NULL
    "fk_master_invite_codes__used_by_master_id__masters" FOREIGN KEY (used_by_master_id) REFERENCES masters(id) ON DELETE SET NULL
Access method: heap


```

### Данные (до 1000 записей)

```
 id | code | city_id | issued_by_staff_id | used_by_master_id | expires_at | is_revoked | used_at | comment | created_at | updated_at 
----+------+---------+--------------------+-------------------+------------+------------+---------+---------+------------+------------
(0 rows)


```


---


## 12. Таблица: `master_skills`

**Количество записей:** 0

### Структура таблицы

```sql
                                                Table "public.master_skills"
   Column   |           Type           | Collation | Nullable | Default | Storage | Compression | Stats target | Description 
------------+--------------------------+-----------+----------+---------+---------+-------------+--------------+-------------
 master_id  | integer                  |           | not null |         | plain   |             |              | 
 skill_id   | integer                  |           | not null |         | plain   |             |              | 
 created_at | timestamp with time zone |           |          | now()   | plain   |             |              | 
Indexes:
    "pk_master_skills" PRIMARY KEY, btree (master_id, skill_id)
    "ix_master_skills__skill" btree (skill_id)
Foreign-key constraints:
    "fk_master_skills__master_id__masters" FOREIGN KEY (master_id) REFERENCES masters(id) ON DELETE CASCADE
    "fk_master_skills__skill_id__skills" FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE
Access method: heap


```

### Данные (до 1000 записей)

```
 master_id | skill_id | created_at 
-----------+----------+------------
(0 rows)


```


---


## 13. Таблица: `masters`

**Количество записей:** 20

### Структура таблицы

```sql
                                                                          Table "public.masters"
           Column           |           Type           | Collation | Nullable |               Default               | Storage  | Compression | Stats target | Description 
----------------------------+--------------------------+-----------+----------+-------------------------------------+----------+-------------+--------------+-------------
 id                         | integer                  |           | not null | nextval('masters_id_seq'::regclass) | plain    |             |              | 
 tg_user_id                 | bigint                   |           |          |                                     | plain    |             |              | 
 full_name                  | character varying(160)   |           | not null |                                     | extended |             |              | 
 phone                      | character varying(32)    |           |          |                                     | extended |             |              | 
 city_id                    | integer                  |           |          |                                     | plain    |             |              | 
 rating                     | double precision         |           | not null | '5'::double precision               | plain    |             |              | 
 is_active                  | boolean                  |           | not null | true                                | plain    |             |              | 
 is_blocked                 | boolean                  |           | not null | false                               | plain    |             |              | 
 blocked_at                 | timestamp with time zone |           |          |                                     | plain    |             |              | 
 blocked_reason             | text                     |           |          |                                     | extended |             |              | 
 referral_code              | character varying(32)    |           |          |                                     | extended |             |              | 
 referred_by_master_id      | integer                  |           |          |                                     | plain    |             |              | 
 last_heartbeat_at          | timestamp with time zone |           |          |                                     | plain    |             |              | 
 created_at                 | timestamp with time zone |           |          | now()                               | plain    |             |              | 
 updated_at                 | timestamp with time zone |           |          | now()                               | plain    |             |              | 
 version                    | integer                  |           | not null | 1                                   | plain    |             |              | 
 moderation_status          | moderation_status        |           | not null | 'PENDING'::moderation_status        | plain    |             |              | 
 moderation_note            | text                     |           |          |                                     | extended |             |              | 
 shift_status               | shift_status             |           | not null | 'SHIFT_OFF'::shift_status           | plain    |             |              | 
 break_until                | timestamp with time zone |           |          |                                     | plain    |             |              | 
 pdn_accepted_at            | timestamp with time zone |           |          |                                     | plain    |             |              | 
 payout_method              | payout_method            |           |          |                                     | plain    |             |              | 
 payout_data                | jsonb                    |           |          |                                     | extended |             |              | 
 has_vehicle                | boolean                  |           | not null | false                               | plain    |             |              | 
 vehicle_plate              | character varying(16)    |           |          |                                     | extended |             |              | 
 home_latitude              | numeric(9,6)             |           |          |                                     | main     |             |              | 
 home_longitude             | numeric(9,6)             |           |          |                                     | main     |             |              | 
 max_active_orders_override | smallint                 |           |          |                                     | plain    |             |              | 
 is_on_shift                | boolean                  |           | not null | false                               | plain    |             |              | 
 verified                   | boolean                  |           | not null | false                               | plain    |             |              | 
 is_deleted                 | boolean                  |           | not null |                                     | plain    |             |              | 
 moderation_reason          | text                     |           |          |                                     | extended |             |              | 
 verified_at                | timestamp with time zone |           |          |                                     | plain    |             |              | 
 verified_by                | integer                  |           |          |                                     | plain    |             |              | 
 telegram_username          | character varying(64)    |           |          |                                     | extended |             |              | 
 first_name                 | character varying(80)    |           |          |                                     | extended |             |              | 
 last_name                  | character varying(120)   |           |          |                                     | extended |             |              | 
Indexes:
    "pk_masters" PRIMARY KEY, btree (id)
    "ix_masters__city_id" btree (city_id)
    "ix_masters__heartbeat" btree (last_heartbeat_at)
    "ix_masters__mod_shift" btree (moderation_status, shift_status)
    "ix_masters__onshift_verified" btree (is_on_shift, verified)
    "ix_masters__phone" btree (phone)
    "ix_masters__referred_by" btree (referred_by_master_id)
    "ix_masters__tg_user_id" btree (tg_user_id)
    "ix_masters__verified_active_deleted_city" btree (verified, is_active, is_deleted, city_id)
    "uq_masters__referral_code" UNIQUE CONSTRAINT, btree (referral_code)
    "uq_masters__tg_user_id" UNIQUE CONSTRAINT, btree (tg_user_id)
Check constraints:
    "ck_masters__ck_masters__limit_nonneg" CHECK (max_active_orders_override IS NULL OR max_active_orders_override >= 0)
Foreign-key constraints:
    "fk_masters__city_id__cities" FOREIGN KEY (city_id) REFERENCES cities(id) ON DELETE SET NULL
    "fk_masters__referred_by_master_id__masters" FOREIGN KEY (referred_by_master_id) REFERENCES masters(id) ON DELETE SET NULL
    "fk_masters__verified_by__staff_users" FOREIGN KEY (verified_by) REFERENCES staff_users(id) ON DELETE SET NULL
Referenced by:
    TABLE "distribution_metrics" CONSTRAINT "distribution_metrics_master_id_fkey" FOREIGN KEY (master_id) REFERENCES masters(id) ON DELETE SET NULL
    TABLE "admin_audit_log" CONSTRAINT "fk_admin_audit_log__master_id__masters" FOREIGN KEY (master_id) REFERENCES masters(id) ON DELETE SET NULL
    TABLE "attachments" CONSTRAINT "fk_attachments__uploaded_by_master_id__masters" FOREIGN KEY (uploaded_by_master_id) REFERENCES masters(id) ON DELETE SET NULL
    TABLE "commissions" CONSTRAINT "fk_commissions__master_id__masters" FOREIGN KEY (master_id) REFERENCES masters(id) ON DELETE CASCADE
    TABLE "master_districts" CONSTRAINT "fk_master_districts__master_id__masters" FOREIGN KEY (master_id) REFERENCES masters(id) ON DELETE CASCADE
    TABLE "master_invite_codes" CONSTRAINT "fk_master_invite_codes__used_by_master_id__masters" FOREIGN KEY (used_by_master_id) REFERENCES masters(id) ON DELETE SET NULL
    TABLE "master_skills" CONSTRAINT "fk_master_skills__master_id__masters" FOREIGN KEY (master_id) REFERENCES masters(id) ON DELETE CASCADE
    TABLE "masters" CONSTRAINT "fk_masters__referred_by_master_id__masters" FOREIGN KEY (referred_by_master_id) REFERENCES masters(id) ON DELETE SET NULL
    TABLE "notifications_outbox" CONSTRAINT "fk_notifications_outbox__master_id__masters" FOREIGN KEY (master_id) REFERENCES masters(id) ON DELETE CASCADE
    TABLE "offers" CONSTRAINT "fk_offers__master_id__masters" FOREIGN KEY (master_id) REFERENCES masters(id) ON DELETE CASCADE
    TABLE "order_status_history" CONSTRAINT "fk_order_status_history__changed_by_master_id__masters" FOREIGN KEY (changed_by_master_id) REFERENCES masters(id) ON DELETE SET NULL
    TABLE "orders" CONSTRAINT "fk_orders__assigned_master_id__masters" FOREIGN KEY (assigned_master_id) REFERENCES masters(id) ON DELETE SET NULL
    TABLE "orders" CONSTRAINT "fk_orders__preferred_master_id__masters" FOREIGN KEY (preferred_master_id) REFERENCES masters(id) ON DELETE SET NULL
    TABLE "referral_rewards" CONSTRAINT "fk_referral_rewards__referred_master_id__masters" FOREIGN KEY (referred_master_id) REFERENCES masters(id) ON DELETE CASCADE
    TABLE "referral_rewards" CONSTRAINT "fk_referral_rewards__referrer_id__masters" FOREIGN KEY (referrer_id) REFERENCES masters(id) ON DELETE CASCADE
    TABLE "referrals" CONSTRAINT "fk_referrals__master_id__masters" FOREIGN KEY (master_id) REFERENCES masters(id) ON DELETE CASCADE
    TABLE "referrals" CONSTRAINT "fk_referrals__referrer_id__masters" FOREIGN KEY (referrer_id) REFERENCES masters(id) ON DELETE CASCADE
Access method: heap


```

### Данные (до 1000 записей)

```
  id  | tg_user_id |      full_name      |    phone     | city_id | rating | is_active | is_blocked | blocked_at | blocked_reason | referral_code | referred_by_master_id | last_heartbeat_at |          created_at           |          updated_at           | version | moderation_status | moderation_note | shift_status | break_until | pdn_accepted_at | payout_method | payout_data | has_vehicle | vehicle_plate | home_latitude | home_longitude | max_active_orders_override | is_on_shift | verified | is_deleted | moderation_reason | verified_at | verified_by | telegram_username | first_name | last_name 
------+------------+---------------------+--------------+---------+--------+-----------+------------+------------+----------------+---------------+-----------------------+-------------------+-------------------------------+-------------------------------+---------+-------------------+-----------------+--------------+-------------+-----------------+---------------+-------------+-------------+---------------+---------------+----------------+----------------------------+-------------+----------+------------+-------------------+-------------+-------------+-------------------+------------+-----------
 3378 |      10000 | Load Test Master 1  | +79000010000 | 1000000 |    4.5 | t         | f          |            |                |               |                       |                   | 2025-10-15 13:18:42.563481+00 | 2025-10-15 13:18:42.563481+00 |       1 | PENDING           |                 | SHIFT_OFF    |             |                 |               |             | t           |               |               |                |                            | t           | t        | f          |                   |             |             |                   |            | 
 3379 |      10001 | Load Test Master 2  | +79000010001 | 1000000 |    4.5 | t         | f          |            |                |               |                       |                   | 2025-10-15 13:18:42.563481+00 | 2025-10-15 13:18:42.563481+00 |       1 | PENDING           |                 | SHIFT_OFF    |             |                 |               |             | t           |               |               |                |                            | t           | t        | f          |                   |             |             |                   |            | 
 3380 |      10002 | Load Test Master 3  | +79000010002 | 1000000 |    4.5 | t         | f          |            |                |               |                       |                   | 2025-10-15 13:18:42.563481+00 | 2025-10-15 13:18:42.563481+00 |       1 | PENDING           |                 | SHIFT_OFF    |             |                 |               |             | t           |               |               |                |                            | t           | t        | f          |                   |             |             |                   |            | 
 3381 |      10003 | Load Test Master 4  | +79000010003 | 1000000 |    4.5 | t         | f          |            |                |               |                       |                   | 2025-10-15 13:18:42.563481+00 | 2025-10-15 13:18:42.563481+00 |       1 | PENDING           |                 | SHIFT_OFF    |             |                 |               |             | t           |               |               |                |                            | t           | t        | f          |                   |             |             |                   |            | 
 3382 |      10004 | Load Test Master 5  | +79000010004 | 1000000 |    4.5 | t         | f          |            |                |               |                       |                   | 2025-10-15 13:18:42.563481+00 | 2025-10-15 13:18:42.563481+00 |       1 | PENDING           |                 | SHIFT_OFF    |             |                 |               |             | t           |               |               |                |                            | t           | t        | f          |                   |             |             |                   |            | 
 3383 |      10005 | Load Test Master 6  | +79000010005 | 1000000 |    4.5 | t         | f          |            |                |               |                       |                   | 2025-10-15 13:18:42.563481+00 | 2025-10-15 13:18:42.563481+00 |       1 | PENDING           |                 | SHIFT_OFF    |             |                 |               |             | t           |               |               |                |                            | t           | t        | f          |                   |             |             |                   |            | 
 3384 |      10006 | Load Test Master 7  | +79000010006 | 1000000 |    4.5 | t         | f          |            |                |               |                       |                   | 2025-10-15 13:18:42.563481+00 | 2025-10-15 13:18:42.563481+00 |       1 | PENDING           |                 | SHIFT_OFF    |             |                 |               |             | t           |               |               |                |                            | t           | t        | f          |                   |             |             |                   |            | 
 3385 |      10007 | Load Test Master 8  | +79000010007 | 1000000 |    4.5 | t         | f          |            |                |               |                       |                   | 2025-10-15 13:18:42.563481+00 | 2025-10-15 13:18:42.563481+00 |       1 | PENDING           |                 | SHIFT_OFF    |             |                 |               |             | t           |               |               |                |                            | t           | t        | f          |                   |             |             |                   |            | 
 3386 |      10008 | Load Test Master 9  | +79000010008 | 1000000 |    4.5 | t         | f          |            |                |               |                       |                   | 2025-10-15 13:18:42.563481+00 | 2025-10-15 13:18:42.563481+00 |       1 | PENDING           |                 | SHIFT_OFF    |             |                 |               |             | t           |               |               |                |                            | t           | t        | f          |                   |             |             |                   |            | 
 3387 |      10009 | Load Test Master 10 | +79000010009 | 1000000 |    4.5 | t         | f          |            |                |               |                       |                   | 2025-10-15 13:18:42.563481+00 | 2025-10-15 13:18:42.563481+00 |       1 | PENDING           |                 | SHIFT_OFF    |             |                 |               |             | t           |               |               |                |                            | t           | t        | f          |                   |             |             |                   |            | 
 3388 |      10010 | Load Test Master 11 | +79000010010 | 1000000 |    4.5 | t         | f          |            |                |               |                       |                   | 2025-10-15 13:18:42.563481+00 | 2025-10-15 13:18:42.563481+00 |       1 | PENDING           |                 | SHIFT_OFF    |             |                 |               |             | t           |               |               |                |                            | t           | t        | f          |                   |             |             |                   |            | 
 3389 |      10011 | Load Test Master 12 | +79000010011 | 1000000 |    4.5 | t         | f          |            |                |               |                       |                   | 2025-10-15 13:18:42.563481+00 | 2025-10-15 13:18:42.563481+00 |       1 | PENDING           |                 | SHIFT_OFF    |             |                 |               |             | t           |               |               |                |                            | t           | t        | f          |                   |             |             |                   |            | 
 3390 |      10012 | Load Test Master 13 | +79000010012 | 1000000 |    4.5 | t         | f          |            |                |               |                       |                   | 2025-10-15 13:18:42.563481+00 | 2025-10-15 13:18:42.563481+00 |       1 | PENDING           |                 | SHIFT_OFF    |             |                 |               |             | t           |               |               |                |                            | t           | t        | f          |                   |             |             |                   |            | 
 3391 |      10013 | Load Test Master 14 | +79000010013 | 1000000 |    4.5 | t         | f          |            |                |               |                       |                   | 2025-10-15 13:18:42.563481+00 | 2025-10-15 13:18:42.563481+00 |       1 | PENDING           |                 | SHIFT_OFF    |             |                 |               |             | t           |               |               |                |                            | t           | t        | f          |                   |             |             |                   |            | 
 3392 |      10014 | Load Test Master 15 | +79000010014 | 1000000 |    4.5 | t         | f          |            |                |               |                       |                   | 2025-10-15 13:18:42.563481+00 | 2025-10-15 13:18:42.563481+00 |       1 | PENDING           |                 | SHIFT_OFF    |             |                 |               |             | t           |               |               |                |                            | t           | t        | f          |                   |             |             |                   |            | 
 3393 |      10015 | Load Test Master 16 | +79000010015 | 1000000 |    4.5 | t         | f          |            |                |               |                       |                   | 2025-10-15 13:18:42.563481+00 | 2025-10-15 13:18:42.563481+00 |       1 | PENDING           |                 | SHIFT_OFF    |             |                 |               |             | t           |               |               |                |                            | t           | t        | f          |                   |             |             |                   |            | 
 3394 |      10016 | Load Test Master 17 | +79000010016 | 1000000 |    4.5 | t         | f          |            |                |               |                       |                   | 2025-10-15 13:18:42.563481+00 | 2025-10-15 13:18:42.563481+00 |       1 | PENDING           |                 | SHIFT_OFF    |             |                 |               |             | t           |               |               |                |                            | t           | t        | f          |                   |             |             |                   |            | 
 3395 |      10017 | Load Test Master 18 | +79000010017 | 1000000 |    4.5 | t         | f          |            |                |               |                       |                   | 2025-10-15 13:18:42.563481+00 | 2025-10-15 13:18:42.563481+00 |       1 | PENDING           |                 | SHIFT_OFF    |             |                 |               |             | t           |               |               |                |                            | t           | t        | f          |                   |             |             |                   |            | 
 3396 |      10018 | Load Test Master 19 | +79000010018 | 1000000 |    4.5 | t         | f          |            |                |               |                       |                   | 2025-10-15 13:18:42.563481+00 | 2025-10-15 13:18:42.563481+00 |       1 | PENDING           |                 | SHIFT_OFF    |             |                 |               |             | t           |               |               |                |                            | t           | t        | f          |                   |             |             |                   |            | 
 3397 |      10019 | Load Test Master 20 | +79000010019 | 1000000 |    4.5 | t         | f          |            |                |               |                       |                   | 2025-10-15 13:18:42.563481+00 | 2025-10-15 13:18:42.563481+00 |       1 | PENDING           |                 | SHIFT_OFF    |             |                 |               |             | t           |               |               |                |                            | t           | t        | f          |                   |             |             |                   |            | 
(20 rows)


```


---


## 14. Таблица: `notifications_outbox`

**Количество записей:** 0

### Структура таблицы

```sql
                                                                   Table "public.notifications_outbox"
    Column     |           Type           | Collation | Nullable |                     Default                      | Storage  | Compression | Stats target | Description 
---------------+--------------------------+-----------+----------+--------------------------------------------------+----------+-------------+--------------+-------------
 id            | integer                  |           | not null | nextval('notifications_outbox_id_seq'::regclass) | plain    |             |              | 
 master_id     | integer                  |           | not null |                                                  | plain    |             |              | 
 event         | character varying(64)    |           | not null |                                                  | extended |             |              | 
 payload       | jsonb                    |           | not null | '{}'::jsonb                                      | extended |             |              | 
 created_at    | timestamp with time zone |           | not null | now()                                            | plain    |             |              | 
 processed_at  | timestamp with time zone |           |          |                                                  | plain    |             |              | 
 attempt_count | integer                  |           | not null |                                                  | plain    |             |              | 
 last_error    | text                     |           |          |                                                  | extended |             |              | 
Indexes:
    "pk_notifications_outbox" PRIMARY KEY, btree (id)
    "ix_notifications_outbox_created" btree (created_at)
    "ix_notifications_outbox_master" btree (master_id)
Foreign-key constraints:
    "fk_notifications_outbox__master_id__masters" FOREIGN KEY (master_id) REFERENCES masters(id) ON DELETE CASCADE
Access method: heap


```

### Данные (до 1000 записей)

```
 id | master_id | event | payload | created_at | processed_at | attempt_count | last_error 
----+-----------+-------+---------+------------+--------------+---------------+------------
(0 rows)


```


---


## 15. Таблица: `offers`

**Количество записей:** 20

### Структура таблицы

```sql
                                                                  Table "public.offers"
    Column    |           Type           | Collation | Nullable |              Default               | Storage | Compression | Stats target | Description 
--------------+--------------------------+-----------+----------+------------------------------------+---------+-------------+--------------+-------------
 id           | integer                  |           | not null | nextval('offers_id_seq'::regclass) | plain   |             |              | 
 order_id     | integer                  |           | not null |                                    | plain   |             |              | 
 master_id    | integer                  |           | not null |                                    | plain   |             |              | 
 round_number | smallint                 |           | not null | '1'::smallint                      | plain   |             |              | 
 state        | offer_state              |           | not null |                                    | plain   |             |              | 
 sent_at      | timestamp with time zone |           |          | now()                              | plain   |             |              | 
 responded_at | timestamp with time zone |           |          |                                    | plain   |             |              | 
 expires_at   | timestamp with time zone |           |          |                                    | plain   |             |              | 
 created_at   | timestamp with time zone |           |          | now()                              | plain   |             |              | 
Indexes:
    "pk_offers" PRIMARY KEY, btree (id)
    "ix_offers__expires_at" btree (expires_at)
    "ix_offers__master_state" btree (master_id, state)
    "ix_offers__order_state" btree (order_id, state)
    "uix_offers__order_accepted_once" UNIQUE, btree (order_id) WHERE state = 'ACCEPTED'::offer_state
    "uq_offers__order_master_active" UNIQUE, btree (order_id, master_id) WHERE state = ANY (ARRAY['SENT'::offer_state, 'VIEWED'::offer_state, 'ACCEPTED'::offer_state])
Foreign-key constraints:
    "fk_offers__master_id__masters" FOREIGN KEY (master_id) REFERENCES masters(id) ON DELETE CASCADE
    "fk_offers__order_id__orders" FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
Access method: heap


```

### Данные (до 1000 записей)

```
  id  | order_id | master_id | round_number |  state   |            sent_at            |         responded_at          |          expires_at           |          created_at           
------+----------+-----------+--------------+----------+-------------------------------+-------------------------------+-------------------------------+-------------------------------
 2898 |      305 |      3378 |            1 | ACCEPTED | 2025-10-15 13:18:42.707056+00 | 2025-10-15 13:18:42.762396+00 | 2025-10-15 13:20:42.707056+00 | 2025-10-15 13:18:42.680891+00
 2899 |      305 |      3379 |            1 | CANCELED | 2025-10-15 13:18:42.707056+00 | 2025-10-15 13:18:42.762396+00 | 2025-10-15 13:20:42.707056+00 | 2025-10-15 13:18:42.680891+00
 2900 |      305 |      3380 |            1 | CANCELED | 2025-10-15 13:18:42.708046+00 | 2025-10-15 13:18:42.762396+00 | 2025-10-15 13:20:42.708046+00 | 2025-10-15 13:18:42.680891+00
 2901 |      305 |      3381 |            1 | CANCELED | 2025-10-15 13:18:42.708046+00 | 2025-10-15 13:18:42.762396+00 | 2025-10-15 13:20:42.708046+00 | 2025-10-15 13:18:42.680891+00
 2902 |      305 |      3382 |            1 | CANCELED | 2025-10-15 13:18:42.708046+00 | 2025-10-15 13:18:42.762396+00 | 2025-10-15 13:20:42.708046+00 | 2025-10-15 13:18:42.680891+00
 2903 |      305 |      3383 |            1 | CANCELED | 2025-10-15 13:18:42.708046+00 | 2025-10-15 13:18:42.762396+00 | 2025-10-15 13:20:42.708046+00 | 2025-10-15 13:18:42.680891+00
 2904 |      305 |      3384 |            1 | CANCELED | 2025-10-15 13:18:42.708046+00 | 2025-10-15 13:18:42.762396+00 | 2025-10-15 13:20:42.708046+00 | 2025-10-15 13:18:42.680891+00
 2905 |      305 |      3385 |            1 | CANCELED | 2025-10-15 13:18:42.708046+00 | 2025-10-15 13:18:42.762396+00 | 2025-10-15 13:20:42.708046+00 | 2025-10-15 13:18:42.680891+00
 2906 |      305 |      3386 |            1 | CANCELED | 2025-10-15 13:18:42.708046+00 | 2025-10-15 13:18:42.762396+00 | 2025-10-15 13:20:42.708046+00 | 2025-10-15 13:18:42.680891+00
 2907 |      305 |      3387 |            1 | CANCELED | 2025-10-15 13:18:42.708046+00 | 2025-10-15 13:18:42.762396+00 | 2025-10-15 13:20:42.708046+00 | 2025-10-15 13:18:42.680891+00
 2908 |      305 |      3388 |            1 | CANCELED | 2025-10-15 13:18:42.708046+00 | 2025-10-15 13:18:42.762396+00 | 2025-10-15 13:20:42.708046+00 | 2025-10-15 13:18:42.680891+00
 2909 |      305 |      3389 |            1 | CANCELED | 2025-10-15 13:18:42.708046+00 | 2025-10-15 13:18:42.762396+00 | 2025-10-15 13:20:42.708046+00 | 2025-10-15 13:18:42.680891+00
 2910 |      305 |      3390 |            1 | CANCELED | 2025-10-15 13:18:42.708046+00 | 2025-10-15 13:18:42.762396+00 | 2025-10-15 13:20:42.708046+00 | 2025-10-15 13:18:42.680891+00
 2911 |      305 |      3391 |            1 | CANCELED | 2025-10-15 13:18:42.708046+00 | 2025-10-15 13:18:42.762396+00 | 2025-10-15 13:20:42.708046+00 | 2025-10-15 13:18:42.680891+00
 2912 |      305 |      3392 |            1 | CANCELED | 2025-10-15 13:18:42.708671+00 | 2025-10-15 13:18:42.762396+00 | 2025-10-15 13:20:42.708671+00 | 2025-10-15 13:18:42.680891+00
 2913 |      305 |      3393 |            1 | CANCELED | 2025-10-15 13:18:42.708671+00 | 2025-10-15 13:18:42.762396+00 | 2025-10-15 13:20:42.708671+00 | 2025-10-15 13:18:42.680891+00
 2914 |      305 |      3394 |            1 | CANCELED | 2025-10-15 13:18:42.708671+00 | 2025-10-15 13:18:42.762396+00 | 2025-10-15 13:20:42.708671+00 | 2025-10-15 13:18:42.680891+00
 2915 |      305 |      3395 |            1 | CANCELED | 2025-10-15 13:18:42.708671+00 | 2025-10-15 13:18:42.762396+00 | 2025-10-15 13:20:42.708671+00 | 2025-10-15 13:18:42.680891+00
 2916 |      305 |      3396 |            1 | CANCELED | 2025-10-15 13:18:42.708671+00 | 2025-10-15 13:18:42.762396+00 | 2025-10-15 13:20:42.708671+00 | 2025-10-15 13:18:42.680891+00
 2917 |      305 |      3397 |            1 | CANCELED | 2025-10-15 13:18:42.708671+00 | 2025-10-15 13:18:42.762396+00 | 2025-10-15 13:20:42.708671+00 | 2025-10-15 13:18:42.680891+00
(20 rows)


```


---


## 16. Таблица: `order_autoclose_queue`

**Количество записей:** 0

### Структура таблицы

```sql
                                             Table "public.order_autoclose_queue"
    Column    |           Type           | Collation | Nullable | Default | Storage | Compression | Stats target | Description 
--------------+--------------------------+-----------+----------+---------+---------+-------------+--------------+-------------
 order_id     | integer                  |           | not null |         | plain   |             |              | 
 closed_at    | timestamp with time zone |           | not null |         | plain   |             |              | 
 autoclose_at | timestamp with time zone |           | not null |         | plain   |             |              | 
 processed_at | timestamp with time zone |           |          |         | plain   |             |              | 
 created_at   | timestamp with time zone |           | not null | now()   | plain   |             |              | 
Indexes:
    "pk_order_autoclose_queue" PRIMARY KEY, btree (order_id)
    "ix_order_autoclose_queue__pending" btree (autoclose_at) WHERE processed_at IS NULL
Foreign-key constraints:
    "fk_order_autoclose_queue__order_id__orders" FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
Access method: heap


```

### Данные (до 1000 записей)

```
 order_id | closed_at | autoclose_at | processed_at | created_at 
----------+-----------+--------------+--------------+------------
(0 rows)


```


---


## 17. Таблица: `order_status_history`

**Количество записей:** 1

### Структура таблицы

```sql
                                                                       Table "public.order_status_history"
        Column        |           Type           | Collation | Nullable |                     Default                      | Storage  | Compression | Stats target | Description 
----------------------+--------------------------+-----------+----------+--------------------------------------------------+----------+-------------+--------------+-------------
 id                   | integer                  |           | not null | nextval('order_status_history_id_seq'::regclass) | plain    |             |              | 
 order_id             | integer                  |           | not null |                                                  | plain    |             |              | 
 from_status          | order_status             |           |          |                                                  | plain    |             |              | 
 to_status            | order_status             |           | not null |                                                  | plain    |             |              | 
 reason               | text                     |           |          |                                                  | extended |             |              | 
 changed_by_staff_id  | integer                  |           |          |                                                  | plain    |             |              | 
 changed_by_master_id | integer                  |           |          |                                                  | plain    |             |              | 
 created_at           | timestamp with time zone |           |          | now()                                            | plain    |             |              | 
 actor_type           | actor_type               |           | not null |                                                  | plain    |             |              | 
 context              | jsonb                    |           | not null | '{}'::jsonb                                      | extended |             |              | 
Indexes:
    "pk_order_status_history" PRIMARY KEY, btree (id)
    "ix_order_status_history__actor_type" btree (actor_type)
    "ix_order_status_history__order_created_at" btree (order_id, created_at)
Foreign-key constraints:
    "fk_order_status_history__changed_by_master_id__masters" FOREIGN KEY (changed_by_master_id) REFERENCES masters(id) ON DELETE SET NULL
    "fk_order_status_history__changed_by_staff_id__staff_users" FOREIGN KEY (changed_by_staff_id) REFERENCES staff_users(id) ON DELETE SET NULL
    "fk_order_status_history__order_id__orders" FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
Access method: heap


```

### Данные (до 1000 записей)

```
 id  | order_id | from_status | to_status |       reason       | changed_by_staff_id | changed_by_master_id |          created_at           | actor_type |                                           context                                            
-----+----------+-------------+-----------+--------------------+---------------------+----------------------+-------------------------------+------------+----------------------------------------------------------------------------------------------
 266 |      305 | SEARCHING   | ASSIGNED  | accepted_by_master |                     |                 3378 | 2025-10-15 13:18:42.762396+00 | MASTER     | {"action": "offer_accepted", "method": "atomic_accept", "offer_id": 2898, "master_id": 3378}
(1 row)


```


---


## 18. Таблица: `orders`

**Количество записей:** 1

### Структура таблицы

```sql
                                                                           Table "public.orders"
            Column             |           Type           | Collation | Nullable |              Default               | Storage  | Compression | Stats target | Description 
-------------------------------+--------------------------+-----------+----------+------------------------------------+----------+-------------+--------------+-------------
 id                            | integer                  |           | not null | nextval('orders_id_seq'::regclass) | plain    |             |              | 
 city_id                       | integer                  |           | not null |                                    | plain    |             |              | 
 district_id                   | integer                  |           |          |                                    | plain    |             |              | 
 street_id                     | integer                  |           |          |                                    | plain    |             |              | 
 house                         | character varying(32)    |           |          |                                    | extended |             |              | 
 apartment                     | character varying(32)    |           |          |                                    | extended |             |              | 
 address_comment               | text                     |           |          |                                    | extended |             |              | 
 client_name                   | character varying(160)   |           |          |                                    | extended |             |              | 
 client_phone                  | character varying(32)    |           |          |                                    | extended |             |              | 
 status                        | order_status             |           | not null | 'CREATED'::order_status            | plain    |             |              | 
 preferred_master_id           | integer                  |           |          |                                    | plain    |             |              | 
 assigned_master_id            | integer                  |           |          |                                    | plain    |             |              | 
 created_by_staff_id           | integer                  |           |          |                                    | plain    |             |              | 
 created_at                    | timestamp with time zone |           |          | now()                              | plain    |             |              | 
 updated_at                    | timestamp with time zone |           |          | now()                              | plain    |             |              | 
 version                       | integer                  |           | not null | 1                                  | plain    |             |              | 
 company_payment               | numeric(10,2)            |           | not null | '0'::numeric                       | main     |             |              | 
 guarantee_source_order_id     | integer                  |           |          |                                    | plain    |             |              | 
 order_type                    | order_type               |           | not null | 'NORMAL'::order_type               | plain    |             |              | 
 category                      | order_category           |           |          |                                    | plain    |             |              | 
 description                   | text                     |           |          |                                    | extended |             |              | 
 late_visit                    | boolean                  |           | not null | false                              | plain    |             |              | 
 dist_escalated_logist_at      | timestamp with time zone |           |          |                                    | plain    |             |              | 
 dist_escalated_admin_at       | timestamp with time zone |           |          |                                    | plain    |             |              | 
 lat                           | numeric(9,6)             |           |          |                                    | main     |             |              | 
 lon                           | numeric(9,6)             |           |          |                                    | main     |             |              | 
 timeslot_start_utc            | timestamp with time zone |           |          |                                    | plain    |             |              | 
 timeslot_end_utc              | timestamp with time zone |           |          |                                    | plain    |             |              | 
 total_sum                     | numeric(10,2)            |           | not null |                                    | main     |             |              | 
 cancel_reason                 | text                     |           |          |                                    | extended |             |              | 
 no_district                   | boolean                  |           | not null |                                    | plain    |             |              | 
 type                          | order_type               |           | not null |                                    | plain    |             |              | 
 geocode_provider              | character varying(32)    |           |          |                                    | extended |             |              | 
 geocode_confidence            | integer                  |           |          |                                    | plain    |             |              | 
 escalation_logist_notified_at | timestamp with time zone |           |          |                                    | plain    |             |              | 
 escalation_admin_notified_at  | timestamp with time zone |           |          |                                    | plain    |             |              | 
Indexes:
    "pk_orders" PRIMARY KEY, btree (id)
    "ix_orders__assigned_master" btree (assigned_master_id)
    "ix_orders__category" btree (category)
    "ix_orders__city_id" btree (city_id)
    "ix_orders__city_status" btree (city_id, status)
    "ix_orders__created_at" btree (created_at)
    "ix_orders__district_id" btree (district_id)
    "ix_orders__guarantee_source" btree (guarantee_source_order_id)
    "ix_orders__phone" btree (client_phone)
    "ix_orders__preferred_master" btree (preferred_master_id)
    "ix_orders__status_city" btree (status, city_id)
    "ix_orders__status_city_timeslot_start" btree (status, city_id, timeslot_start_utc)
    "ix_orders__street_id" btree (street_id)
Check constraints:
    "ck_orders__timeslot_range" CHECK (timeslot_start_utc IS NULL AND timeslot_end_utc IS NULL OR timeslot_start_utc < timeslot_end_utc)
Foreign-key constraints:
    "fk_orders__assigned_master_id__masters" FOREIGN KEY (assigned_master_id) REFERENCES masters(id) ON DELETE SET NULL
    "fk_orders__city_id__cities" FOREIGN KEY (city_id) REFERENCES cities(id) ON DELETE RESTRICT
    "fk_orders__created_by_staff_id__staff_users" FOREIGN KEY (created_by_staff_id) REFERENCES staff_users(id) ON DELETE SET NULL
    "fk_orders__district_id__districts" FOREIGN KEY (district_id) REFERENCES districts(id) ON DELETE SET NULL
    "fk_orders__guarantee_source_order_id__orders" FOREIGN KEY (guarantee_source_order_id) REFERENCES orders(id) ON DELETE SET NULL
    "fk_orders__preferred_master_id__masters" FOREIGN KEY (preferred_master_id) REFERENCES masters(id) ON DELETE SET NULL
    "fk_orders__street_id__streets" FOREIGN KEY (street_id) REFERENCES streets(id) ON DELETE SET NULL
Referenced by:
    TABLE "distribution_metrics" CONSTRAINT "distribution_metrics_order_id_fkey" FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
    TABLE "commissions" CONSTRAINT "fk_commissions__order_id__orders" FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
    TABLE "offers" CONSTRAINT "fk_offers__order_id__orders" FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
    TABLE "order_autoclose_queue" CONSTRAINT "fk_order_autoclose_queue__order_id__orders" FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
    TABLE "order_status_history" CONSTRAINT "fk_order_status_history__order_id__orders" FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
    TABLE "orders" CONSTRAINT "fk_orders__guarantee_source_order_id__orders" FOREIGN KEY (guarantee_source_order_id) REFERENCES orders(id) ON DELETE SET NULL
Access method: heap


```

### Данные (до 1000 записей)

```
 id  | city_id | district_id | street_id | house | apartment | address_comment |   client_name    | client_phone |  status  | preferred_master_id | assigned_master_id | created_by_staff_id |          created_at           |          updated_at           | version | company_payment | guarantee_source_order_id | order_type | category  | description | late_visit | dist_escalated_logist_at | dist_escalated_admin_at | lat | lon |      timeslot_start_utc       |       timeslot_end_utc        | total_sum | cancel_reason | no_district |  type  | geocode_provider | geocode_confidence | escalation_logist_notified_at | escalation_admin_notified_at 
-----+---------+-------------+-----------+-------+-----------+-----------------+------------------+--------------+----------+---------------------+--------------------+---------------------+-------------------------------+-------------------------------+---------+-----------------+---------------------------+------------+-----------+-------------+------------+--------------------------+-------------------------+-----+-----+-------------------------------+-------------------------------+-----------+---------------+-------------+--------+------------------+--------------------+-------------------------------+------------------------------
 305 | 1000000 |        3460 |           | 10    |           |                 | Load Test Client | +79001234567 | ASSIGNED |                     |               3378 |                     | 2025-10-15 13:18:42.680891+00 | 2025-10-15 13:18:42.762396+00 |       2 |            0.00 |                           | NORMAL     | ELECTRICS |             | f          |                          |                         |     |     | 2025-10-15 15:18:42.668557+00 | 2025-10-15 17:18:42.668557+00 |      0.00 |               | f           | NORMAL |                  |                    |                               | 
(1 row)


```


---


## 19. Таблица: `referral_rewards`

**Количество записей:** 0

### Структура таблицы

```sql
                                                                     Table "public.referral_rewards"
       Column       |           Type           | Collation | Nullable |                   Default                    | Storage | Compression | Stats target | Description 
--------------------+--------------------------+-----------+----------+----------------------------------------------+---------+-------------+--------------+-------------
 id                 | integer                  |           | not null | nextval('referral_rewards_id_seq'::regclass) | plain   |             |              | 
 referrer_id        | integer                  |           | not null |                                              | plain   |             |              | 
 referred_master_id | integer                  |           | not null |                                              | plain   |             |              | 
 commission_id      | integer                  |           | not null |                                              | plain   |             |              | 
 level              | smallint                 |           | not null |                                              | plain   |             |              | 
 percent            | numeric(5,2)             |           | not null |                                              | main    |             |              | 
 amount             | numeric(10,2)            |           | not null |                                              | main    |             |              | 
 status             | referral_reward_status   |           | not null |                                              | plain   |             |              | 
 paid_at            | timestamp with time zone |           |          |                                              | plain   |             |              | 
 created_at         | timestamp with time zone |           |          | now()                                        | plain   |             |              | 
Indexes:
    "pk_referral_rewards" PRIMARY KEY, btree (id)
    "ix_ref_rewards__referred" btree (referred_master_id)
    "ix_ref_rewards__referrer_created" btree (referrer_id, created_at)
    "ix_ref_rewards__referrer_status" btree (referrer_id, status)
    "uq_referral_rewards__commission_level" UNIQUE CONSTRAINT, btree (commission_id, level)
Foreign-key constraints:
    "fk_referral_rewards__commission_id__commissions" FOREIGN KEY (commission_id) REFERENCES commissions(id) ON DELETE CASCADE
    "fk_referral_rewards__referred_master_id__masters" FOREIGN KEY (referred_master_id) REFERENCES masters(id) ON DELETE CASCADE
    "fk_referral_rewards__referrer_id__masters" FOREIGN KEY (referrer_id) REFERENCES masters(id) ON DELETE CASCADE
Access method: heap


```

### Данные (до 1000 записей)

```
 id | referrer_id | referred_master_id | commission_id | level | percent | amount | status | paid_at | created_at 
----+-------------+--------------------+---------------+-------+---------+--------+--------+---------+------------
(0 rows)


```


---


## 20. Таблица: `referrals`

**Количество записей:** 0

### Структура таблицы

```sql
                                                                  Table "public.referrals"
   Column    |           Type           | Collation | Nullable |                Default                | Storage | Compression | Stats target | Description 
-------------+--------------------------+-----------+----------+---------------------------------------+---------+-------------+--------------+-------------
 id          | integer                  |           | not null | nextval('referrals_id_seq'::regclass) | plain   |             |              | 
 master_id   | integer                  |           | not null |                                       | plain   |             |              | 
 referrer_id | integer                  |           | not null |                                       | plain   |             |              | 
 created_at  | timestamp with time zone |           |          | now()                                 | plain   |             |              | 
Indexes:
    "pk_referrals" PRIMARY KEY, btree (id)
    "ix_referrals__master" btree (master_id)
    "ix_referrals__referrer" btree (referrer_id)
    "uq_referrals__master_id" UNIQUE CONSTRAINT, btree (master_id)
Foreign-key constraints:
    "fk_referrals__master_id__masters" FOREIGN KEY (master_id) REFERENCES masters(id) ON DELETE CASCADE
    "fk_referrals__referrer_id__masters" FOREIGN KEY (referrer_id) REFERENCES masters(id) ON DELETE CASCADE
Access method: heap


```

### Данные (до 1000 записей)

```
 id | master_id | referrer_id | created_at 
----+-----------+-------------+------------
(0 rows)


```


---


## 21. Таблица: `settings`

**Количество записей:** 25

### Структура таблицы

```sql
                                                            Table "public.settings"
   Column    |           Type           | Collation | Nullable |         Default          | Storage  | Compression | Stats target | Description 
-------------+--------------------------+-----------+----------+--------------------------+----------+-------------+--------------+-------------
 key         | character varying(80)    |           | not null |                          | extended |             |              | 
 value       | text                     |           | not null |                          | extended |             |              | 
 value_type  | character varying(16)    |           | not null | 'STR'::character varying | extended |             |              | 
 description | text                     |           |          |                          | extended |             |              | 
 created_at  | timestamp with time zone |           |          | now()                    | plain    |             |              | 
 updated_at  | timestamp with time zone |           |          | now()                    | plain    |             |              | 
Indexes:
    "pk_settings" PRIMARY KEY, btree (key)
Access method: heap


```

### Данные (до 1000 записей)

```
             key             |                value                 | value_type |                      description                      |          created_at           |          updated_at           
-----------------------------+--------------------------------------+------------+-------------------------------------------------------+-------------------------------+-------------------------------
 commission_percent_default  | 0                                    | INT        | Комиссия по умолчанию (не используется для гарантий)  | 2025-09-17 13:59:33.664919+00 | 2025-09-17 13:59:33.664919+00
 working_hours_end           | 20:00                                | TIME       | Конец рабочего окна                                   | 2025-09-18 06:42:52.661539+00 | 2025-09-18 06:42:52.661539+00
 slot_step_minutes           | 120                                  | INT        | Шаг генерации слотов (мин)                            | 2025-09-18 06:42:52.661539+00 | 2025-09-18 06:42:52.661539+00
 distribution_sla_seconds    | 120                                  | INT        | SLA оффера (сек)                                      | 2025-09-18 06:42:52.661539+00 | 2025-09-18 06:42:52.661539+00
 distribution_rounds         | 2                                    | INT        | Круги до эскалации                                    | 2025-09-18 06:42:52.661539+00 | 2025-09-18 06:42:52.661539+00
 working_hours_start         | 10:00                                | TIME       | Начало рабочего окна                                  | 2025-09-18 06:42:52.661539+00 | 2025-09-18 07:01:50.172923+00
 owner_pay_methods_enabled   | ["card", "sbp"]                      | JSON       | Разрешённые методы оплаты комиссии                    | 2025-09-19 08:15:40.241585+00 | 2025-09-19 08:15:40.241585+00
 commission_deadline_hours   | 3                                    | INT        | Дедлайн оплаты комиссии (часы)                        | 2025-09-18 06:42:52.661539+00 | 2025-09-18 07:02:03.551941+00
 DISTRIBUTION_ROUNDS         | 1                                    | STR        |                                                       | 2025-09-18 12:59:11.24868+00  | 2025-09-18 12:59:11.24868+00
 owner_pay_card_number       | 2200123456789000                     | STR        | Номер карты (без пробелов)                            | 2025-09-19 08:15:40.241585+00 | 2025-09-19 08:15:40.241585+00
 DISTRIBUTION_SLA_SECONDS    | 120                                  | STR        |                                                       | 2025-09-18 12:57:03.641588+00 | 2025-09-18 14:59:09.102792+00
 distribution_tick_seconds   | 30                                   | INT        | Период тика распределения (сек)                       | 2025-09-19 08:15:40.241585+00 | 2025-09-19 08:15:40.241585+00
 distribution_log_topn       | 10                                   | INT        | Сколько кандидатов писать в лог                       | 2025-09-19 08:15:40.241585+00 | 2025-09-19 08:15:40.241585+00
 escalate_to_admin_after_min | 10                                   | INT        | Через сколько минут после логиста эскалировать админу | 2025-09-19 08:15:40.241585+00 | 2025-09-19 08:15:40.241585+00
 owner_pay_card_holder       | Иванов И.И.                          | STR        | Держатель карты                                       | 2025-09-19 08:15:40.241585+00 | 2025-09-19 08:15:40.241585+00
 owner_pay_card_bank         | Т-Банк                               | STR        | Банк                                                  | 2025-09-19 08:15:40.241585+00 | 2025-09-19 08:15:40.241585+00
 owner_pay_sbp_phone         | +79998987800                         | STR        | Телефон СБП                                           | 2025-09-19 08:15:40.241585+00 | 2025-09-19 08:15:40.241585+00
 owner_pay_sbp_bank          | Т-Банк                               | STR        | Банк СБП                                              | 2025-09-19 08:15:40.241585+00 | 2025-09-19 08:15:40.241585+00
 owner_pay_sbp_qr_file_id    |                                      | STR        | QR file_id (Telegram)                                 | 2025-09-19 08:15:40.241585+00 | 2025-09-19 08:15:40.241585+00
 alerts_channel_id           | -1002959114551                       | INT        | Telegram channel for alerts                           | 2025-10-03 17:10:52.822413+00 | 2025-10-03 17:10:52.822413+00
 logs_channel_id             | -1003026745283                       | INT        | Telegram channel for logs                             | 2025-10-03 17:10:52.822413+00 | 2025-10-03 17:10:52.822413+00
 reports_channel_id          | -1003056834543                       | INT        | Telegram channel for reports                          | 2025-10-03 17:10:52.822413+00 | 2025-10-03 17:10:52.822413+00
 max_active_orders           | 5                                    | INT        | Лимит активных заказов на мастера                     | 2025-09-17 13:59:33.664919+00 | 2025-10-10 14:52:13.198009+00
 owner_pay_other_text        |                                      | STR        | Иной способ (текст)                                   | 2025-09-19 08:15:40.241585+00 | 2025-09-19 08:15:40.241585+00
 owner_pay_comment_template  | Комиссия #<order_id> от <master_fio> | STR        | Шаблон комментария к платежу                          | 2025-09-19 08:15:40.241585+00 | 2025-09-19 08:15:40.241585+00
(25 rows)


```


---


## 22. Таблица: `skills`

**Количество записей:** 1

### Структура таблицы

```sql
                                                                  Table "public.skills"
   Column   |           Type           | Collation | Nullable |              Default               | Storage  | Compression | Stats target | Description 
------------+--------------------------+-----------+----------+------------------------------------+----------+-------------+--------------+-------------
 id         | integer                  |           | not null | nextval('skills_id_seq'::regclass) | plain    |             |              | 
 code       | character varying(64)    |           | not null |                                    | extended |             |              | 
 name       | character varying(160)   |           | not null |                                    | extended |             |              | 
 is_active  | boolean                  |           | not null | true                               | plain    |             |              | 
 created_at | timestamp with time zone |           |          | now()                              | plain    |             |              | 
Indexes:
    "pk_skills" PRIMARY KEY, btree (id)
    "uq_skills__code" UNIQUE CONSTRAINT, btree (code)
Referenced by:
    TABLE "master_skills" CONSTRAINT "fk_master_skills__skill_id__skills" FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE
Access method: heap


```

### Данные (до 1000 записей)

```
 id  | code |   name    | is_active |          created_at           
-----+------+-----------+-----------+-------------------------------
 267 | ELEC | Электрика | t         | 2025-10-15 13:18:08.882378+00
(1 row)


```


---


## 23. Таблица: `staff_access_code_cities`

**Количество записей:** 0

### Структура таблицы

```sql
                                             Table "public.staff_access_code_cities"
     Column     |           Type           | Collation | Nullable | Default | Storage | Compression | Stats target | Description 
----------------+--------------------------+-----------+----------+---------+---------+-------------+--------------+-------------
 access_code_id | integer                  |           | not null |         | plain   |             |              | 
 city_id        | integer                  |           | not null |         | plain   |             |              | 
 created_at     | timestamp with time zone |           |          | now()   | plain   |             |              | 
Indexes:
    "pk_staff_access_code_cities" PRIMARY KEY, btree (access_code_id, city_id)
    "ix_staff_code_cities__city" btree (city_id)
    "ix_staff_code_cities__code" btree (access_code_id)
Foreign-key constraints:
    "fk_staff_access_code_cities__access_code_id__staff_access_codes" FOREIGN KEY (access_code_id) REFERENCES staff_access_codes(id) ON DELETE CASCADE
    "fk_staff_access_code_cities__city_id__cities" FOREIGN KEY (city_id) REFERENCES cities(id) ON DELETE CASCADE
Access method: heap


```

### Данные (до 1000 записей)

```
 access_code_id | city_id | created_at 
----------------+---------+------------
(0 rows)


```


---


## 24. Таблица: `staff_access_codes`

**Количество записей:** 0

### Структура таблицы

```sql
                                                                      Table "public.staff_access_codes"
       Column        |           Type           | Collation | Nullable |                    Default                     | Storage  | Compression | Stats target | Description 
---------------------+--------------------------+-----------+----------+------------------------------------------------+----------+-------------+--------------+-------------
 id                  | integer                  |           | not null | nextval('staff_access_codes_id_seq'::regclass) | plain    |             |              | 
 code                | character varying(16)    |           | not null |                                                | extended |             |              | 
 role                | staff_role               |           | not null |                                                | plain    |             |              | 
 city_id             | integer                  |           |          |                                                | plain    |             |              | 
 created_by_staff_id | integer                  |           |          |                                                | plain    |             |              | 
 used_by_staff_id    | integer                  |           |          |                                                | plain    |             |              | 
 expires_at          | timestamp with time zone |           |          |                                                | plain    |             |              | 
 used_at             | timestamp with time zone |           |          |                                                | plain    |             |              | 
 created_at          | timestamp with time zone |           |          | now()                                          | plain    |             |              | 
 comment             | text                     |           |          |                                                | extended |             |              | 
 revoked_at          | timestamp with time zone |           |          |                                                | plain    |             |              | 
Indexes:
    "pk_staff_access_codes" PRIMARY KEY, btree (id)
    "ix_staff_access_codes__code_available" UNIQUE, btree (code) WHERE used_by_staff_id IS NULL AND revoked_at IS NULL
    "uq_staff_access_codes__code" UNIQUE CONSTRAINT, btree (code)
Foreign-key constraints:
    "fk_staff_access_codes__city_id__cities" FOREIGN KEY (city_id) REFERENCES cities(id) ON DELETE SET NULL
    "fk_staff_access_codes__issued_by_staff_id__staff_users" FOREIGN KEY (created_by_staff_id) REFERENCES staff_users(id) ON DELETE SET NULL
    "fk_staff_access_codes__used_by_staff_id__staff_users" FOREIGN KEY (used_by_staff_id) REFERENCES staff_users(id) ON DELETE SET NULL
Referenced by:
    TABLE "staff_access_code_cities" CONSTRAINT "fk_staff_access_code_cities__access_code_id__staff_access_codes" FOREIGN KEY (access_code_id) REFERENCES staff_access_codes(id) ON DELETE CASCADE
Access method: heap


```

### Данные (до 1000 записей)

```
 id | code | role | city_id | created_by_staff_id | used_by_staff_id | expires_at | used_at | created_at | comment | revoked_at 
----+------+------+---------+---------------------+------------------+------------+---------+------------+---------+------------
(0 rows)


```


---


## 25. Таблица: `staff_cities`

**Количество записей:** 0

### Структура таблицы

```sql
                                                  Table "public.staff_cities"
    Column     |           Type           | Collation | Nullable | Default | Storage | Compression | Stats target | Description 
---------------+--------------------------+-----------+----------+---------+---------+-------------+--------------+-------------
 staff_user_id | integer                  |           | not null |         | plain   |             |              | 
 city_id       | integer                  |           | not null |         | plain   |             |              | 
 created_at    | timestamp with time zone |           |          | now()   | plain   |             |              | 
Indexes:
    "pk_staff_cities" PRIMARY KEY, btree (staff_user_id, city_id)
    "ix_staff_cities__city_id" btree (city_id)
    "ix_staff_cities__staff_user_id" btree (staff_user_id)
Foreign-key constraints:
    "fk_staff_cities__city_id__cities" FOREIGN KEY (city_id) REFERENCES cities(id) ON DELETE CASCADE
    "fk_staff_cities__staff_user_id__staff_users" FOREIGN KEY (staff_user_id) REFERENCES staff_users(id) ON DELETE CASCADE
Access method: heap


```

### Данные (до 1000 записей)

```
 staff_user_id | city_id | created_at 
---------------+---------+------------
(0 rows)


```


---


## 26. Таблица: `staff_users`

**Количество записей:** 7

### Структура таблицы

```sql
                                                                       Table "public.staff_users"
        Column         |           Type           | Collation | Nullable |                 Default                 | Storage  | Compression | Stats target | Description 
-----------------------+--------------------------+-----------+----------+-----------------------------------------+----------+-------------+--------------+-------------
 id                    | integer                  |           | not null | nextval('staff_users_id_seq'::regclass) | plain    |             |              | 
 tg_user_id            | bigint                   |           |          |                                         | plain    |             |              | 
 username              | character varying(64)    |           |          |                                         | extended |             |              | 
 full_name             | character varying(160)   |           |          |                                         | extended |             |              | 
 phone                 | character varying(32)    |           |          |                                         | extended |             |              | 
 role                  | staff_role               |           | not null |                                         | plain    |             |              | 
 is_active             | boolean                  |           | not null | true                                    | plain    |             |              | 
 created_at            | timestamp with time zone |           |          | now()                                   | plain    |             |              | 
 updated_at            | timestamp with time zone |           |          | now()                                   | plain    |             |              | 
 commission_requisites | jsonb                    |           | not null | '{}'::jsonb                             | extended |             |              | 
Indexes:
    "pk_staff_users" PRIMARY KEY, btree (id)
    "ix_staff_users__tg_user_id" UNIQUE, btree (tg_user_id)
Referenced by:
    TABLE "admin_audit_log" CONSTRAINT "fk_admin_audit_log__admin_id__staff_users" FOREIGN KEY (admin_id) REFERENCES staff_users(id) ON DELETE SET NULL
    TABLE "attachments" CONSTRAINT "fk_attachments__uploaded_by_staff_id__staff_users" FOREIGN KEY (uploaded_by_staff_id) REFERENCES staff_users(id) ON DELETE SET NULL
    TABLE "master_invite_codes" CONSTRAINT "fk_master_invite_codes__issued_by_staff_id__staff_users" FOREIGN KEY (issued_by_staff_id) REFERENCES staff_users(id) ON DELETE SET NULL
    TABLE "masters" CONSTRAINT "fk_masters__verified_by__staff_users" FOREIGN KEY (verified_by) REFERENCES staff_users(id) ON DELETE SET NULL
    TABLE "order_status_history" CONSTRAINT "fk_order_status_history__changed_by_staff_id__staff_users" FOREIGN KEY (changed_by_staff_id) REFERENCES staff_users(id) ON DELETE SET NULL
    TABLE "orders" CONSTRAINT "fk_orders__created_by_staff_id__staff_users" FOREIGN KEY (created_by_staff_id) REFERENCES staff_users(id) ON DELETE SET NULL
    TABLE "staff_access_codes" CONSTRAINT "fk_staff_access_codes__issued_by_staff_id__staff_users" FOREIGN KEY (created_by_staff_id) REFERENCES staff_users(id) ON DELETE SET NULL
    TABLE "staff_access_codes" CONSTRAINT "fk_staff_access_codes__used_by_staff_id__staff_users" FOREIGN KEY (used_by_staff_id) REFERENCES staff_users(id) ON DELETE SET NULL
    TABLE "staff_cities" CONSTRAINT "fk_staff_cities__staff_user_id__staff_users" FOREIGN KEY (staff_user_id) REFERENCES staff_users(id) ON DELETE CASCADE
Access method: heap


```

### Данные (до 1000 записей)

```
 id | tg_user_id |   username    |    full_name    |    phone     |     role     | is_active |          created_at           |          updated_at           |                commission_requisites                
----+------------+---------------+-----------------+--------------+--------------+-----------+-------------------------------+-------------------------------+-----------------------------------------------------
  4 |     777000 |               |                 |              | GLOBAL_ADMIN | f         | 2025-09-18 14:56:42.316315+00 | 2025-09-18 14:56:42.316315+00 | {"SBP": "+79991234567", "CARD": "4000000000000002"}
  6 |  987654321 | admin2        | Secondary Admin | +79876543210 | ADMIN        | t         | 2025-10-03 18:09:52.812416+00 | 2025-10-03 18:09:52.812416+00 | {}
  1 |            | admin_demo    | Админ Демо      |              | GLOBAL_ADMIN | t         | 2025-09-18 07:00:17.292073+00 | 2025-10-03 18:14:23.081897+00 | {}
  5 |  332786197 | your_username | Superuser       | +your_phone  | GLOBAL_ADMIN | t         | 2025-10-03 18:09:52.812416+00 | 2025-10-03 18:41:31.911608+00 | {}
  7 | 5639433843 | shortooo      | shortooo        |              | GLOBAL_ADMIN | t         | 2025-10-04 07:12:00.842626+00 | 2025-10-04 08:23:33.523779+00 | {}
  9 | 8212329751 | top_disp      | top_disp        |              | CITY_ADMIN   | t         | 2025-10-04 08:36:58.820652+00 | 2025-10-04 08:37:35.930535+00 | {}
  8 | 6022057382 | regizdrou     | regizdrou       |              | GLOBAL_ADMIN | t         | 2025-10-04 07:26:29.087208+00 | 2025-10-09 14:01:18.849974+00 | {}
(7 rows)


```


---
