# Тех-спека: Layout Fixer (исправление неверной раскладки)

Встраивается в существующий проект `wayscribe`. Аналог/наследник Punto Switcher
для Wayland (KDE, GNOME, Sway, Hyprland), переосмысленный под security-модель
Wayland. Headless: фоновый демон + горячие клавиши + KDE-уведомление с превью.

## Решения по дизайну

| Вопрос | Выбор |
| --- | --- |
| Модель захвата текста | **Фаза 1**: hotkey + выделение/последнее слово (Wayland-native, без кейлоггера). **Фаза 2** (opt-in, за флагом): глобальный evdev-автокорректор |
| Конверсия раскладки | Статичная keymap (ЙЦУКЕН↔QWERTY) + триграммы для направления; **LLM-fallback** когда триграммы неуверены |
| LLM-эндпоинт | Любой OpenAI-совместимый chat-endpoint (второй FLM-контейнер ИЛИ внешний); фича выключена пока endpoint не задан |

## Зачем это ложится в wayscribe (переиспользуемая база)

- Синтез клавиш + paste non-ASCII уже есть: [output.py:21](wayscribe/output.py#L21)
  (`type_text`, `_ydotool_paste` через Ctrl+V).
- Запрос активной раскладки по D-Bus `org.kde.KeyboardLayouts`:
  [keyboard.py:60](wayscribe/keyboard.py#L60). Тот же интерфейс умеет `setLayout`.
- KDE-уведомления с превью: [output.py:70](wayscribe/output.py#L70) (`_send_notification`).
- Демон + Unix-socket IPC + state machine + единый `asyncio.Lock`:
  [daemon.py:115](wayscribe/daemon.py#L115) (`handle_command`).
- LLM-ограничение NPU: Whisper съедает все 8 колонок → chat нужен в отдельном
  контейнере (см. BACKEND.md). Поэтому chat-endpoint конфигурируется отдельно
  от STT-endpoint.

## Архитектура

Новый поток команд внутри уже существующего демона. KDE global shortcut →
`wayscribe fix` → тонкий клиент шлёт JSON по сокету → демон обрабатывает в
`handle_command` под тем же `Lock`, что и `toggle`.

Новые модули:

- `layout.py` — keymap-таблицы ЙЦУКЕН↔QWERTY (включая Shift-ряд и пунктуацию),
  функции `ru_to_en(text)` / `en_to_ru(text)`, обе чистые и без зависимостей.
- `langdetect.py` — триграммный скоринг. Частотные таблицы триграмм для ru/en
  (встроены как данные пакета). `score(text) -> {"ru": float, "en": float}`;
  `dominant(text) -> ("ru"|"en", confidence)`. Используется для решения
  направления конверсии и порога уверенности.
- `llm.py` — HTTP-клиент к chat-endpoint (httpx, как `transcriber.py`).
  `spellfix(text, lang) -> str`, `translate_to_en(text) -> str`,
  `fix_layout(text) -> str` (fallback). Best-effort: при недоступности
  endpoint — лог + no-op, демон не падает (тот же контракт, что «FLM unreachable»).
- `selection.py` — захват и замена текста под выделением (см. ниже).

### Захват и замена текста (Фаза 1, без кейлоггера)

1. **Источник текста** (по приоритету конфига):
   - PRIMARY-выделение: `wl-paste --primary --no-newline`. Если непусто — берём его.
   - Иначе авто-захват последнего слова: синтез `Ctrl+Shift+Left` × N через
     `ydotool key`, затем чтение выделения. N (число слов) — конфиг.
2. **Решение**: `langdetect.dominant` на исходнике → определить, что текст набран
   в неверной раскладке (например, латиница, дающая осмысленный русский после
   `en_to_ru`). Сравниваем score(исходник) vs score(переложенного) — выбираем
   вариант с более высокой уверенностью.
3. **Конверсия**: статичная keymap. Если |Δconfidence| < порога (неуверенно) и
   LLM включён → `llm.fix_layout` как fallback.
4. **Замена in-place**: выделенный текст перезаписывается перепечаткой
   (на выделение печать заменяет его). Используем существующий `output.type_text`
   (ASCII → `ydotool type`, non-ASCII → wl-copy+Ctrl+V). Для «последнего слова»
   без выделения — `Backspace` × len через `ydotool key` + перепечатка.
5. **Превью**: KDE-уведомление `было → стало` через `_live_notify`.
6. **Опц. переключение активной раскладки KDE** (конфиг `switch_layout`): после
   правки вызвать `org.kde.KeyboardLayouts.setLayout`, чтобы следующий ввод шёл
   уже в правильной раскладке.

### Фаза 2 (opt-in): evdev-автокорректор

За явным флагом `evdev_autocorrect = true` и предупреждением в doctor. Демон
читает `/dev/input/event*` (группа `input`, как уже требует ydotool для uinput),
буферизует клавиши по словам в памяти, на границе слова скорит триграммы и при
срабатывании порога делает Backspace+перепечатку. **Security**: это эффективно
кейлоггер — буфер только в памяти, никогда на диск, очищается на границе слова;
doctor явно предупреждает; по умолчанию выключено. Отдельный asyncio-таск,
сносится вместе с демоном.

## Новые команды CLI / IPC

| CLI | IPC cmd | Действие |
| --- | --- | --- |
| `wayscribe fix` | `fix` | Переложить раскладку выделения/последнего слова |
| `wayscribe fix --spell` | `fix` + `mode=spell` | Переложить + LLM-исправление ошибок |
| `wayscribe translate` | `translate` | Перевести выделение на английский (LLM) |

Регистрируются в [CLI-парсере](wayscribe/__main__.py) (build_parser + dispatch) и
в `handle_command` ([daemon.py:143](wayscribe/daemon.py#L143)) рядом с `toggle`.
Команды работают только в `State.IDLE` (не мешают записи); иначе — `busy`.

## Новые ключи конфига (`config.py`)

```toml
# Layout fixer
layout_pairs = ["ru", "en"]          # между какими раскладками перекладываем
fix_source = "selection"             # "selection" | "last_word"
fix_last_word_count = 1              # сколько слов захватывать в режиме last_word
switch_layout = false                # переключать активную KDE-раскладку после правки
trigram_confidence_min = 0.15        # порог |Δ|, ниже которого зовём LLM-fallback

# LLM (chat) — отдельно от STT endpoint
llm_endpoint = ""                    # пусто = LLM-фичи выключены
llm_model = ""
llm_api_key = ""                     # для внешних OpenAI-совместимых
llm_timeout_sec = 30.0

# Phase 2 (opt-in, security-sensitive)
evdev_autocorrect = false
```

Незаданный `llm_endpoint` ⇒ `--spell`/`translate` отвечают «LLM не настроен»
(уведомление), `fix` работает на одной keymap без fallback.

## Тесты (`tests/`, pytest)

- `test_layout.py` — round-trip keymap (`en_to_ru(ru_to_en(x)) == x`), пунктуация,
  Shift-ряд, не-буквенные символы проходят без изменений.
- `test_langdetect.py` — `ghbdtn`→ru-доминанта, `руддщ`→en-доминанта, короткие/
  пустые строки не падают.
- `test_llm.py` — httpx-мок: spellfix/translate/fix_layout парсят ответ; при
  ConnectError возвращают исходник + лог (best-effort контракт).
- Команда `fix` в `handle_command`: мок `selection`/`output`, проверка
  IDLE-гейта и busy-ответа.

## Doctor

Добавить в [doctor.py](wayscribe/doctor.py): проверку `wl-paste` (захват
выделения), достижимость `llm_endpoint` (если задан), и — при
`evdev_autocorrect` — членство в группе `input` + предупреждение о
характере фичи.

## Открытые вопросы

- Триграммные таблицы: взять готовый корпус или сгенерировать из небольшого
  текстового сэмпла на этапе сборки? (влияет на размер пакета / PyInstaller-бандл).
- `fix_source = "last_word"`: надёжность синтеза `Ctrl+Shift+Left` зависит от
  приложения (терминал vs GUI). Возможно, держать `selection` дефолтом.
- Нужна ли отдельная горячая клавиша на `translate`, или один `fix` с режимами?
