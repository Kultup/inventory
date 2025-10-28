# REST API Документація

## Огляд

Система інвентаризації обладнання надає RESTful API для інтеграції з зовнішніми системами.

**Base URL:** `http://your-domain.com/api/v1`

**Версія:** 1.0

## Автентифікація

API використовує автентифікацію через API ключі в заголовку запиту.

```http
X-API-Key: your-api-key
```

**Примітка:** В поточній версії використовується username користувача як API ключ. Для production рекомендується впровадити JWT токени.

## Endpoints

### Пристрої

#### GET /devices

Отримати список пристроїв з пагінацією та фільтрацією.

**Параметри запиту:**

| Параметр | Тип | Опис |
|----------|-----|------|
| page | integer | Номер сторінки (за замовчуванням: 1) |
| per_page | integer | Кількість записів на сторінці (макс: 100) |
| city_id | integer | Фільтр за містом (тільки для адміністраторів) |
| type | string | Фільтр за типом пристрою |
| status | string | Фільтр за статусом |
| search | string | Пошук по назві, серійному номеру, інвентарному номеру |

**Приклад запиту:**

```bash
curl -X GET "http://localhost:5000/api/v1/devices?page=1&per_page=20&status=В%20роботі" \
  -H "X-API-Key: admin"
```

**Відповідь (200 OK):**

```json
{
  "devices": [
    {
      "id": 1,
      "name": "Комп'ютер Dell",
      "type": "Комп'ютер",
      "serial_number": "SN123456",
      "inventory_number": "2025-0001",
      "location": "Офіс 201",
      "status": "В роботі",
      "notes": "Примітки",
      "city_id": 1,
      "city_name": "Київ",
      "created_at": "2025-01-15T10:30:00",
      "last_maintenance": "2024-12-01",
      "next_maintenance": "2025-12-01"
    }
  ],
  "total": 100,
  "pages": 5,
  "current_page": 1,
  "per_page": 20
}
```

---

#### GET /devices/:id

Отримати інформацію про конкретний пристрій.

**Параметри URL:**

| Параметр | Тип | Опис |
|----------|-----|------|
| id | integer | ID пристрою |

**Приклад запиту:**

```bash
curl -X GET "http://localhost:5000/api/v1/devices/1" \
  -H "X-API-Key: admin"
```

**Відповідь (200 OK):**

```json
{
  "id": 1,
  "name": "Комп'ютер Dell",
  "type": "Комп'ютер",
  "serial_number": "SN123456",
  "inventory_number": "2025-0001",
  "location": "Офіс 201",
  "status": "В роботі",
  "notes": "Примітки",
  "city_id": 1,
  "city_name": "Київ",
  "created_at": "2025-01-15T10:30:00",
  "last_maintenance": "2024-12-01",
  "next_maintenance": "2025-12-01",
  "maintenance_interval": 365
}
```

**Помилки:**
- `404 Not Found` - Пристрій не знайдено
- `403 Forbidden` - Доступ заборонено

---

#### POST /devices

Створити новий пристрій.

**Тіло запиту:**

| Поле | Тип | Обов'язкове | Опис |
|------|-----|-------------|------|
| name | string | Так | Назва пристрою |
| type | string | Так | Тип пристрою |
| serial_number | string | Так | Серійний номер (унікальний) |
| location | string | Ні | Місце розташування |
| status | string | Ні | Статус (за замовчуванням: "В роботі") |
| notes | string | Ні | Примітки |
| city_id | integer | Ні | ID міста (тільки для адміністраторів) |
| maintenance_interval | integer | Ні | Інтервал обслуговування в днях (за замовчуванням: 365) |

**Приклад запиту:**

```bash
curl -X POST "http://localhost:5000/api/v1/devices" \
  -H "X-API-Key: admin" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Принтер HP LaserJet",
    "type": "Принтер",
    "serial_number": "HP123456789",
    "location": "Офіс 305",
    "status": "В роботі",
    "notes": "Новий принтер"
  }'
```

**Відповідь (201 Created):**

```json
{
  "id": 42,
  "inventory_number": "2025-0042",
  "message": "Device created successfully"
}
```

**Помилки:**
- `400 Bad Request` - Відсутні обов'язкові поля
- `409 Conflict` - Пристрій з таким серійним номером вже існує

---

#### PUT /devices/:id

Оновити пристрій.

**Параметри URL:**

| Параметр | Тип | Опис |
|----------|-----|------|
| id | integer | ID пристрою |

**Тіло запиту:**

Всі поля опціональні. Оновлюються тільки передані поля.

| Поле | Тип | Опис |
|------|-----|------|
| name | string | Назва пристрою |
| type | string | Тип пристрою |
| location | string | Місце розташування |
| status | string | Статус |
| notes | string | Примітки |
| maintenance_interval | integer | Інтервал обслуговування |
| last_maintenance | string (ISO date) | Дата останнього обслуговування |

