# Job Watcher

> Bot que monitorea **7 portales de empleo venezolanos** en **5 estados** y notifica ofertas relevantes por Telegram. Configurado para perfiles tecnicos (Frontend, QA, Soporte, Admin Digital). Corre **gratis en GitHub Actions** cada 3 horas.

## Estado del proyecto

- **Version**: `v0.16.0` (ver [CHANGELOG.md](CHANGELOG.md))
- **7 portales venezolanos**: unmejorempleo, trabajo_org, computrabajo, trabajosdiarios, buscojobs, empleate, mipleo
- **5 estados**: Nueva Esparta, Distrito Capital, Miranda, Carabobo, Zulia
- **4 perfiles profesionales** configurables
- **~2,350 ofertas unicas** por ciclo, en **~2.1 min**
- **164 tests**, 86.86% coverage
- **CI matrix** (Python 3.11 + 3.12) en cada push

## Caracteristicas

- Scraping paralelo (`ThreadPoolExecutor`, 6 workers)
- Cache de ofertas por portal (una sola sesion HTTP por portal)
- Deduplicacion por fingerprint (sha256) + cross-portal (titulo + empresa normalizados)
- Filtros accent-insensitive (keywords, exclusiones, ubicaciones, remoto)
- Filtro de antiguedad configurable por perfil
- Formato enriquecido en Telegram: emoji por perfil, badge remoto, snippet
- Resumen diario si no hay matches (throttle 20h)
- Monitor de scrapers: alerta si un portal cae >50% vs baseline de 7 dias
- Notificacion a Telegram si el cron falla
- Backup de la DB como artifact de GitHub Actions

## Arquitectura

```
config.yaml + profiles.yaml + .env
                |
                v
     pipeline.run_pipeline()
                |
     +----------+----------+
     |          |          |
  Scraping   Monitoreo   (7 portales en paralelo)
     |
     v
  Filtros por perfil (keywords, ubicacion, remoto, antiguedad)
     |
     v
  Deduplicacion (fingerprint + cross-portal normalizado)
     |
     v
  Notificacion Telegram (formato enriquecido)
     |
     v
  Resumen diario (si 0 matches)
```

Ver [docs/architecture.md](docs/architecture.md) para el detalle completo.

## Portales soportados

| Portal | Cobertura | Metodo |
|---|---|---|
| unmejorempleo | Nueva Esparta | HTML |
| trabajo_org | 5 estados | HTML |
| computrabajo | 5 estados | HTML |
| trabajosdiarios | 5 estados | HTML |
| buscojobs | Nueva Esparta (JSON `__NEXT_DATA__`) | HTML+JSON |
| empleate | 5 estados | HTML |
| mipleo | 5 estados | HTML |

## Perfiles activos por defecto

- **Frontend Developer** (React / TypeScript / React Native)
- **QA Engineer / Tester**
- **Soporte Tecnico / IT**
- **Asistente Tecnico / Admin Digital**

Configurables en `config/profiles.yaml` (keywords, exclusiones, ubicaciones, `max_age_days`, portales activos por perfil).

## Requisitos

- Python 3.11+
- Bot de Telegram (token de [@BotFather](https://t.me/BotFather))
- `chat_id` de Telegram (de [@userinfobot](https://t.me/userinfobot))

## Instalacion local

```powershell
git clone https://github.com/axeljimenezdeveloper/job-watcher.git
cd job-watcher
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
# Edita .env con tu TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID
```

## Uso

```powershell
# Ejecutar el pipeline una vez (scrapea, filtra, notifica)
python -m job_watcher

# Correr la suite de tests
pytest

# Calidad de codigo
ruff check src tests
ruff format --check src tests
mypy src tests
```

## Configuracion

### `config/config.yaml`

```yaml
app:
  timezone: "America/Caracas"
  log_level: "INFO"

scraping:
  timeout_seconds: 30
  request_delay_seconds: 2
  estados:
    - nueva-esparta
    - distrito-capital
    - miranda
    - carabobo
    - zulia
```

### `config/profiles.yaml`

Cada perfil define:

- `must_match_any`: keywords que deben aparecer
- `must_not_match`: keywords de exclusion
- `locations_any`: ubicaciones aceptadas
- `local_locations`: ubicaciones locales (no requieren keyword "remoto")
- `remote_keywords`: keywords de trabajo remoto
- `max_age_days`: filtrar ofertas mas antiguas
- `portals`: portales activos para este perfil

### `.env`

```env
TELEGRAM_BOT_TOKEN=tu-token-de-botfather
TELEGRAM_CHAT_ID=tu-chat-id-de-userinfobot
```

## Despliegue

El bot corre **gratis en GitHub Actions** cada 3 horas via `.github/workflows/scrape.yml`.

**Configurar secrets** en GitHub:

1. Ir a `Settings` → `Secrets and variables` → `Actions`
2. Crear `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` con los valores de tu `.env`

La base de datos `data/jobs.db` se persiste entre runs via `actions/cache` con respaldo en `actions/upload-artifact` (90 dias de retencion).

## Anadir un portal nuevo

1. Crear `src/job_watcher/scrapers/<nombre>.py` heredando de `BaseScraper`
2. Implementar `parse(html)` y opcionalmente `run(url)` para paginacion
3. Registrar en `src/job_watcher/scrapers/registry.py`
4. Anadir fixture en `tests/fixtures/<nombre>_listado.html`
5. Escribir `tests/test_<nombre>.py`
6. Activar en `config/profiles.yaml` (`<nombre>: true`)

Ver [docs/architecture.md](docs/architecture.md) para el detalle.

## Versionado

- [Conventional Commits](https://www.conventionalcommits.org/)
- [SemVer](https://semver.org/)
- Tags `v*` disparan release automatica con artefactos
- Ver [CHANGELOG.md](CHANGELOG.md) para el historial completo

## Tests y cobertura

```
164 passed, 86.86% coverage
```

## Documentacion

- [docs/architecture.md](docs/architecture.md) — vision general, flujo de datos, decisiones de diseno
- [CHANGELOG.md](CHANGELOG.md) — historial de versiones

## Licencia

MIT
