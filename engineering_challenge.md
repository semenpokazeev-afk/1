# 🧠 ARBITER — Adaptive Multi-Model Intelligence Router

## Для кого это

Ты работаешь с LLM каждый день. Ты тратишь деньги на API, переключаешься между моделями вручную, гадаешь какая модель лучше справится с задачей, теряешь время на retry'и и rate limit'ы. **Arbiter** — это система, которая решает все эти проблемы и со временем становится умнее.

> [!CAUTION]
> **Это не "оберни API и добавь UI".** Здесь 7 инженерных подсистем, каждая из которых содержит алгоритмические задачи, которые нельзя решить простым промптом к нейросети. Нейросеть поможет с бойлерплейтом, но архитектурные решения, дебаг concurrency, настройку алгоритмов и интеграцию — придётся делать головой.

---

## Что это делает (User Stories)

1. Я отправляю запрос в единый endpoint → система сама выбирает оптимальную модель (по типу задачи, бюджету, latency)
2. Для критичных запросов система отправляет в 2-3 модели параллельно и мержит лучший ответ
3. Я вижу в реальном времени: сколько потратил, какая модель лучше справляется, где bottleneck'и
4. Система учится на моих оценках (👍/👎) и со временем маршрутизирует точнее
5. Если модель упала или rate limit — автоматический fallback без потери контекста

---

## Архитектура (7 подсистем)

```
┌─────────────────────────────────────────────────────────┐
│                    API Gateway (FastAPI)                  │
│  OpenAI-compatible endpoint + WebSocket для dashboard     │
└──────────┬──────────────────────────────────┬────────────┘
           │                                  │
     ┌─────▼─────┐                    ┌───────▼───────┐
     │  Classifier │                    │   Dashboard    │
     │  (Module 2) │                    │   (Module 7)   │
     └─────┬─────┘                    └───────▲───────┘
           │                                  │
     ┌─────▼─────────────────────┐    ┌───────┴───────┐
     │   Router / MAB Engine     │    │  Metrics Store │
     │   (Module 3)              │◄───│  (Module 6)    │
     └─────┬─────────────────────┘    └───────▲───────┘
           │                                  │
     ┌─────▼─────────────────────┐            │
     │   Provider Pool           │────────────┘
     │   (Module 4)              │
     │   - Rate Limiter          │
     │   - Retry Engine          │
     │   - Stream Multiplexer    │
     └─────┬─────────────────────┘
           │
     ┌─────▼─────────────────────┐
     │   Response Evaluator      │
     │   (Module 5)              │
     │   - Quality Estimator     │
     │   - Merge Engine          │
     └──────────────────────────┘
```

---

## Module 1: API Gateway

### Требования
- OpenAI-совместимый API (`/v1/chat/completions`) — чтобы можно было подключить как drop-in replacement
- Поддержка streaming (SSE) и non-streaming режимов
- WebSocket endpoint для real-time dashboard
- Header `X-Arbiter-Strategy: auto | fastest | cheapest | quality | consensus`
- Header `X-Arbiter-Budget: 0.05` (макс. стоимость запроса в $)

### Инженерная сложность
- Нужно корректно проксировать SSE stream, при этом на лету подменяя metadata (model name, usage stats)
- WebSocket должен push'ить события маршрутизации в реальном времени, не блокируя основной request pipeline
- Graceful degradation: если classifier упал — fallback на default model без задержки

---

## Module 2: Task Classifier (БЕЗ использования LLM)

> [!IMPORTANT]
> Это ключевое ограничение. Классификатор НЕ должен вызывать LLM для классификации — иначе это chicken-and-egg problem (мы тратим деньги/время на классификацию, чтобы сэкономить деньги/время).

### Категории задач
```
code_generation    — генерация кода
code_review        — ревью и анализ кода  
creative_writing   — креативное письмо
data_analysis      — анализ данных, SQL, формулы
translation        — перевод
summarization      — суммаризация
reasoning          — логика, математика, головоломки
conversation       — обычный чат
system_prompt      — системные промпты, инструкции
multimodal         — запросы с изображениями/файлами
```

