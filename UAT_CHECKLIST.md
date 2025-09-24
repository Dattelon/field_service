- [ ] При пустой staff_users на первом запуске в разделе "Доступ и персонал" появляются GLOBAL_ADMIN из переменной GLOBAL_ADMINS_TG_IDS.

- [ ] Попытка входа без записи выводит «Введите код доступа», а для is_active=false показывается сообщение «Доступ деактивирован, обратитесь к администратору».

- [ ] Городские роли видят очереди, финансы, мастеров и отчёты только по своим городам; глобальный админ без ограничений.

- [ ] Admin bot: global admin issues access code via adm:staff:menu (city multi-select, code card, revoke button).
- [ ] Admin bot: new city/logist staff joins with access code (code entry, PDN consent, profile data, menu limited to assigned cities).
- [ ] Heartbeat messages from admin and master bots appear in the logs channel every 60 seconds; stop once the process terminates.
- [ ] Distribution alerts fire: no district -> immediate alert, empty candidate list after two rounds -> alert to logist, 10 minutes later -> admin alert.
- [ ] Overdue commission watchdog blocks the master and pushes a 🚫 alert with a quick button to open the commission card.
- [ ] Launching a second bot instance logs the 409 conflict message and exits immediately without crashing the running instance.
- [ ] `ops/backup_db.sh` / `ops/backup_db.ps1` create dumps and prune files older than 7 days when `DATABASE_URL` is provided.

