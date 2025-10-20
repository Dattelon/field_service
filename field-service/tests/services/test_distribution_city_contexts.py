from field_service.db import models as m
from field_service.services.distribution_scheduler import _build_city_contexts


def test_build_city_contexts_assigns_staff_per_city():
    contexts = _build_city_contexts(
        cities=[
            (1, "Москва", "Europe/Moscow"),
            (2, "Казань", None),
        ],
        staff_rows=[
            (111, m.StaffRole.LOGIST, 1),
            (112, m.StaffRole.LOGIST, None),
            (201, m.StaffRole.CITY_ADMIN, 1),
            (202, m.StaffRole.CITY_ADMIN, 2),
            (301, m.StaffRole.GLOBAL_ADMIN, None),
        ],
        default_timezone="UTC",
    )

    assert set(contexts.keys()) == {1, 2}

    ctx_moscow = contexts[1]
    assert ctx_moscow.city_name == "Москва"
    assert str(ctx_moscow.timezone) == "Europe/Moscow"
    assert ctx_moscow.admin_chat_ids == (201, 301)
    assert ctx_moscow.logist_chat_ids == (111, 112, 201, 301)

    ctx_kazan = contexts[2]
    assert ctx_kazan.city_name == "Казань"
    assert str(ctx_kazan.timezone) == "UTC"
    assert ctx_kazan.admin_chat_ids == (202, 301)
    assert ctx_kazan.logist_chat_ids == (112, 202, 301)