### Что нужно реализовать
1. **Feature Extractor** — извлекает из промпта:
   - Средняя длина слов
   - Наличие code fence'ов (```)
   - Доля ASCII vs Unicode символов (для детекции перевода)
   - Наличие ключевых паттернов (regex-based)
   - Оценка "сложности" через readability metrics (Flesch-Kincaid адаптированный)
   - Наличие числовых данных / таблиц
   - Длина и структура conversation history
   
2. **Классификатор** — лёгкая модель (scikit-learn или ручной rule engine):
   - Первый уровень: rule-based (быстрый, 0ms)
   - Второй уровень: trained model (точнее, ~5ms)
   - Нужен fallback на rule-based если модель ещё не обучена

3. **Self-training loop** — классификатор учится на данных из Module 6 (какие запросы к каким моделям были отправлены и какие оценки получили)

### 🔴 Почему это сложно
- Нужно собрать или сгенерировать обучающий датасет
- Rule engine должен быть расширяемым (DSL или config)
- Балансировка precision/recall для каждой категории
- Мультиязычность (русский + английский минимум)
- Граничные случаи: "напиши код который переводит текст" — это code_generation или translation?

---

## Module 3: Router / Multi-Armed Bandit Engine

### Алгоритм маршрутизации

Для каждой пары `(task_category, strategy)` система должна выбирать оптимального provider'а. Это **классическая задача Multi-Armed Bandit** с контекстом.

### Что нужно реализовать

1. **Thompson Sampling** с контекстными признаками:
   ```
   Для каждого provider p и категории c:
     - Поддерживать Beta-распределение B(α_pc, β_pc)
     - α обновляется на positive feedback
     - β обновляется на negative feedback
     - Сэмплировать из распределения для выбора
   ```

2. **Constraint Solver** — маршрутизация с ограничениями:
   - Бюджет пользователя (X-Arbiter-Budget)
   - Latency SLA (стратегия "fastest")
   - Доступность provider'а (rate limits, downtime)
   - Минимальный exploration rate (чтобы не застревать в local optimum)

3. **Consensus Mode** — для стратегии "quality":
   - Отправить в Top-N моделей параллельно
   - Дождаться всех ответов (с timeout)
   - Передать в Merge Engine (Module 5)

4. **Decay Mechanism** — старые данные должны "забываться":
   - Exponential decay с настраиваемым half-life
   - Иначе система не адаптируется к изменениям в моделях (после апдейтов)

### 🔴 Почему это сложно
- Thompson Sampling с контекстом — нетривиальная математика
- Constraint solver с real-time ограничениями (бюджет уже потрачен на N% за сегодня)
- Decay нужно правильно интегрировать — слишком быстрый = не учится, слишком медленный = не адаптируется
- Cold start problem: что делать с новым provider'ом, для которого нет данных?
- Нужна корректная работа при конкурентном доступе (несколько запросов одновременно обновляют распределения)

---

## Module 4: Provider Pool & Stream Multiplexer

### Provider Interface
```python
class Provider(Protocol):
    name: str
    models: list[str]
    
    async def complete(
        self, 
        messages: list[Message],
        model: str,
        stream: bool = False,
        **kwargs
    ) -> AsyncIterator[Chunk] | Response:
        ...
    
    async def health_check(self) -> HealthStatus:
        ...
    
    def estimate_cost(self, input_tokens: int, output_tokens: int, model: str) -> Decimal:
        ...
```

### Что нужно реализовать

1. **Token Bucket Rate Limiter** (per-provider, per-model):
   - Не просто `time.sleep()` — нужен async-aware rate limiter
   - С поддержкой burst'ов
   - С автоматическим backoff при 429
   - **С разделением между requests/min и tokens/min** (у разных API разные лимиты)

2. **Circuit Breaker**:
   - States: CLOSED → OPEN → HALF_OPEN
   - Настраиваемые thresholds (N ошибок за M секунд)
   - При OPEN — мгновенный fallback, не тратим время на timeout

