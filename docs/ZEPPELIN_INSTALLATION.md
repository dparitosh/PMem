# Apache Zeppelin installation

Zeppelin 0.12.1 was downloaded to `D:\\DEPO\\runtime\\zeppelin-0.12.1` from Apache and the netinst archive was SHA512 verified. Its Windows environment is configured for the existing Java 21, Spark 4.1.2, Hadoop shim, and PMem virtualenv.

## Current validation

- Spark 4.1.2 and Java 21 are installed and callable.
- The netinst server initializes its interpreters, notebook repository, and Spark settings.
- The netinst distribution does not contain the web UI. Starting it therefore fails with a missing `zeppelin-web-angular` directory. This is expected for netinst, not a PMem defect.
- The full `bin-all` archive download was truncated by the configured network mirror and is not installed. Do not use the incomplete archive.

## Completing the UI installation

Download the complete `zeppelin-0.12.1-bin-all.tgz` from an Apache mirror, verify its published SHA512, extract it to `D:\\DEPO\\runtime`, and replace the netinst directory. Keep the existing `conf\\zeppelin-env.cmd` settings. Start with `bin\\zeppelin.cmd`; the UI should bind to `http://127.0.0.1:8080`.

Zeppelin is an optional operator notebook for Spark jobs. It is not a replacement for PMem APIs, catalog, governance, or graph publication boundaries.
