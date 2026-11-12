# Arquitectura

## Vision general

```
config.yaml + profiles.yaml + .env
                |
                v
        pipeline.run_pipeline()
                |
                v
    FASE 1: Scraping (paralelo, MAX_WORKERS=6)
    unmejorempleo | computrabajo | empleate
    trabajo_org   | buscojobs    | trabajosdiarios
                |
                v
        offers_by_portal: dict[str, list[JobOffer]]
                |
    +-----------+-----------+
    v           v           v
 Monitor     FASE 2:      FASE 3:
(caidas?)    Filtros x    DB dedup
             perfil       + notificar
    +-----------+-----------+
                |
                v
            Telegram
```

## Modulos

| Modulo | Responsabilidad |
|---|---|
| `config.py` | Carga `config.yaml`, `profiles.yaml`, `.env`. Dataclasses frozen. |
| `models.py` | `JobOffer` (frozen, slots). Fingerprint sha256 para dedup. |
| `db.py` | `JobDatabase`: SQLite thread-safe, WAL. Tablas `jobs`, `scrape_runs`, `summary_log`. |
| `filters.py` | `ProfileFilter`: keywords, exclusiones, ubicaciones, remote, antiguedad. |
| `monitor.py` | `check_and_alert`: alerta si un portal cae >50% vs baseline de 7 dias. |
| `notifier.py` | `TelegramNotifier`: envio a la API Bot con manejo de errores. |
| `pipeline.py` | Orquestador: scrapea en paralelo, filtra, deduplica, notifica. |
| `scrapers/` | `BaseScraper` + 6 implementaciones. `run_multi_estado()` helper. |

## Flujo de datos

1. **Configuracion**: `load_config()` parsea YAML + env -> `Config` dataclass inmutable.
2. **Scraping**: `_scrape_all_portals()` usa `ThreadPoolExecutor(6)` -> cada portal corre `run_multi_estado()` sobre los 5 estados.
3. **Monitoreo**: `_monitor_portals()` compara cada conteo con baseline de 7 dias. Si cae >50%, alerta a Telegram.
4. **Filtrado**: para cada perfil, `filter_offers()` aplica keywords, exclusiones, ubicaciones y antiguedad.
5. **Deduplicacion**: `db.is_new()` (fingerprint) evita repetir entre ciclos. `db.find_recent_duplicate()` evita duplicados cross-portal.
6. **Notificacion**: `notifier.send()` con formato enriquecido (emoji + remoto + snippet).
7. **Resumen diario**: si 0 matches, y no se envio en las ultimas 20h, envia resumen de estado.

## Decisiones de diseno

### Por que cache por portal y no por perfil?
Scrapear 6 portales x 5 estados x 4 perfiles = 120 requests. Scrapear 1 vez y filtrar 4 veces = 30 requests. **4x speedup.**

### Por que ThreadPoolExecutor y no asyncio?
Los scrapers usan `requests` (sync). `ThreadPoolExecutor` es suficiente, no requiere reescribir a `aiohttp`. Ademas, SQLite es sync-friendly con WAL.

### Por que monitor de scrapers?
Si un portal cambia su HTML, sigue corriendo sin error pero devuelve 0 ofertas. **Fallar silenciosamente es peor que fallar con error.** El monitor detecta caidas >50%.

### Por que filtro de antiguedad?
Muchas ofertas viejas siguen listadas. Filtrar <7 dias reduce ruido sin perder ofertas frescas. Configurable por perfil (`max_age_days`).

### Por que dedup cross-portal?
La misma oferta aparece en computrabajo + empleate + unmejorempleo. Sin dedup, el usuario recibe 3 notificaciones identicas. Con dedup: 1.

## Anadir un portal nuevo

1. Crear `src/job_watcher/scrapers/<nombre>.py`:

```python
class MiPortalScraper(BaseScraper):
    portal = "mi_portal"
    BASE_URL = "https://mi-portal.com/"
    ESTADOS = {"nueva-esparta": "empleos/nueva-esparta"}

    def parse(self, html: str) -> list[JobOffer]:
        ...  # implementar
```

2. Registrar en `src/job_watcher/scrapers/registry.py`.
3. Anadir fixture HTML en `tests/fixtures/mi_portal_listado.html`.
4. Escribir `tests/test_mi_portal.py`.
5. Anadir `mi_portal: true` en cada perfil de `config/profiles.yaml`.
6. Ejecutar `pytest` y `python -m job_watcher` para validar.

## Calidad

- `ruff` para lint y format
- `mypy` strict para tipado
- `pre-commit` en cada commit
- CI (matrix 3.11 + 3.12) en cada push
- Coverage minimo 80%
- 144 tests, ~87% coverage