3. **Stream Multiplexer** (для consensus mode):
   - Получает SSE streams от N провайдеров параллельно
   - Буферизирует chunks до тех пор, пока все не завершатся
   - Передает результат в Merge Engine
   - **Хитрость**: нужно правильно обрабатывать случай когда один provider отвечает за 2 секунды, а другой за 30
   - Adaptive timeout: не ждать слишком долго, но и не обрезать хороший ответ

4. **Cost Calculator**:
   - Каждый провайдер имеет свой формат pricing (per 1K tokens, per 1M tokens, с кэш-скидкой)
   - Нужно считать стоимость ДО отправки (estimate) и ПОСЛЕ (actual)
   - Учитывать cached tokens (Gemini context caching, Anthropic prompt caching)

### 🔴 Почему это сложно
- Async rate limiter, который корректно работает под нагрузкой — классическая задача с subtle bugs
- Circuit breaker + rate limiter вместе создают сложное state machine
- Stream multiplexer с adaptive timeout — нужно балансировать между quality и latency
- Cost calculation с кэшированием — нужно трекать, какие промпты уже в кэше у провайдера

---

## Module 5: Response Evaluator & Merge Engine

### Quality Estimator (без LLM-as-judge)

> [!IMPORTANT]
> Опять ключевое ограничение: нельзя использовать LLM для оценки качества LLM — это удваивает стоимость. Нужны эвристики.

1. **Structural Quality Score**:
   - Полнота: ответ содержит все запрошенные элементы?
   - Форматирование: markdown, code blocks, списки — правильно ли оформлены?
   - Длина: слишком короткий (недораскрыто) или слишком длинный (водянистый)?
   - Самосогласованность: нет ли противоречий в разных частях ответа?

2. **Code Quality Score** (для code_generation):
   - Парсится ли код? (AST parsing)
   - Есть ли синтаксические ошибки?
   - Используются ли правильные импорты?
   - Complexity metrics (cyclomatic complexity)

3. **Coherence Score**:
   - Ответ релевантен вопросу? (TF-IDF / embedding similarity без LLM)
   - Нет ли hallucination markers (фразы типа "as an AI", "I cannot", excessive hedging)

### Merge Engine (для consensus mode)

Получает N ответов на один и тот же запрос. Нужно создать один "лучший" ответ.

**Алгоритм:**
1. Оценить каждый ответ по Quality Score
2. Если один явно лучше (score > 2σ от остальных) → вернуть его
3. Если ответы похожи → вернуть ответ с лучшим score
4. Если ответы разные и score близкий → **structural merge**:
   - Разбить на секции
   - Для каждой секции выбрать лучший вариант
   - Проверить согласованность мержа

### 🔴 Почему это сложно
- Quality estimation без LLM — это research-grade задача
- Structural merge текста — нет готового решения, нужен собственный алгоритм
- Детекция self-inconsistency — NLP задача, не решается regex'ами
- Code parsing для произвольных языков — нужен multi-language AST parser
- Всё это должно работать за <100ms чтобы не добавлять latency

---

## Module 6: Metrics Store & Learning Engine

### Data Model

```sql
-- Каждый запрос
CREATE TABLE requests (
    id UUID PRIMARY KEY,
    timestamp TIMESTAMPTZ,
    task_category VARCHAR(50),
    strategy VARCHAR(20),
    input_tokens INT,
    estimated_cost DECIMAL(10, 6),
    budget_limit DECIMAL(10, 6) NULL
);

-- Каждый provider call (может быть несколько на один request в consensus mode)
CREATE TABLE provider_calls (
    id UUID PRIMARY KEY,
    request_id UUID REFERENCES requests(id),
    provider VARCHAR(50),
    model VARCHAR(100),
    status VARCHAR(20), -- success, error, timeout, rate_limited
    latency_ms INT,
    input_tokens INT,
    output_tokens INT,
    actual_cost DECIMAL(10, 6),
    quality_score FLOAT,
    was_selected BOOLEAN -- был ли этот ответ выбран как финальный
);

-- Пользовательский фидбек
CREATE TABLE feedback (
    id UUID PRIMARY KEY,
    request_id UUID REFERENCES requests(id),
    rating INT CHECK (rating BETWEEN -1 AND 1), -- -1, 0, 1
    timestamp TIMESTAMPTZ
);

-- Состояние MAB
CREATE TABLE bandit_state (
    provider VARCHAR(50),
    model VARCHAR(100),
    task_category VARCHAR(50),
    alpha FLOAT DEFAULT 1.0,
    beta FLOAT DEFAULT 1.0,
    total_trials INT DEFAULT 0,
    last_updated TIMESTAMPTZ
);
```

