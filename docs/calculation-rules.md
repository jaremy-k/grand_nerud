# Правила расчёта сделок — описание для клиента

Документ описывает API и формат данных для работы с правилами расчёта сделок в CRM.

**Базовый URL:** `/calculation-rules`  
**Авторизация:** `Authorization: Bearer <token>`

---

## Обзор

Правила расчёта определяют, как из данных сделки вычисляются поля: маржа, НДС, доход менеджера и т.д.

Каждый набор правил содержит:

- **inputs** — какие переменные доступны в формулах (из сделки, конфига, профиля пользователя)
- **formulas** — формулы вычисления (словарь `имя → выражение`)
- **metadata** — подписи и описания для UI (не влияют на расчёт)

Порядок формул в запросе **не важен** — сервер сам выстраивает зависимости.

---

## Что изменилось (миграция с предыдущей версии)

| Было | Стало |
|------|-------|
| `fields: [{ name, expression, store, label }]` | `schema: { inputs, formulas, metadata }` |
| `store: true/false` | `snapshot: true` — только для полей, которые нужно сохранить в сделке |
| `storedNdsPercent` в формулах | Не нужен — используйте `ndsPercent` со `snapshot: true` |
| Вычисляемые поля писались в БД сделки | В БД сохраняются только **snapshot**-поля; остальное считается при чтении |

---

## Структура `schema`

```json
{
  "inputs": {
    "deal": ["quantity", "amountSalesUnit", "amountPurchaseUnit"],
    "config": ["ndsPercentConfig", "cashPaymentMethod", "nonCashPaymentMethod"],
    "user": ["managerShare"]
  },
  "formulas": {
    "amountSalesTotal": {
      "expr": "amountSalesUnit * quantity"
    },
    "ndsPercent": {
      "expr": "ndsPercentConfig if paymentMethod == nonCashPaymentMethod else 0",
      "snapshot": true
    },
    "companyProfit": {
      "expr": "amountSalesTotal - amountPurchaseTotal - amountDelivery - sumExpenses(addExpenses)"
    }
  },
  "metadata": {
    "companyProfit": {
      "label": "Маржа",
      "description": "Прибыль компании по сделке",
      "group": "profit"
    }
  }
}
```

### `inputs`

| Группа | Источник | Примеры |
|--------|----------|---------|
| `deal` | Поля сделки (ввод пользователя) | `quantity`, `amountSalesUnit`, `paymentMethod`, `addExpenses` |
| `config` | Настройки калькулятора | `ndsPercentConfig`, `cashPaymentMethod` |
| `user` | Профиль менеджера | `managerShare` |

Список `inputs` используется для валидации: формула не может ссылаться на переменную, которой нет в `inputs` или в других формулах.

### `formulas`

Каждая формула — объект с полями:

| Поле | Тип | Обязательное | Описание |
|------|-----|--------------|----------|
| `expr` | string | да | Выражение на DSL (до 2000 символов) |
| `snapshot` | boolean | нет (default: `false`) | Сохранять значение в сделке при создании |

**`snapshot: true`** — поле фиксируется в сделке при первом расчёте и **не пересчитывается** при последующих обновлениях.  
Используется для историчности (например, ставка НДС на момент создания сделки).

### `metadata`

Опциональные подписи для UI. Ключ — имя формулы.

| Поле | Описание |
|------|----------|
| `label` | Отображаемое название |
| `description` | Подсказка |
| `group` | Группа в интерфейсе (`profit`, `totals` и т.д.) |

---

## Как работает расчёт сделки

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Ввод сделки    │     │  Правила (schema) │     │  Ответ API      │
│  quantity,      │ ──► │  formulas +       │ ──► │  companyProfit, │
│  amountSales... │     │  snapshot-поля    │     │  ndsAmount, ... │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

1. **Создание сделки** — применяется активный набор правил, вычисляются все формулы. Поля с `snapshot: true` сохраняются в документ сделки. Также сохраняются `calculationRuleId` и `calculationRuleVersion`.

2. **Чтение сделки** — все формулы пересчитываются заново, **кроме** snapshot-полей (берётся значение из сделки).

3. **Обновление сделки** — `calculationRuleId` **не меняется** (сделка остаётся на правилах, с которыми была создана). Snapshot-поля не пересчитываются.

### Что хранится в сделке

