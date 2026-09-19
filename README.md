# 🧠 ARBITER — Adaptive Multi-Model Intelligence Router

**ARBITER** — высокопроизводительный, самообучающийся интеллектуальный маршрутизатор запросов к LLM (OpenAI, Anthropic Claude, Google Gemini, локальные и mock-модели) с открытой архитектурой и поддержкой стандарта OpenAI API.

---

## 🏗️ Архитектура системы (7 подсистем)

```
┌─────────────────────────────────────────────────────────┐
│                    API Gateway (FastAPI)                  │
│  OpenAI-compatible endpoint (/v1) + WebSocket dashboard │
└──────────┬──────────────────────────────────┬────────────┘
           │                                  │
     ┌─────▼─────┐                    ┌───────▼───────┐
     │ Classifier│                    │   Dashboard   │
     │ (Zero-LLM)│                    │  (Module 7)   │
     └─────┬─────┘                    └───────▲───────┘
           │                                  │
     ┌─────▼─────────────────────┐    ┌───────┴───────┐
     │   Router / MAB Engine     │    │ Metrics Store │
     │   (Module 3)              │◄───│  (Module 6)   │
     └─────┬─────────────────────┘    └───────▲───────┘
           │                                  │
     ┌─────▼─────────────────────┐            │
     │   Provider Pool           │────────────┘
     │   (Module 4)              │
     │   - Rate Limiter (GCRA)   │
     │   - Circuit Breaker       │
     │   - Stream Multiplexer    │
     └─────┬─────────────────────┘
           │
     ┌─────▼─────────────────────┐
     │   Response Evaluator      │
     │   (Module 5)              │
     │   - Structural & AST Code │
     │   - Coherence & Consensus │
     └──────────────────────────┘
```

---

## ⚡ Ключевые возможности

1. **Module 1: OpenAI-Compatible Drop-In Proxy**
   - Полная совместимость с `/v1/chat/completions` (любой SDK или библиотека подключается простой сменой `base_url="http://localhost:8000/v1"`).
   - Поддержка непрерывного SSE-стриминга (`stream: true`) с динамической подменой метаданных на лету.
   - Поддержка кастомных заголовков:
     - `X-Arbiter-Strategy: auto | fastest | cheapest | quality | consensus`
     - `X-Arbiter-Budget: 0.05` (максимальная стоимость запроса в долларах).

2. **Module 2: Zero-LLM Task Classifier**
   - Скорость инференса: **< 5 мс**.
   - Не расходует токены и не делает сетевых запросов.
   - 10 категорий: `code_generation`, `code_review`, `creative_writing`, `data_analysis`, `translation`, `summarization`, `reasoning`, `conversation`, `system_prompt`, `multimodal`.
   - Граничный разбор приоритетов (например, *"напиши код который переводит"* классифицируется как `code_generation`).
   - Фоновый цикл самообучения (`SelfTrainer`) на основе пользовательских оценок.

3. **Module 3: Multi-Armed Bandit (MAB) Router Engine**
   - Контекстное сэмплирование Томпсона на базе апостериорных $\text{Beta}(\alpha, \beta)$ распределений для каждой пары `(модель, категория)`.
   - Механизм затухания (**Exponential Decay** с настраиваемым периодом полураспада $T_{half}$), предотвращающий фиксацию на устаревших оценках моделей.
   - **Constraint Solver**: учет ограничений по бюджету, SLA задержки и доступности провайдеров.

4. **Module 4: Provider Pool & Stream Multiplexer**
   - Асинхронный двумерный **Token Bucket Rate Limiter** с раздельными лимитами для RPM (запросы в минуту) и TPM (токены в минуту), поддержкой burst-всплесков и экспоненциальным backoff при получении HTTP 429.
   - Автомат состояний **Circuit Breaker** (`CLOSED` ➔ `OPEN` ➔ `HALF_OPEN`) для защиты от каскадных сбоев.
   - **Stream Multiplexer** с адаптивным таймаутом для режима консенсуса.
   - **Cost Calculator**: матрица тарифов с учетом скидок на prompt caching.