### Analytics Queries (должны работать быстро)
- Средняя стоимость по категориям за последние 24h / 7d / 30d
- Win rate каждой модели по категориям (сколько раз была выбрана / сколько раз участвовала)
- Trend линии quality score по моделям
- Аномалии: резкое падение quality или рост latency
- Прогноз месячных расходов на основе текущего usage

### 🔴 Почему это сложно
- Нужна efficient write path (каждый запрос = 2-5 записей в БД)
- Analytics queries на растущих таблицах — нужны индексы и, возможно, materialized views
- Обновление bandit_state должно быть atomic (concurrent requests)
- Прогноз расходов — нужна простая time-series модель
- Data retention policy: не хранить всё вечно, но не терять важные aggregates

---

## Module 7: Real-Time Dashboard

### Технологии
- Frontend: React + TailwindCSS + Recharts (или Vue + если предпочитаешь)
- Связь: WebSocket для real-time, REST для historical data

### Экраны

**1. Live Feed** (главный экран)
- Поток запросов в реальном времени (как tail -f для логов)
- Каждый запрос: категория → выбранная модель → latency → cost → quality score
- Цветовая индикация: 🟢 отлично, 🟡 норм, 🔴 проблема

**2. Analytics**
- График расходов по дням/неделям (stacked bar по моделям)
- Pie chart: распределение запросов по категориям
- Heatmap: quality score по модели × категории
- Линейный график: latency P50/P95/P99 по моделям

**3. Bandit Explorer**
- Визуализация Beta-распределений для каждой пары (модель, категория)
- Слайдер для simulation: "что будет, если exploration rate = X?"
- Лог решений: почему для конкретного запроса была выбрана конкретная модель

**4. Provider Health**
- Текущий статус каждого provider'а (Circuit Breaker state)
- Rate limit utilization (%)
- Error rate за последний час
- Uptime graph

### 🔴 Почему это сложно
- WebSocket state management с reconnection и buffering
- Визуализация Beta-распределений — нужно рендерить probability density functions
- Heatmap с реальными данными, а не заглушками
- Responsive design для 4 разных экранов
- Performance: dashboard не должен лагать при 100 req/sec в live feed

---

## Бонусные вызовы (если основное покажется мало)

### 🌟 Bonus 1: Custom Evaluation DSL
Создай мини-язык для описания правил оценки:

```
rule "code_must_parse" {
  when task_category == "code_generation"
  check ast_parse(response.code_blocks[0]) == true
  score +2.0
}

rule "no_hallucination_markers" {
  when true
  check not contains(response.text, ["as an AI", "I cannot verify"])
  score +0.5
}

rule "response_length_appropriate" {
  when task_category == "summarization"
  check response.word_count < input.word_count * 0.3
  score +1.0
}
```

Нужно: лексер → парсер → AST → интерпретатор. Готовые библиотеки для DSL использовать можно, но язык должен быть свой.

### 🌟 Bonus 2: Replay & Debug Mode
- Сохранять полный trace каждого запроса (промпт → classifier решение → router решение → provider responses → evaluator scores → final response)
- Возможность "replay" запроса с другими параметрами (другой explorer rate, другой budget)
- Diff двух replay'ев

### 🌟 Bonus 3: Prompt Mutation Engine
- Для consensus mode: не отправлять одинаковый промпт в разные модели
- Мутировать промпт: добавить "Think step by step", изменить температуру, добавить few-shot examples
- Трекать какие мутации улучшают quality для каких моделей

---

## Стек технологий (рекомендованный)

