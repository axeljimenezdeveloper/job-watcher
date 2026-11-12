# Job Watcher

Bot que monitorea portales de empleo venezolanos y notifica ofertas relevantes por Telegram. Configurado para perfiles tecnicos (Frontend, QA, Soporte, Admin Digital) en 5 estados de Venezuela.

## Arquitectura

```
Scrapers (6 portales, paralelo)
        |
        v
  Filtros por perfil (keywords, ubicacion, remoto, antiguedad)
        |
        v
  Deduplicacion SQLite (fingerprint + cross-portal)
        |
        v
  Notificacion Telegram (formato enriquecido)
        |
        v
  Monitor de scrapers + resumen diario
```

## Portales

| Portal | Cobertura | Metodo |
|---|---|---|
| unmejorempleo | Nueva Esparta | HTML |
| trabajo_org | 5 estados | HTML |
| computrabajo | 5 estados | HTML |
| trabajosdiarios | 5 estados | HTML |
| buscojobs | Nueva Esparta (JSON `__NEXT_DATA__`) | HTML+JSON |
| empleate | 5 estados | HTML |

## Perfiles activos

- Frontend Developer (React / TypeScript / React Native)
- QA Engineer / Tester
- Soporte Tecnico / IT
- Asistente Tecnico / Admin Digital

Configuracion en `config/profiles.yaml`.

## Requisitos

- Python 3.11
- Bot de Telegram (token de @BotFather) y `chat_id` (de @userinfobot)

## Instalacion local

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
# Edita .env con tu token y chat_id
```

## Uso

```powershell
# Ejecutar el pipeline una vez
python -m job_watcher

# Correr la suite de tests
pytest

# Calidad de codigo
ruff check src tests
mypy src tests
```

## Despliegue

El bot corre **gratis en GitHub Actions** cada 3 horas (`scrape.yml`).

Los secretos `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` se configuran en:
`https://github.com/<usuario>/job-watcher/settings/secrets/actions`

## Estado del proyecto

- 6 portales venezolanos
- 5 estados (Nueva Esparta, Distrito Capital, Miranda, Carabobo, Zulia)
- 4 perfiles profesionales
- ~1,900 ofertas por ciclo en ~1.8 min
- 144 tests, 87% coverage
- Monitoreo de scrapers (alerta si cae >50%)
- Filtro de antiguedad (<7 dias)
- Resumen diario si no hay matches
- Deduplicacion cross-portal

Ver [CHANGELOG.md](CHANGELOG.md) para el historial de versiones.

## Licencia

MIT