**Приклад запиту:**

```bash
curl -X PUT "http://localhost:5000/api/v1/devices/42" \
  -H "X-API-Key: admin" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "На ремонті",
    "notes": "Застряг папір"
  }'
```

**Відповідь (200 OK):**

```json
{
  "message": "Device updated successfully"
}
```

**Помилки:**
- `400 Bad Request` - Немає даних для оновлення
- `403 Forbidden` - Доступ заборонено
- `404 Not Found` - Пристрій не знайдено

---

#### DELETE /devices/:id

Видалити пристрій.

**Параметри URL:**

| Параметр | Тип | Опис |
|----------|-----|------|
| id | integer | ID пристрою |

**Приклад запиту:**

```bash
curl -X DELETE "http://localhost:5000/api/v1/devices/42" \
  -H "X-API-Key: admin"
```

**Відповідь (200 OK):**

```json
{
  "message": "Device deleted successfully"
}
```

**Помилки:**
- `403 Forbidden` - Доступ заборонено
- `404 Not Found` - Пристрій не знайдено

---

### Міста

#### GET /cities

Отримати список міст.

**Приклад запиту:**

```bash
curl -X GET "http://localhost:5000/api/v1/cities" \
  -H "X-API-Key: admin"
```

**Відповідь (200 OK):**

```json
{
  "cities": [
    {
      "id": 1,
      "name": "Київ",
      "created_at": "2025-01-01T00:00:00"
    },
    {
      "id": 2,
      "name": "Львів",
      "created_at": "2025-01-02T00:00:00"
    }
  ]
}
```

---

### Статистика

#### GET /stats

Отримати загальну статистику по пристроях.

**Приклад запиту:**

```bash
curl -X GET "http://localhost:5000/api/v1/stats" \
  -H "X-API-Key: admin"
```

**Відповідь (200 OK):**

```json
{
  "total_devices": 150,
  "active_devices": 120,
  "repair_devices": 20,
  "decommissioned_devices": 10
}
```

**Примітка:** Користувачі, які не є адміністраторами, бачать статистику тільки по своєму місту.

---

## Коди відповідей

| Код | Опис |
|-----|------|
| 200 OK | Успішний запит |
| 201 Created | Ресурс створено |
| 400 Bad Request | Некоректний запит |
| 401 Unauthorized | Відсутній або неправильний API ключ |
| 403 Forbidden | Доступ заборонено |
| 404 Not Found | Ресурс не знайдено |
| 409 Conflict | Конфлікт даних (напр., дублікат) |
| 500 Internal Server Error | Внутрішня помилка сервера |

---

## Обмеження та рекомендації

### Rate Limiting

В поточній версії rate limiting не впроваджено. Рекомендується для production.

### Пагінація

- Максимальна кількість записів на сторінці: 100
- За замовчуванням: 20 записів

### Права доступу

- **Адміністратори:** Доступ до всіх пристроїв та міст
- **Звичайні користувачі:** Доступ тільки до пристроїв свого міста

---

## Приклади використання

### Python (requests)

```python
import requests

API_KEY = 'admin'
BASE_URL = 'http://localhost:5000/api/v1'

headers = {
    'X-API-Key': API_KEY,
    'Content-Type': 'application/json'
}

# Отримати список пристроїв
response = requests.get(f'{BASE_URL}/devices', headers=headers)
devices = response.json()

# Створити пристрій
new_device = {
    'name': 'Ноутбук Lenovo',
    'type': 'Ноутбук',
    'serial_number': 'LN987654321',
    'location': 'Офіс 101'
}

response = requests.post(
    f'{BASE_URL}/devices', 
    json=new_device, 
    headers=headers
)
result = response.json()
print(f"Created device with ID: {result['id']}")
```

### JavaScript (Fetch API)

```javascript
const API_KEY = 'admin';
const BASE_URL = 'http://localhost:5000/api/v1';

const headers = {
    'X-API-Key': API_KEY,
    'Content-Type': 'application/json'
};

// Отримати пристрій
fetch(`${BASE_URL}/devices/1`, { headers })
    .then(response => response.json())
    .then(device => console.log(device));

// Оновити пристрій
const updateData = {
    status: 'На ремонті',
    notes: 'Потребує діагностики'
};

fetch(`${BASE_URL}/devices/1`, {
    method: 'PUT',
    headers: headers,
    body: JSON.stringify(updateData)
})
.then(response => response.json())
.then(result => console.log(result));
```

---

## Планується в майбутніх версіях

- JWT токени для автентифікації
- Rate limiting
- Webhooks для подій
- Фільтрація за датою обслуговування
- Пошук за QR кодами
- Batch операції
- GraphQL endpoint

---

## Підтримка

При виникненні проблем перевірте:
1. Правильність API ключа
2. Формат даних (Content-Type: application/json)
3. Права доступу користувача
4. Логи сервера для деталей помилок