| Компонент | Технология |
|-----------|-----------|
| Backend | Python 3.12+ / FastAPI |
| Async | asyncio + aiohttp |
| Database | PostgreSQL + asyncpg |
| Cache | Redis (для rate limiter state, short-term metrics) |
| ML | scikit-learn (classifier), numpy/scipy (MAB, statistics) |
| Frontend | React 18+ / TypeScript / TailwindCSS |
| Charts | Recharts или D3.js |
| WebSocket | FastAPI WebSocket + reconnecting-websocket (client) |
| Testing | pytest + pytest-asyncio + hypothesis (property-based) |
| Containerization | Docker Compose (backend + postgres + redis + frontend) |

---

## Критерии "Готово"

### Minimum Viable Product (Level 1)
- [ ] API Gateway работает как OpenAI-compatible proxy
- [ ] Rule-based classifier определяет категорию задачи
- [ ] Простой round-robin router (без MAB)
- [ ] Один provider (OpenAI или Gemini)
- [ ] Logging в stdout

### Production-Ready (Level 2)
- [ ] 3+ провайдера (OpenAI, Anthropic, Gemini)
- [ ] Thompson Sampling router с constraint'ами
- [ ] Token Bucket rate limiter + Circuit Breaker
- [ ] Quality evaluator с 3+ метриками
- [ ] PostgreSQL storage + basic analytics
- [ ] Feedback API (👍/👎)
- [ ] Docker Compose для запуска

### Полный зверь (Level 3)
- [ ] Все 7 модулей полностью реализованы
- [ ] Consensus mode с Stream Multiplexer и Merge Engine
- [ ] Trained classifier с self-training loop
- [ ] Real-time dashboard с 4 экранами
- [ ] Evaluation DSL
- [ ] Property-based тесты для MAB и Rate Limiter
- [ ] Документация с architecture decision records
- [ ] < 50ms overhead на routing decision

---

## Подсказки (не ответы!)

1. **Для Rate Limiter**: посмотри алгоритм Generic Cell Rate Algorithm (GCRA) — он элегантнее классического Token Bucket для async контекста
2. **Для MAB**: начни с простого UCB1, затем переходи к Thompson Sampling. Понимание UCB1 поможет понять, почему Thompson Sampling лучше
3. **Для Classifier**: не пытайся сделать идеальный классификатор сразу. Начни с regex rules, потом добавь TF-IDF + Naive Bayes
4. **Для Merge Engine**: посмотри как работает `diff3` в git — трёхсторонний merge текста
5. **Для Dashboard**: не рендери все данные — используй виртуализацию списка и downsampling для графиков
6. **Для тестов**: `hypothesis` библиотека отлично подходит для тестирования rate limiter'а — генерирует рандомные паттерны запросов

---

## Что нейросеть НЕ сделает за тебя

| Задача | Почему AI не справится |
|--------|----------------------|
| Настройка decay rate для MAB | Зависит от ТВОИХ паттернов использования. Нужен эксперимент |
| Пороги для Circuit Breaker | Зависит от конкретных API — у Gemini и Anthropic разные failure modes |
| Feature engineering для classifier | Нужно анализировать ТВОИ реальные промпты, а не синтетические |
| Adaptive timeout для Stream Multiplexer | Latency distribution зависит от сети, региона, модели. Нужен profiling |
| Dashboard UX | Layout, цвета, приоритизация информации — design decisions, которые требуют итерации |
| Integration testing | Реальные API ведут себя не так, как mock'и. Rate limit'ы, timeout'ы, неожиданные response formats |
| Performance tuning | 50ms бюджет на routing — нужен profiling и оптимизация bottleneck'ов |

---

> [!TIP]
> **Порядок реализации**: Module 1 (Gateway) → Module 4 (Provider Pool, один провайдер) → Module 2 (Classifier, только rules) → Module 3 (Router, round-robin) → Module 6 (Metrics, SQLite для начала) → Module 5 (Evaluator) → Module 7 (Dashboard) → затем улучшай каждый модуль до Level 2 и Level 3.

---

*Estimated time: 40-80 часов инженерной работы. Не continuous coding, а работа с перерывами на think, experiment, debug.*

*Результат: инструмент, которым ты будешь пользоваться каждый день, который сэкономит тебе деньги и время, и который ты реально понимаешь изнутри.*