5. **Module 5: Zero-LLM Response Evaluator & Merge Engine**
   - Оценка структуры (полнота, markdown-разметка, списки, скобки).
   - AST-парсинг и синтаксический анализ кода (Python AST, валидация JS/TS, цикломатическая сложность).
   - Когерентность и семантическое соответствие промпту с детекцией маркеров галлюцинаций.
   - Алгоритм многомодельного слияния (Consensus Merge): выявление явного статистического лидера ($> 2\sigma$) или структурное слияние непересекающихся секций ответа.

6. **Module 6: Metrics Store & Learning Engine**
   - Асинхронная БД (SQLite в режиме WAL для нулевой латентности и высокой конкурентности или PostgreSQL).
   - Атомарные обновления состояния бандита.
   - Аналитические агрегации: расчет перцентилей задержки (P50, P95, P99), win rate моделей, тепловая карта качества, предиктивный прогноз месячных расходов.

7. **Module 7: Real-Time Dashboard**
   - Премиальный веб-интерфейс (Glassmorphism, Cyber Dark Theme, Chart.js, WebSocket с авто-реконнектом).
   - 4 экрана:
     1. **Live Feed**: поток маршрутизации запросов в реальном времени с мгновенными кнопками оценки 👍 / 👎.
     2. **Analytics**: win rates моделей, разбивка расходов по категориям, таблица перцентилей задержки, тепловая карта качества.
     3. **Bandit Explorer**: визуализация кривых плотности вероятности (PDF) Beta-распределений для всех моделей и интерактивный симулятор параметров $\epsilon$ и decay.
     4. **Provider Health**: мониторинг состояния Circuit Breaker, индикаторы утилизации RPM/TPM и тестовая консоль.

8. **Бонусные модули**:
   - **Bonus 1: Custom Evaluation DSL**: собственный лексер, парсер, AST и интерпретатор правил валидации с встроенными функциями `ast_parse` и `contains`.
   - **Bonus 2: Replay & Debug Mode**: сохранение полных трасс и эндпоинт `/v1/arbiter/replay` для ретроспективного сравнения стратегий и бюджетов.

---

## 🚀 Быстрый старт

### 1. Установка зависимостей
```powershell
.\.venv\Scripts\pip.exe install -r requirements.txt
```

### 2. Конфигурация окружения
Создайте файл `.env` на основе `.env.example`:
```ini
HOST=0.0.0.0
PORT=8000
DATABASE_URL=sqlite+aiosqlite:///./arbiter.db

# API Ключи (опционально, при их отсутствии система прозрачно работает через MockProvider)
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
```

### 3. Запуск сервера
```powershell
.\.venv\Scripts\uvicorn.exe arbiter.gateway.app:app --host 0.0.0.0 --port 8000
```
- Веб-дашборд: [http://localhost:8000](http://localhost:8000)
- OpenAPI интерактивная документация: [http://localhost:8000/docs](http://localhost:8000/docs)
- WebSocket шина: `ws://localhost:8000/ws/dashboard`

---

## 🧪 Запуск набора тестов

Полный набор из 29 тестов (включая property-based тестирование инвариантов через Hypothesis):
```powershell
.\.venv\Scripts\pytest.exe -v tests/
```

---

## 📡 Примеры использования API

### 1. Стандартный запрос через OpenAI SDK (Python)
```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed"
)

response = client.chat.completions.create(
    model="arbiter-auto",
    messages=[
        {"role": "user", "content": "Напиши алгоритм быстрой сортировки на Python"}
    ],
    extra_headers={
        "X-Arbiter-Strategy": "auto",
        "X-Arbiter-Budget": "0.05"
    }
)

print(response.choices[0].message.content)
print("Категория задачи:", getattr(response, "arbiter_category", "N/A"))
```

### 2. Режим консенсуса (параллельный опрос и слияние)
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Arbiter-Strategy: consensus" \
  -d '{"messages": [{"role": "user", "content": "Сравни микросервисы и монолит"}]}'
```

### 3. Отправка обратной связи (обучение MAB)
```bash
curl -X POST http://localhost:8000/v1/arbiter/feedback \
  -H "Content-Type: application/json" \
  -d '{"request_id": "req-123456", "rating": 1, "comment": "Отличный ответ!"}'
```