| Поле | Описание |
|------|----------|
| Ввод пользователя | `quantity`, `amountSalesUnit`, `paymentMethod`, ... |
| Snapshot | `ndsPercent` (если в правилах `snapshot: true`) |
| Привязка к правилам | `calculationRuleId`, `calculationRuleVersion` |

Вычисляемые поля (`companyProfit`, `amountSalesTotal`, `ndsAmount` и т.д.) **не хранятся** в БД — они приходят в ответе API при каждом чтении.

---

## DSL — язык формул

### Синтаксис

Python-подобные выражения:

- Арифметика: `+`, `-`, `*`, `/`, `**`
- Сравнения: `==`, `!=`, `<`, `>`, `<=`, `>=`
- Логика: `and`, `or`, `not`
- Условие: `значение_если_да if условие else значение_если_нет`

### Примеры

```
amountSalesUnit * quantity
```

```
ndsPercentConfig if paymentMethod == nonCashPaymentMethod else 0
```

```
(amountSalesTotal / (1 + ndsPercent)) * ndsPercent if ndsPercent else 0
```

### Переменные (из сделки)

| Переменная | Описание |
|------------|----------|
| `quantity` | Количество |
| `amountPurchaseUnit` | Цена закупки за единицу |
| `amountSalesUnit` | Цена клиента за единицу |
| `amountDelivery` | Стоимость доставки |
| `paymentMethod` | Способ оплаты |
| `addExpenses` | Список доп. расходов |
| `deliveredQuantity` | Список доставок |

### Переменные (из конфига)

| Переменная | Описание |
|------------|----------|
| `ndsPercentConfig` | Текущая ставка НДС |
| `defaultManagerShare` | Дефолтная доля менеджера |
| `cashPaymentMethod` | Строка «наличный расчёт» |
| `nonCashPaymentMethod` | Строка «безналичный расчёт» |

### Переменные (из профиля)

| Переменная | Описание |
|------------|----------|
| `managerShare` | Доля менеджера |

### Функции

| Функция | Описание |
|---------|----------|
| `sumExpenses(addExpenses)` | Сумма доп. расходов |
| `sumDeliveredQuantity(deliveredQuantity)` | Сумма доставленных объёмов |
| `sumDeliveredPurchase(deliveredQuantity, amountPurchaseUnit)` | Сумма закупки по доставленным партиям |
| `deliveryShare(totalDeliveredQuantity, quantity)` | Доля доставленного объёма |
| `coalesce(a, b, ...)` | Первое не-`null` значение |
| `abs(x)`, `min(a, b)`, `max(a, b)`, `round(x)` | Математические функции |

Актуальный список: `GET /calculation-rules/dsl-docs`.

---

## API-эндпоинты

### Справка по DSL

```
GET /calculation-rules/dsl-docs
```

Доступ: пользователь с правом просмотра формул.

**Ответ:**

```json
{
  "variables": [{ "name": "quantity", "description": "Количество" }],
  "functions": [{ "name": "sumExpenses(addExpenses)", "description": "..." }],
  "syntax": ["Python-подобные выражения: +, -, *, /, ..."]
}
```

---

### Активный набор правил

```
GET /calculation-rules/active
```

Возвращает текущий активный набор правил.

---

### Получить набор по ID

```
GET /calculation-rules/{rule_id}
```

---

### Список всех наборов (админ)

```
GET /calculation-rules
```

---

### Создать набор (админ)

```
POST /calculation-rules
```

**Тело запроса:**

```json
{
  "name": "Стандартный расчёт сделки",
  "isActive": false,
  "schema": {
    "inputs": { "deal": ["quantity"], "config": [], "user": [] },
    "formulas": {
      "amountSalesTotal": { "expr": "amountSalesUnit * quantity" }
    },
    "metadata": {}
  }
}
```

---

### Обновить набор (админ)

```
PATCH /calculation-rules/{rule_id}
```

Можно передать `name`, `schema`, `isActive` — только изменяемые поля.

---

### Активировать набор (админ)

```
POST /calculation-rules/{rule_id}/activate
```

Деактивирует предыдущий активный набор и делает указанный активным.  
**Новые сделки** будут использовать этот набор. Существующие сделки остаются на своём `calculationRuleId`.

---

### Валидация формул (админ)

```
POST /calculation-rules/validate
```

**Тело:** объект `schema` (без обёртки).

**Ответ:**

```json
{
  "valid": true,
  "errors": []
}
```

При ошибках:

