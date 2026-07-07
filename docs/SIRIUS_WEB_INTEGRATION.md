# Sirius Web Integration

DEPO treats modeling as an integration with the actual Eclipse Sirius Web application, not as a custom Graph Explorer page.

## Local Source Folder

The Sirius Web source is cloned here:

```text
external/sirius-web
```

Source repository:

```text
https://github.com/eclipse-sirius/sirius-web.git
```

Windows long-path support was enabled for the clone:

```powershell
git -C external/sirius-web config core.longpaths true
```

## No-Docker Customer Rule

Customer environments that do not allow Docker should not use the Sirius Web Docker Compose quick start. Use the filesystem/source build path instead.

Sirius Web is not a static HTML folder. It is a Spring Boot backend plus React frontend application. Running it without Docker requires:

| Requirement | Version / Note |
| --- | --- |
| Java | Java 21 |
| Maven | Maven 3.6.3 or compatible customer-approved Maven |
| Node.js | 22.16.0 |
| npm | 10.9.2 |
| TurboRepo | Installed through npm or customer-approved package mirror |
| PostgreSQL | Customer-managed PostgreSQL service |
| GitHub package credentials | Required by upstream Sirius Web Maven/npm dependencies unless mirrored internally |

The cloned source is filesystem-based, but the runtime still needs PostgreSQL. Sirius Web's default backend properties point to:

```properties
server.port=8080
spring.datasource.url=jdbc:postgresql://localhost:5438/sirius-web-db
spring.datasource.username=dbuser
spring.datasource.password=dbpwd
```

For a customer VM, override these through environment variables or an external Spring Boot properties file instead of editing upstream files directly.

## No-Docker Build Path

From the Sirius Web source folder:

```powershell
cd external/sirius-web
```

Install/build frontend packages:

```powershell
npm ci
npx turbo run build
```

Copy the built Sirius frontend into the Spring Boot static resources folder. On Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force packages/sirius-web/backend/sirius-web-frontend/src/main/resources/static
Copy-Item -Recurse -Force packages/sirius-web/frontend/sirius-web/dist/* packages/sirius-web/backend/sirius-web-frontend/src/main/resources/static/
```

Build backend without Docker-based tests:

```powershell
mvn clean install -f packages/pom.xml -DskipTests
```

The Spring Boot fat JAR is expected under:

```text
external/sirius-web/packages/sirius-web/backend/sirius-web/target/
```

Run the JAR with customer PostgreSQL settings:

```powershell
java -jar external/sirius-web/packages/sirius-web/backend/sirius-web/target/sirius-web-*.jar `
  --server.port=8080 `
  --spring.datasource.url=jdbc:postgresql://<postgres-host>:<postgres-port>/<database> `
  --spring.datasource.username=<username> `
  --spring.datasource.password=<password> `
  --sirius.components.cors.allowedOriginPatterns=*
```

If customer policy blocks direct internet dependency download, mirror these dependencies internally first:

- Maven artifacts from GitHub Packages referenced by Sirius Web
- npm packages from GitHub Packages and npm registry
- Java, Maven, Node, npm installers

## Configure DEPO Frontend

The DEPO Modeling page reads:

```text
REACT_APP_SIRIUS_WEB_URL=http://localhost:8080
```

If it is not set, DEPO defaults to `http://localhost:8080`.

For another VM/IP, use for example:

```text
REACT_APP_SIRIUS_WEB_URL=http://192.168.1.4:8080
```

Restart the DEPO frontend after changing React environment variables.

## Runtime Responsibility Split

| Area | Owner |
| --- | --- |
| Modeling workbench, explorer, diagrams, forms, validation views | Sirius Web |
| Ontology ingestion, OWL/RDF/TTL, Semantic Bridge | DEPO backend |
| Neo4j graph projection, contextual graph, GraphRAG | DEPO backend |
| PLMXML, STEP, XMI, ReqIF, ArchiMate import pipelines | DEPO import APIs |
| Teamcenter / external assistant API | DEPO chat APIs |

Do not duplicate Sirius Web features inside Graph Explorer. Graph Explorer remains the analysis and traceability graph, not the modeling editor.

## DEPO Modeling Page Behavior

The DEPO Modeling page provides:

- Open Sirius Web button
- Reload embedded frame button
- URL/config status strip
- Embedded Sirius Web frame when browser security headers allow it

If a customer deployment blocks iframe embedding, users should click `Open Sirius Web` and use the Sirius app in its own tab.

## Recommended Bridge Layer

Keep Sirius Web independent and add a small bridge instead of mixing Sirius internals into DEPO Graph Explorer:

```text
DEPO backend API <-> Sirius Web REST/GraphQL extension <-> Sirius model repository
```

Initial bridge endpoints should cover:

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v1/modeling/sirius/context` | Return DEPO ontology/project context for Sirius launch |
| `POST /api/v1/modeling/sirius/export` | Export selected Sirius model metadata into DEPO ontology/Neo4j pipeline |
| `POST /api/v1/modeling/sirius/import` | Send DEPO semantic model package into Sirius-compatible modeling input |
| `GET /api/v1/modeling/sirius/health` | Show Sirius availability in Admin |

## References

- Sirius Web repository: https://github.com/eclipse-sirius/sirius-web
- Sirius Web documentation: https://eclipse-sirius.github.io/sirius-web/sirius-web/index.html
- Sirius Web features: https://eclipse-sirius.github.io/sirius-web/sirius-web/user-manual/features/features.html
