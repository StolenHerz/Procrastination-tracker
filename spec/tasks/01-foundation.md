# Этап 01. Спецификация и каркас

## Задачи 001–003. Спецификация

- `README.md`: цель, стек, структура `spec/`, правила разработки.
- `requirements.md`: MVP, нефункциональные требования, критерии готовности.
- `architecture.md`: модули, потоки, очередь событий, жизненный цикл.
- `data-model.md`: таблицы, индексы, формат времени.
- `backlog.md` и `schedule.csv`: 60 задач и расписание коммитов.

**DoD:** документы согласованы между собой, ссылки рабочие, все 60 задач
покрывают требования MVP.

## Задачи 004–006. Каркас

- `.gitignore`: `data.db`, `__pycache__`, `.venv`, `build`, `dist`, `logs`.
- `requirements.txt`: `customtkinter`, `pystray`, `Pillow`, `pyinstaller`.
- `config.py`: `APP_NAME`, `APP_VERSION`, режим темы, размеры окон, пути.
- `logging_config.py`: `RotatingFileHandler`, консольный вывод, защита от
  повторной инициализации.

**DoD:** импорт `config` и `logging_config` не создаёт побочных файлов,
`python -m compileall .` проходит.