```json
{
  "valid": false,
  "errors": [
    "Формула #3 (companyProfit): неизвестные переменные: unknownVar",
    "Формула #5 (ndsAmount): Деление на ноль"
  ]
}
```

Рекомендуется вызывать перед сохранением в UI.

---

### Тестовый прогон (админ)

```
POST /calculation-rules/test
```

**Тело:**

```json
{
  "schema": { "...": "..." },
  "context": null
}
```

`context` — опциональный тестовый контекст. Если не передан, используются демо-данные.

**Ответ:**

```json
{
  "results": {
    "amountSalesTotal": 2000,
    "companyProfit": 300,
    "ndsPercent": 0.22
  },
  "errors": []
}
```

Удобно для preview в редакторе правил: показать промежуточные значения всех формул.

---

## Превью сделки (без сохранения)

```
POST /deals/preview
```

Считает поля по **активному** набору правил без создания сделки.

**Тело:**

```json
{
  "quantity": 10,
  "amountPurchaseUnit": 100,
  "amountSalesUnit": 200,
  "amountDelivery": 500,
  "paymentMethod": "безналичный расчет",
  "addExpenses": [{ "name": "fee", "amount": 200 }],
  "deliveredQuantity": []
}
```

**Ответ:**

```json
{
  "amountSalesTotal": 2000,
  "amountPurchaseTotal": 1000,
  "companyProfit": 300,
  "managerProfit": 30,
  "ndsPercent": 0.22,
  "taxAmount": 360.66,
  "totalAmount": 2000,
  "managerShare": 0.1,
  "actualCompanyProfit": 0,
  "actualAmountSalesTotal": 0,
  "actualAmountPurchaseTotal": 0,
  "totalDeliveredQuantity": 0
}
```

---

## Стандартный набор правил

При первом запуске сервер создаёт набор **«Стандартный расчёт сделки»** со следующими формулами:

| Формула | Snapshot | Описание |
|---------|----------|----------|
| `ndsPercent` | да | Ставка НДС |
| `amountSalesTotal` | нет | Сумма от клиента |
| `amountPurchaseTotal` | нет | Сумма закупки |
| `ndsAmount` | нет | Сумма НДС |
| `companyProfit` | нет | Маржа |
| `managerProfit` | нет | Доход менеджера |
| `totalAmount` | нет | Итоговая сумма |
| `totalDeliveredQuantity` | нет | Доставлено (объём) |
| `actualAmountSalesTotal` | нет | Факт. сумма от клиента |
| `actualAmountPurchaseTotal` | нет | Факт. сумма закупки |
| `actualCompanyProfit` | нет | Фактическая прибыль |

Получить актуальную схему: `GET /calculation-rules/active`.

---

## Рекомендации для UI

### Редактор правил

1. Загрузить `GET /calculation-rules/dsl-docs` — подсказки автодополнения.
2. Редактировать `schema.formulas` как словарь (ключ = имя поля).
3. Перед сохранением: `POST /calculation-rules/validate`.
4. Кнопка «Проверить»: `POST /calculation-rules/test` — показать таблицу `results`.
5. `metadata.label` — подпись в таблице, `metadata.group` — группировка.

### Отображение сделки

- Все вычисляемые поля приходят в ответе `GET /deals/{id}` — отдельный запрос к правилам не нужен.
- `ndsPercent` в сделке — зафиксированное значение (не меняется при смене глобальной ставки НДС).

### Создание / редактирование сделки

- При вводе данных можно вызывать `POST /deals/preview` для live-расчёта.
- Не отправляйте вычисляемые поля (`companyProfit` и т.д.) в `POST /deals` — сервер их игнорирует и считает сам.

---

## Ошибки

| Код | Ситуация |
|-----|----------|
| `400` | Ошибка валидации формул, синтаксис DSL |
| `403` | Нет прав (админ-эндпоинты) |
| `404` | Набор правил не найден / нет активного набора |

Типичные ошибки валидации:

- `неизвестные переменные: foo` — переменная не в `inputs` и не в других формулах
- `Циклическая зависимость между формулами` — формулы ссылаются друг на друга по кругу
- `Синтаксическая ошибка` — невалидное выражение
- `Деление на ноль` — ошибка при тестовом прогоне

---

## Права доступа

| Эндпоинт | Кто может |
|----------|-----------|
| `GET /dsl-docs`, `GET /active`, `GET /{id}` | Пользователь с доступом к формулам |
| `POST`, `PATCH`, `/validate`, `/test`, `/activate` | Администратор |
