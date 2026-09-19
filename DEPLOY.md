# 🌐 Руководство по развертыванию ARBITER (Cloud & Public Access)

В проекте настроены все необходимые конфигурации для развертывания вне локального окружения.

---

## Вариант 1: Мгновенный публичный доступ через Cloudflare Tunnel (Рекомендуется для быстрого теста)

Если сервер запущен на вашей машине или сервере, Cloudflare Tunnel мгновенно создает публичный HTTPS URL с поддержкой WebSockets и SSL без выделенного IP и настроек NAT:

```powershell
# 1. Запуск сервера ARBITER
.\.venv\Scripts\uvicorn.exe arbiter.gateway.app:app --host 0.0.0.0 --port 8000

# 2. Запуск туннеля (в отдельном окне)
cloudflared tunnel --url http://localhost:8000
```
В консоли появится ссылка вида `https://<случайное-имя>.trycloudflare.com`. По ней сразу открывается веб-дашборд и доступен API.

---

## Вариант 2: Бесплатный облачный хостинг 24/7 (Render.com)

Render позволяет развернуть ARBITER бесплатно без собственного сервера:

1. Загрузите код в ваш репозиторий на [GitHub](https://github.com/).
2. Перейдите на [dashboard.render.com](https://dashboard.render.com/) и нажмите **New +** ➔ **Blueprint** (или **Web Service**).
3. Выберите ваш репозиторий. Render автоматически обнаружит файл [`render.yaml`](file:///c:/Users/%D0%A1%D1%82%D0%B5%D0%BF%D0%B0%D0%BD%20%D0%BB%D0%BE%D1%85/Desktop/%D0%BD%D0%B5%20%D0%BF%D0%B0%D0%BF%D0%BA%D0%B0/render.yaml).
4. Нажмите **Apply**. Сервер соберется и запустится с постоянным доменом `https://arbiter-xxxx.onrender.com`.

---

## Вариант 3: Облачный хостинг Railway.app

1. Перейдите на [railway.app](https://railway.app/) и выберите **Deploy from GitHub repo**.
2. Railway автоматически прочитает [`Dockerfile`](file:///c:/Users/%D0%A1%D1%82%D0%B5%D0%BF%D0%B0%D0%BD%20%D0%BB%D0%BE%D1%85/Desktop/%D0%BD%D0%B5%20%D0%BF%D0%B0%D0%BF%D0%BA%D0%B0/Dockerfile) или [`Procfile`](file:///c:/Users/%D0%A1%D1%82%D0%B5%D0%BF%D0%B0%D0%BD%20%D0%BB%D0%BE%D1%85/Desktop/%D0%BD%D0%B5%20%D0%BF%D0%B0%D0%BF%D0%BA%D0%B0/Procfile) и развернет контейнер.
3. В настройках сервиса нажмите **Generate Domain**, чтобы получить публичный URL.

---

## Вариант 4: Развертывание на собственном VPS / сервере через Docker Compose

```bash
# Клонирование и запуск
docker compose up -d --build

# Проверка логов
docker compose logs -f
```
Сервис будет доступен по адресу вашего сервера: `http://<IP_СЕРВЕРА>:8000`.
Для привязки домена и SSL рекомендуется настроить Nginx или Traefik.
