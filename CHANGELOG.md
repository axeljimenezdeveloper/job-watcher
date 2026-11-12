# Changelog

Todas las versiones notables del proyecto. Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y [SemVer](https://semver.org/lang/es/).

## [Unreleased]

## [0.13.0] - 2026-11-12

### Added
- Deduplicacion cross-portal (misma oferta en 2 portales -> 1 sola notificacion)
- Notificacion a Telegram si el cron falla
- Upload/restore de `jobs.db` como artifact (respaldo del cache)

### Changed
- Log de `_apply_profile` incluye `dupes=N`

## [0.12.0] - 2026-11-12

### Added
- Filtro de antiguedad: solo ofertas < 7 dias (`max_age_days` en perfil)
- Resumen diario a Telegram si no hay matches (throttle de 20h)
- Formato enriquecido del mensaje: emoji por perfil, badge Remoto, snippet de 200 chars

### Changed
- `MAX_WORKERS` 3 -> 6 (todos los portales en paralelo)
- Tiempo por ciclo: 2.67 min -> 1.84 min

## [0.11.0] - 2026-11-12

### Changed
- Paralelizacion con `ThreadPoolExecutor` (5.67 min -> 2.67 min, 2.1x)
- `JobDatabase` thread-safe (`threading.Lock`, `check_same_thread=False`, WAL)

## [0.10.0] - 2026-11-12

### Added
- Monitor de scrapers: alerta a Telegram si un portal cae >50% vs baseline de 7 dias
- Tabla `scrape_runs` para historial de conteos por portal

## [0.9.0] - 2026-11-12

### Added
- Scraper de empleate.com (6 portales total)

## [0.8.0] - 2026-11-12

### Changed
- Cache de scraping por portal: 20 min -> 4.3 min (4.6x)
- Multi-estado (5 estados)

### Added
- Filtro remoto: ofertas fuera de NE solo si mencionan "remoto"

## [0.7.0] - 2026-11-12

### Added
- Scraper de buscojobs con filtro geografico 3 capas
- 4 perfiles profesionales (Frontend, QA, Soporte, Admin)

## [0.6.0] - 2026-11-12

### Added
- Scraper de trabajosdiarios (4 portales total)

## [0.5.0] - 2026-11-12

### Added
- Scraper de computrabajo (3 portales total)

## [0.4.0] - 2026-11-12

### Added
- Scraper de trabajo.org (2 portales total)

## [0.3.0] - 2026-11-12

### Added
- Cron en GitHub Actions cada 3 horas
- Cache de `jobs.db` entre runs
- Secrets `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`

## [0.2.0] - 2026-11-12

### Added
- Scraper de unmejorempleo (primer portal real)
- Filtros por perfil (accent-insensitive)
- Pipeline scraper -> filter -> db -> notifier
- SQLite con deduplicacion por fingerprint

## [0.1.0] - 2026-11-12

### Added
- Estructura inicial del proyecto
- Config loader (YAML + env)
- Telegram notifier
- Entrypoint minimo
