# lms_agent

Frappe-приложение платформы **MCP-LMS**: хранит директивы уроков, учебные
сессии и результаты серверного квиза, отдаёт их наружу документированным
REST-контрактом.

Дополняет [Frappe Learning](https://github.com/frappe/lms), не заменяя его:
итоги занятий пишутся в стандартные `LMS Course Progress` и
`LMS Quiz Submission`, поэтому прогресс, набранный через агента, виден в
браузерном интерфейсе.

## Лицензия и граница

Приложение распространяется под **AGPL-3.0** — оно загружается в один процесс
с Frappe Learning и работает с его DocType, а значит считается совместным
произведением.

Закрытая часть платформы — MCP-сервис — живёт отдельным процессом и общается с
этим приложением **только по HTTP**, через документированный контракт общего
назначения. Что именно можно писать здесь, а что нельзя, — в
[CONTRIBUTING.md](CONTRIBUTING.md); это не стилистика, а условие, на котором
держится граница.

## Состав

| Что | Состояние |
|---|---|
| `Agent Lesson Directive` — директива урока | готово, [#6](https://github.com/NikoMusaev/lms-mcp/issues/6) |
| `Agent Learning Session`, `Agent Session Event` — занятия и журнал | готово, [#7](https://github.com/NikoMusaev/lms-mcp/issues/7) |
| Нормализатор контента уроков | готово, [#8](https://github.com/NikoMusaev/lms-mcp/issues/8) |
| Организации, членство, назначение курсов | готово, [#9](https://github.com/NikoMusaev/lms-mcp/issues/9) |
| Изоляция организаций | готово, [#10](https://github.com/NikoMusaev/lms-mcp/issues/10) |
| Пошаговый серверный квиз | готово, [#11](https://github.com/NikoMusaev/lms-mcp/issues/11) |
| Whitelisted-методы контракта | готово, [#12](https://github.com/NikoMusaev/lms-mcp/issues/12) |

Занятия закрываются по бездействию фоновой задачей раз в час; порог задаётся в
`Agent Learning Settings`, по умолчанию 6 часов.
На стенде для этого нужен включённый планировщик: у нового сайта он выключен,
`bench --site $SITE_NAME enable-scheduler`.

## Разработка

Стенд поднимается из [`lms-deploy`](https://github.com/NikoMusaev/lms-deploy).
Приложение монтируется в контейнеры с хоста, поэтому правки видны без
пересборки образа:

```bash
docker compose up -d                      # compose.yaml + compose.override.yaml
docker compose exec backend bench --site lms.localhost install-app lms_agent
docker compose exec backend bench --site lms.localhost migrate     # после правок DocType
docker compose exec backend bench --site lms.localhost run-tests --app lms_agent
```

## Видимость репозитория

Репозиторий пока приватный. AGPL требует предлагать исходники тем, кто
пользуется программой **по сети** (ст. 13) — обязательство возникает в момент
развёртывания платформы наружу, не раньше. К этому моменту репозиторий
открывается, а в подвале интерфейса и в описании MCP-сервера появляется ссылка
на него.
