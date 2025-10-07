from __future__ import annotations

from pathlib import Path


def replace_in_block(lines: list[str], func_name: str, old_prefix: str, new_line: str) -> None:
    # naive: find def line, then within next 50 lines replace first line that startswith old_prefix
    for i, line in enumerate(lines):
        if line.strip().startswith(f"async def {func_name}("):
            for j in range(i, min(i + 50, len(lines))):
                if lines[j].lstrip().startswith(old_prefix):
                    indent = lines[j][: len(lines[j]) - len(lines[j].lstrip())]
                    lines[j] = indent + new_line + "\n"
                    return


def main() -> None:
    path = Path("field-service/field_service/bots/admin_bot/handlers.py")
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    replace_in_block(lines, "settings_edit_cancel", "await msg.answer(", 'await msg.answer("Редактирование отменено.")')
    replace_in_block(lines, "settings_edit_value", "await msg.answer(", 'await msg.answer("Настройка сохранена.")')
    replace_in_block(lines, "cb_logs_clear", "await cq.answer(", 'await cq.answer("Готово")')

    path.write_text("".join(lines), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()

