# DEPO customer demo narratives

These narratives follow the customer-visible Siemens IX sidebar in application
order. Each page has its own folder so screenshots, sample inputs, acceptance
evidence, and customer-specific variants can be added without mixing concerns.

## Presenter preparation

1. Start the backend with `infra/windows/start-depo-services.ps1`.
2. Start the UI with `infra/windows/start-depo-frontend.ps1`.
3. Confirm PostgreSQL and Neo4j are ready; enable Spark only for a Spark demo.
4. Use a non-production dataset and approved demo API keys.
5. Complete each page's readiness checks before presenting it.

## Page order

| Order | Page | Narrative |
| ---: | --- | --- |
| 1 | Home | [home/DEMO.md](home/DEMO.md) |
| 2 | Import | [import/DEMO.md](import/DEMO.md) |
| 3 | Data Flow | [data-flow/DEMO.md](data-flow/DEMO.md) |
| 4 | Ontology Junction | [ontology/DEMO.md](ontology/DEMO.md) |
| 5 | Metadata Registry | [registry/DEMO.md](registry/DEMO.md) |
| 6 | Graph Explorer | [graph/DEMO.md](graph/DEMO.md) |
| 7 | Code Network | [code-audit/DEMO.md](code-audit/DEMO.md) |
| 8 | Modeling | [modeling/DEMO.md](modeling/DEMO.md) |
| 9 | ReqIF | [requirements/DEMO.md](requirements/DEMO.md) |
| 10 | QIF | [qif/DEMO.md](qif/DEMO.md) |
| 11 | Where Used | [whereused/DEMO.md](whereused/DEMO.md) |
| 12 | Recommendations | [quality/DEMO.md](quality/DEMO.md) |
| 13 | Reports | [reports/DEMO.md](reports/DEMO.md) |
| 14 | Admin | [admin/DEMO.md](admin/DEMO.md) |

Do not claim a capability when its readiness condition is not met. Show the
page's explicit unavailable or empty state and explain the dependency required.
