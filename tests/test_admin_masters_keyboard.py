from field_service.bots.admin_bot.dto import MasterListItem
from field_service.bots.admin_bot.routers import admin_masters


def _sample_item(master_id: int = 1) -> MasterListItem:
    return MasterListItem(
        id=master_id,
        full_name=f"Master {master_id}",
        city_name="City",
        skills=(),
        rating=5.0,
        has_vehicle=False,
        is_on_shift=False,
        shift_status="SHIFT_OFF",
        on_break=False,
        verified=True,
        is_active=True,
        is_deleted=False,
        active_orders=0,
        max_active_orders=None,
        avg_check=None,
    )


def test_build_list_kb_adds_group_tabs_for_master_menu():
    markup = admin_masters.build_list_kb(
        group="ok",
        category="all",
        page=1,
        items=[_sample_item()],
        has_next=False,
        skills=[],
        prefix="adm:m",
    )

    rows = markup.inline_keyboard
    assert rows, "keyboard should contain at least group row"
    first_row_callbacks = [button.callback_data for button in rows[0]]
    expected_callbacks = [f"adm:m:grp:{key}" for key in admin_masters.MASTER_GROUP_ORDER]
    assert first_row_callbacks == expected_callbacks
    assert rows[0][0].text.startswith("["), "active group should be highlighted"


def test_build_list_kb_no_group_tabs_for_other_prefix():
    markup = admin_masters.build_list_kb(
        group="mod",
        category="all",
        page=1,
        items=[_sample_item()],
        has_next=False,
        skills=[],
        prefix="adm:mod",
    )

    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert not any(cb.startswith("adm:m:grp:") for cb in callbacks)
