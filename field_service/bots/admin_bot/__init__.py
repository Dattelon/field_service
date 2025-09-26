from . import services_db as _services_db
from .manual_candidates_patch import apply_manual_candidates_patch

apply_manual_candidates_patch(_services_db.DBOrdersService)
