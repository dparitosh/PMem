# DEPO installation and release guide

This is the single installation guide for the DEPO frontend, backend, PostgreSQL,
Neo4j, Spark and PySpark. Run commands from the repository root on Windows.

## 1. Provision the customer dependencies

### 1.1 Install PostgreSQL 16

PostgreSQL is required. For a new Windows machine, download the supported
PostgreSQL 16 x64 installer from the [official PostgreSQL Windows download
page](https://www.postgresql.org/download/windows/). The installer is provided
by EDB and includes the database server and `psql` command-line tools. During
the installer screens:

1. Select **PostgreSQL Server** and **Command Line Tools**. pgAdmin is optional.
2. Keep the displayed data directory unless the customer storage policy assigns
   a dedicated data volume.
3. Choose and record the Windows service name shown by the installer.
4. Set a PostgreSQL administrator password. The installer starts the Windows
   service when it finishes.

Open a new PowerShell window and confirm the tools and service are available:

```powershell
$pgBin = 'C:\Program Files\PostgreSQL\16\bin'
& "$pgBin\psql.exe" --version
Get-Service | Where-Object DisplayName -like '*PostgreSQL*' | Format-Table Status, Name, DisplayName
```

If the service is stopped, start the exact `Name` returned above:

```powershell
Start-Service -Name 'postgresql-x64-16'
```

Record that exact service name. You will set
`DEPO_POSTGRES_MODE=service` and `DEPO_POSTGRES_SERVICE_NAME=<that-name>` in
the root `.env.local` in section 2.1, which allows the lifecycle launcher to
start and check the local database. For a managed or remote PostgreSQL server,
keep `DEPO_POSTGRES_MODE=external` and leave the service name blank.

Create a database, a least-privilege application login, and its schema. The
second command prompts securely for the application password instead of writing
it into PowerShell history. Replace only the server administrator account when
it differs from `postgres`.

```powershell
& "$pgBin\psql.exe" -U postgres -h 127.0.0.1 -c 'CREATE ROLE depo_app LOGIN;'
& "$pgBin\psql.exe" -U postgres -h 127.0.0.1 -c '\password depo_app'
& "$pgBin\psql.exe" -U postgres -h 127.0.0.1 -c 'CREATE DATABASE depo OWNER depo_app;'
& "$pgBin\psql.exe" -U postgres -h 127.0.0.1 -d depo -c 'CREATE SCHEMA semantic AUTHORIZATION depo_app;'
```

In the root `.env.local` created in section 2, set
`DEPO_DATABASE_URL=postgresql://depo_app:URL_ENCODED_PASSWORD@127.0.0.1:5432/depo?sslmode=disable`
for this local setup. For a managed or customer database, ask the DBA to create
the equivalent login, database and schema; use `sslmode=verify-full` and the
customer CA certificate. If the customer has explicitly approved a private,
isolated non-TLS network, use `sslmode=disable` instead. Never paste a real
password into PowerShell history or source control.

If PostgreSQL is hosted on another VM, do **not** install PostgreSQL or set a
Windows PostgreSQL service name on the DEPO application VM. Ask the DBA to
create the database, role, and `semantic` schema on the database VM, permit the
application VM's private IP on port `5432`, and provide the CA certificate.
Configure the application VM as follows:

```powershell
# Run from the DEPO repository root and edit the existing keys in this file.
notepad .env.local
```

The resulting entries must be exactly one line each (replace the placeholders
with DBA-approved values):

```text
DEPO_POSTGRES_MODE=external
DEPO_POSTGRES_SERVICE_NAME=
DEPO_POSTGRES_BIN_DIR=
DEPO_POSTGRES_DATA_DIR=
DEPO_DATABASE_SCHEMA=semantic
DEPO_POSTGRES_CONNECT_TIMEOUT_SECONDS=10
DEPO_DATABASE_URL=postgresql://depo_app:URL_ENCODED_PASSWORD@postgres-db.internal.example:5432/depo?sslmode=disable
```

Use `sslmode=verify-full` and the DBA-provided CA certificate when TLS is
required. With an approved private non-TLS network, keep `sslmode=disable` and
set pgAdmin and the ODBC DSN to **SSL mode: Disable** as well.

Edit existing keys in place if they already exist; do not append duplicate
keys. In external mode the Windows lifecycle scripts skip `Start-Service`,
`pg_ctl`, and local PostgreSQL paths. They connect to the remote database only
when schema initialization and service readiness checks run.

### 1.1.1 Test the remote PostgreSQL connection with pgAdmin 4

pgAdmin is a graphical PostgreSQL client; it does not install or host the
server, and a successful pgAdmin connection does not test ODBC. Install pgAdmin
4 on the administrator or application VM from the [official pgAdmin Windows
download](https://www.pgadmin.org/download/pgadmin-4-windows/).

Open pgAdmin, right-click **Servers**, select **Register > Server**, and enter
the DBA-provided host name/private IP, port `5432`, maintenance database
`depo` (or `postgres`), user `depo_app`, and password. Set SSL mode to
`verify-full` and select the customer CA certificate when required. Use any
local label such as `DEPO PostgreSQL (remote)` for the General > Name field.

Open **Tools > Query Tool** and run these read-only checks:

```sql
SELECT current_database(), current_user, current_schema();
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'semantic'
ORDER BY table_name;
```

The first query must show `depo`, `depo_app`, and the expected schema. The
second confirms that the application schema is reachable. A pgAdmin connection
proves PostgreSQL network access and credentials only; continue with the ODBC
test below when another Windows application requires ODBC.

### 1.1.2 Install and test the PostgreSQL ODBC driver on a 64-bit Windows VM

Install psqlODBC on the Windows VM where the ODBC-consuming application or
service runs, not on the PostgreSQL database VM. Download the signed 64-bit
Windows installer from the [official PostgreSQL ODBC project](https://odbc.postgresql.org/).
After installation, verify that Windows registered the driver:

```powershell
Get-OdbcDriver -Name '*PostgreSQL*' | Format-Table Name, Platform, Version
Start-Process "$env:WINDIR\System32\odbcad32.exe"
```

On 64-bit Windows, `System32\odbcad32.exe` is the 64-bit ODBC Administrator.
In **System DSN**, select **Add**, choose **PostgreSQL Unicode(x64)**, and set
the data source name to `DEPO_PG_REMOTE`. Enter the DBA-provided host, port,
database `depo`, and user `depo_app`; set SSL mode to `verify-full` and select
the customer root CA if TLS is required. For an approved private non-TLS setup,
set SSL mode to `disable`. Use a System DSN for a Windows service. Do not
export the DSN with a plaintext password.

Test the DSN without putting the password in command history:

```powershell
$secure = Read-Host 'PostgreSQL password' -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
$plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
try {
  $cn = [System.Data.Odbc.OdbcConnection]::new("DSN=DEPO_PG_REMOTE;UID=depo_app;PWD=$plain;")
  $cn.Open(); $cmd = $cn.CreateCommand()
  $cmd.CommandText = 'select current_database(), current_user, current_schema()'
  $reader = $cmd.ExecuteReader()
  while ($reader.Read()) { '{0} / {1} / {2}' -f $reader.GetValue(0), $reader.GetValue(1), $reader.GetValue(2) }
  $reader.Close(); $cn.Close()
} finally {
  $plain = $null
  if ($ptr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}
```

The DEPO backend uses `DEPO_DATABASE_URL` through `psycopg`; ODBC is optional
for external Windows tools. If no driver appears, check that the 64-bit driver
was installed. A timeout indicates DNS, firewall, or port `5432` access; an SSL
error indicates a CA or hostname mismatch; an authentication error requires
the DBA to check role, password, and schema grants.

Neo4j may run on-premises, on a private VM, as a hosted self-managed server, or
in Neo4j Aura. Use the provider's actual database name. Production requires
certificate-verified TLS: `neo4j+s://` or direct `bolt+s://`. Bootstrap may use
`+ssc` or plaintext only on a controlled local network. Configure the advertised
Bolt address, certificate chain and application database account. The application
installer does not install or operate either database server.

### 1.2 Install optional Apache Spark and PySpark

> **Current Windows deployment boundary:** Until a Linux Spark VM is available,
> DEPO runs native Windows Spark only in the dedicated
> `data-pipeline-worker` process. The HTTP Data Pipeline service submits a
> durable PostgreSQL run and returns a queued status; it does not own the JVM.
> PostgreSQL leases, worker heartbeats, bounded retries and expired-lease
> recovery prevent an API restart from losing submitted work. Set
> `DEPO_PIPELINE_EXECUTION_MODE=worker` for customer installations. The
> `inline` mode is retained only for isolated developer compatibility.

Install Spark only when the Data Pipeline service will execute Spark jobs. The
application validates one fixed layout: **Spark 4.1.2**, **Scala 2.13**, **JDK
21**, the bundled PySpark/Py4J libraries, and the Windows Hadoop helper. Follow
the commands below from an Administrator PowerShell window.

Run the Spark setup in this order. Do not jump directly to the final installer:

| Order | Run | Continue with |
| --- | --- | --- |
| 1 | Step A | Confirm `java -version` starts with `21` |
| 2 | Step B | Confirm both files exist under `C:\DEPO\downloads` |
| 3 | Step C | Confirm the SHA-512 and GPG checks pass |
| 4 | Step D | Confirm `spark-submit.cmd`, `pyspark.zip`, the Spark core JAR, approved `winutils.exe`, and `hadoop.dll` exist |
| 5 | Section 2.3 | Copy the verified paths into the root `.env.local` |
| 6 | Section 3 | Run the application installer with `-EnableSpark` |
| 7 | Section 4 | Complete post-install validation and customer acceptance |

The only archive downloaded in this sequence is
`spark-4.1.2-bin-hadoop3.tgz`. The `.tgz` is extracted by Windows
`tar.exe` in Step D; no separate unzip program or `pip install pyspark` command
is required.

The exact filenames expected at the end of the Spark setup are:

| Location | Exact filename |
| --- | --- |
| `C:\DEPO\downloads` | `spark-4.1.2-bin-hadoop3.tgz` |
| `C:\DEPO\downloads` | `spark-4.1.2-bin-hadoop3.tgz.sha512` |
| `C:\DEPO\downloads` | `spark-4.1.2-bin-hadoop3.tgz.asc` |
| `C:\DEPO\downloads` | `apache-spark-KEYS` |
| `C:\DEPO\runtime\spark-4.1.2-bin-hadoop3\bin` | `spark-submit.cmd` |
| `C:\DEPO\runtime\spark-4.1.2-bin-hadoop3\python\lib` | `pyspark.zip` |
| `C:\DEPO\runtime\spark-4.1.2-bin-hadoop3\python\lib` | `py4j-0.10.9.9-src.zip` |
| `C:\DEPO\runtime\spark-4.1.2-bin-hadoop3\jars` | `spark-core_2.13-4.1.2.jar` |
| `C:\DEPO\runtime\hadoop\bin` | `winutils.exe` |
| `C:\DEPO\runtime\hadoop\bin` | `hadoop.dll` |
| JDK installation directory `bin` | `java.exe` |

The Py4J filename can include a Spark-published patch version. Step D's
`Get-Item` check validates the PySpark archive and Spark core JAR; the runtime
smoke test validates the bundled Py4J library.

#### Step A — install and verify JDK 21

Install JDK 21 through the customer software catalogue. If the customer permits
Windows Package Manager, this command installs Microsoft OpenJDK 21:

```powershell
winget install --id Microsoft.OpenJDK.21 -e --source winget
java -version
$jdkHome = 'C:\Program Files\Java\jdk-21' # Replace if the installer used another JDK 21 folder.
Get-Item "$jdkHome\bin\java.exe", "$jdkHome\release"
```

Close and reopen PowerShell if `java` is not found. The version output must start
with `21`. Record the JDK installation folder containing `bin\java.exe` and a
`release` file. The examples below use `C:\Program Files\Java\jdk-21`; replace
that path if your JDK installer uses another folder.

#### Step B — download Spark 4.1.2 and its SHA-512 file

This release is intentionally pinned to Spark 4.1.2 because the application
checks for `spark-core_2.13-4.1.2.jar`. Apache ships the Windows-compatible
binary as a **`.tgz`** archive; it does not publish a `.zip` file for this
package. Windows 10/11 includes `tar.exe`, which extracts `.tgz` files.

Download these exact files. Do **not** download `pyspark-4.1.2.tar.gz`,
`pyspark_client-4.1.2.tar.gz`, `spark-4.1.2.tgz`, or the `-connect` archive:
they do not provide the full local Spark runtime expected by this application.

| Purpose | Exact file to download | Direct Apache URL |
| --- | --- | --- |
| Spark runtime | `spark-4.1.2-bin-hadoop3.tgz` | [download runtime](https://archive.apache.org/dist/spark/spark-4.1.2/spark-4.1.2-bin-hadoop3.tgz) |
| SHA-512 checksum | `spark-4.1.2-bin-hadoop3.tgz.sha512` | [download checksum](https://archive.apache.org/dist/spark/spark-4.1.2/spark-4.1.2-bin-hadoop3.tgz.sha512) |
| GPG signature | `spark-4.1.2-bin-hadoop3.tgz.asc` | [download signature](https://archive.apache.org/dist/spark/spark-4.1.2/spark-4.1.2-bin-hadoop3.tgz.asc) |
| Apache signing keys | `KEYS` | [download keys](https://downloads.apache.org/spark/KEYS) |

The 4.1.2 files are historical-release artifacts because the application is
pinned to that approved baseline. Record the security approval alongside the
release evidence.

```powershell
$sparkVersion = '4.1.2'
$jdkHome = 'C:\Program Files\Java\jdk-21' # Replace with the JDK 21 folder verified in Step A.
$sparkHome = "C:\DEPO\runtime\spark-$sparkVersion-bin-hadoop3"
$sparkArchive = "C:\DEPO\downloads\spark-$sparkVersion-bin-hadoop3.tgz"
$sparkUrl = 'https://archive.apache.org/dist/spark/spark-4.1.2/spark-4.1.2-bin-hadoop3.tgz'

New-Item -ItemType Directory -Force C:\DEPO\downloads, C:\DEPO\runtime, C:\DEPO\data\spark-output, C:\DEPO\runtime\hadoop\bin | Out-Null
Invoke-WebRequest -Uri $sparkUrl -OutFile $sparkArchive
Invoke-WebRequest -Uri "$sparkUrl.sha512" -OutFile "$sparkArchive.sha512"
```

#### Step C — verify the download before extracting it

Run the following checksum check. It stops immediately if the downloaded
archive differs from the Apache-published SHA-512 value.

```powershell
$expectedHash = ((Get-Content "$sparkArchive.sha512" -Raw).Trim() -split '\s+')[0].ToUpperInvariant()
$actualHash = (Get-FileHash -Algorithm SHA512 $sparkArchive).Hash.ToUpperInvariant()
if ($actualHash -ne $expectedHash) { throw "Spark SHA-512 verification failed. Delete $sparkArchive and download it again." }
Write-Host 'Spark SHA-512 verification passed.'
```

For a customer release, also validate the Apache release signature. Install
Gpg4win from the customer software catalogue first, then run. These commands
download the exact `.asc` and `KEYS` files listed in the table above:

```powershell
Invoke-WebRequest -Uri "$sparkUrl.asc" -OutFile "$sparkArchive.asc"
Invoke-WebRequest -Uri 'https://downloads.apache.org/spark/KEYS' -OutFile 'C:\DEPO\downloads\apache-spark-KEYS'
gpg --import C:\DEPO\downloads\apache-spark-KEYS
gpg --verify "$sparkArchive.asc" $sparkArchive
if ($LASTEXITCODE -ne 0) { throw 'Spark signature verification failed.' }
```

Record the successful SHA-512 and signature verification in the release
evidence. The archive directory lists the Spark binary and accompanying
`.sha512` and `.asc` files: [Spark 4.1.2 Apache archive](https://archive.apache.org/dist/spark/spark-4.1.2/).

#### Step D — extract Spark and install the Windows helper

Use the `tar.exe` included with current Windows. First verify that PowerShell
can find it, then list the archive contents, and only then extract it. The
commands stop if `tar.exe` is missing or the expected Spark folder already
exists. The final `Get-Item` command proves that the exact files required by
`test-depo-spark.ps1` exist.

```powershell
$tar = Get-Command tar.exe -ErrorAction Stop
& $tar.Source -tzf $sparkArchive | Select-Object -First 10
if (Test-Path $sparkHome) { throw "Spark folder already exists: $sparkHome. Verify it, or remove it before extracting again." }
& $tar.Source -xzf $sparkArchive -C C:\DEPO\runtime
if (-not (Test-Path "$sparkHome\bin\spark-submit.cmd")) { throw "Spark extraction did not create $sparkHome" }
```

##### Step D1 — obtain an approved Windows Hadoop helper

Microsoft does **not** publish a current supported `winutils.exe` package.
Microsoft's archived 2015 Spark-on-Windows article points to an obsolete
third-party Hortonworks HTTP download; do not use that URL for a customer
installation. Apache Hadoop contains the Windows helper source and looks for
`%HADOOP_HOME%\bin\winutils.exe`, but Apache Hadoop and Apache Spark do not
publish an official Windows `winutils.exe` binary with the Spark archive.

**Why Hadoop 3.4.2:** Spark's `v4.1.2` source sets
`<hadoop.version>3.4.2</hadoop.version>`. The downloaded
`spark-4.1.2-bin-hadoop3.tgz` therefore contains Hadoop 3.4.2 client JARs. Prove
the installed distribution matches before accepting any native helper:

```powershell
$sparkHome = 'C:\DEPO\runtime\spark-4.1.2-bin-hadoop3'
$expectedHadoopJars = @(
  "$sparkHome\jars\hadoop-client-api-3.4.2.jar",
  "$sparkHome\jars\hadoop-client-runtime-3.4.2.jar"
)
$missing = $expectedHadoopJars | Where-Object { -not (Test-Path -LiteralPath $_ -PathType Leaf) }
if ($missing) { throw "Spark 4.1.2 does not contain the expected Hadoop 3.4.2 JARs: $($missing -join ', ')" }
Get-Item $expectedHadoopJars | Select-Object Name, Length
```

There is no official URL from which to download a precompiled Hadoop 3.4.2
`winutils.exe`. The official download is **source code**. Build it once on an
approved Windows build workstation and publish the resulting binaries to the
customer's internal software repository. Do not build Hadoop on the production
application VM.

###### Step D1a — download and verify the official Hadoop 3.4.2 source

Run in PowerShell on the build workstation:

```powershell
$hadoopVersion = '3.4.2'
$downloadRoot = 'C:\DEPO\build-downloads'
$sourceArchive = "$downloadRoot\hadoop-$hadoopVersion-src.tar.gz"
New-Item -ItemType Directory -Force $downloadRoot | Out-Null

Invoke-WebRequest -Uri "https://archive.apache.org/dist/hadoop/common/hadoop-$hadoopVersion/hadoop-$hadoopVersion-src.tar.gz" -OutFile $sourceArchive
Invoke-WebRequest -Uri "https://archive.apache.org/dist/hadoop/common/hadoop-$hadoopVersion/hadoop-$hadoopVersion-src.tar.gz.sha512" -OutFile "$sourceArchive.sha512"
Invoke-WebRequest -Uri "https://archive.apache.org/dist/hadoop/common/hadoop-$hadoopVersion/hadoop-$hadoopVersion-src.tar.gz.asc" -OutFile "$sourceArchive.asc"

$expected = ((Get-Content "$sourceArchive.sha512" -Raw) -split '\s+')[0].ToLowerInvariant()
$actual = (Get-FileHash $sourceArchive -Algorithm SHA512).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw 'Hadoop 3.4.2 source SHA-512 verification failed.' }
Write-Host 'Hadoop 3.4.2 source SHA-512 verification passed.'
```

If GnuPG is approved on the build workstation, also verify the Apache release
signature:

```powershell
Invoke-WebRequest -Uri 'https://downloads.apache.org/hadoop/common/KEYS' -OutFile "$downloadRoot\apache-hadoop-KEYS"
gpg --import "$downloadRoot\apache-hadoop-KEYS"
gpg --verify "$sourceArchive.asc" $sourceArchive
if ($LASTEXITCODE -ne 0) { throw 'Hadoop 3.4.2 source signature verification failed.' }
```

###### Step D1b — build the 64-bit Windows native distribution

The Hadoop 3.4.2 `BUILDING.txt` requires Windows 10, JDK 8, Maven, CMake 3.19+
and Visual Studio 2019. This JDK 8 is used only on the build workstation; DEPO
continues to use JDK 21 at runtime. Install the **Desktop development with C++**
workload and MSVC v142 toolset with Visual Studio 2019. Install Git for Windows,
Maven and CMake, and ensure `git.exe`, `mvn.cmd`, `cmake.exe` and the JDK 8
`java.exe` are on `PATH`.

The repository automates source download, SHA-512 and PGP verification, pinned
vcpkg dependency installation, compilation, output collection and SHA-256
manifest creation. From **x64 Native Tools Command Prompt for VS 2019**, run:

```powershell
Set-Location <repository-root>
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\infra\windows\build-depo-hadoop-windows.ps1 `
  -BuildRoot 'C:\DEPO\hadoop-build' `
  -VcpkgRoot 'C:\vcpkg' `
  -OutputDirectory 'C:\DEPO\approved\hadoop-3.4.2-windows-x64'
```

Do not use `-SkipSignatureVerification` for a production package. The switch is
provided only for an isolated build environment where the customer's approved
supply-chain process performs PGP verification outside this script. A failed
download, checksum, signature, dependency installation, compilation or missing
output stops the script. A successful run produces:

```text
C:\DEPO\approved\hadoop-3.4.2-windows-x64\
├── build-manifest.json
└── bin\
    ├── winutils.exe
    └── hadoop.dll
```

The following commands show the underlying Apache build procedure and provide
a manual recovery path if the automated script reports a workstation-specific
toolchain problem.

Open **x64 Native Tools Command Prompt for VS 2019** and execute the following
commands. Hadoop requires a short source path:

```bat
mkdir C:\hdc
cd /d C:\hdc
tar -xzf C:\DEPO\build-downloads\hadoop-3.4.2-src.tar.gz

cd /d C:\
git clone https://github.com/microsoft/vcpkg.git C:\vcpkg
cd /d C:\vcpkg
git checkout 7ffa425e1db8b0c3edf9c50f2f3a0f25a324541d
call bootstrap-vcpkg.bat
vcpkg.exe install boost:x64-windows protobuf:x64-windows openssl:x64-windows zlib:x64-windows

cd /d C:\hdc\hadoop-3.4.2-src
set classpath=
set PROTOBUF_HOME=C:\vcpkg\installed\x64-windows
set MAVEN_OPTS=-Xmx2048M -Xss128M
mvn clean package -Dhttps.protocols=TLSv1.2 -DskipTests -DskipDocs -Pnative-win,dist -Drequire.openssl -Drequire.test.libhadoop -Pyarn-ui -Dshell-executable=C:\Git\bin\bash.exe -Dtar -Dopenssl.prefix=C:\vcpkg\installed\x64-windows -Dcmake.prefix.path=C:\vcpkg\installed\x64-windows -Dwindows.cmake.toolchain.file=C:\vcpkg\scripts\buildsystems\vcpkg.cmake -Dwindows.cmake.build.type=RelWithDebInfo -Dwindows.build.hdfspp.dll=off -Dwindows.no.sasl=on -Duse.platformToolsetVersion=v142
if errorlevel 1 exit /b 1
```

The command is the Apache Hadoop 3.4.2 Windows build command with the
`native-win` profile. After it succeeds, locate and stage the two files:

```powershell
$sourceRoot = 'C:\hdc\hadoop-3.4.2-src'
$winutils = Get-ChildItem $sourceRoot -Recurse -Filter winutils.exe | Where-Object FullName -Match '\\target\\bin\\winutils\.exe$' | Select-Object -First 1
$hadoopDll = Get-ChildItem $sourceRoot -Recurse -Filter hadoop.dll | Where-Object FullName -Match '\\target\\bin\\hadoop\.dll$' | Select-Object -First 1
if (-not $winutils -or -not $hadoopDll) { throw 'The Hadoop Windows build did not produce winutils.exe and hadoop.dll.' }

$approvedOutput = 'C:\DEPO\approved\hadoop-3.4.2-windows-x64\bin'
New-Item -ItemType Directory -Force $approvedOutput | Out-Null
Copy-Item -LiteralPath $winutils.FullName -Destination "$approvedOutput\winutils.exe"
Copy-Item -LiteralPath $hadoopDll.FullName -Destination "$approvedOutput\hadoop.dll"
Get-FileHash "$approvedOutput\winutils.exe", "$approvedOutput\hadoop.dll" -Algorithm SHA256
```

Security must scan and approve these two files and their recorded SHA-256
values. Publish that exact folder in the customer's internal repository. The
application administrator downloads the approved internal package into
`C:\DEPO\downloads\hadoop-helper` and continues with Step D2 below.

The customer's security or platform team must provide these exact files through
its approved software repository or build them from the matching Apache Hadoop
source and publish them internally:

| Required file | Purpose |
| --- | --- |
| `winutils.exe` | Hadoop local-filesystem permission and helper operations on native Windows |
| `hadoop.dll` | Required native Hadoop library for the validated Windows runtime |

The internal package owner must provide a SHA-256 value for each file. Copy the
approved files to a staging folder such as `C:\DEPO\downloads\hadoop-helper`.
Do not put either binary in this Git repository and do not copy `hadoop.dll` to
`C:\Windows\System32`.

Confirm the supplied filenames and calculate the hashes:

```powershell
$helperSource = 'C:\DEPO\downloads\hadoop-helper'
Get-Item "$helperSource\winutils.exe", "$helperSource\hadoop.dll"
Get-FileHash "$helperSource\winutils.exe" -Algorithm SHA256
Get-FileHash "$helperSource\hadoop.dll" -Algorithm SHA256
```

Compare those values with the hashes published in the customer's software
approval record. A locally calculated hash alone does not establish trust.

##### Step D2 — install and validate the helper

Run the repository installer from the repository root. Replace the two example
hashes with the approved 64-character SHA-256 values:

```powershell
$helperSource = 'C:\DEPO\downloads\hadoop-helper'
$winutilsSha256 = '<approved-64-character-winutils-sha256>'
$hadoopDllSha256 = '<approved-64-character-hadoop-dll-sha256>'

powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\infra\windows\install-depo-winutils.ps1 `
  -WinutilsPath "$helperSource\winutils.exe" `
  -WinutilsSha256 $winutilsSha256 `
  -HadoopDllPath "$helperSource\hadoop.dll" `
  -HadoopDllSha256 $hadoopDllSha256 `
  -Destination 'C:\DEPO\runtime\hadoop'
```

The script refuses a hash mismatch and refuses to overwrite an existing helper.
Use `-Force` only for an approved replacement. It installs the files under
`C:\DEPO\runtime\hadoop\bin`, removes the downloaded-file block after hash
approval, runs `winutils.exe ls`, and prints the installed hashes.

Verify the complete runtime layout:

```powershell
$hadoopHome = 'C:\DEPO\runtime\hadoop'
Get-Item "$sparkHome\bin\spark-submit.cmd",
  "$sparkHome\python\lib\pyspark.zip",
  "$sparkHome\jars\spark-core_2.13-4.1.2.jar",
  "$hadoopHome\bin\winutils.exe",
  "$hadoopHome\bin\hadoop.dll",
  "$jdkHome\bin\java.exe"

& "$hadoopHome\bin\winutils.exe" ls $hadoopHome
if ($LASTEXITCODE -ne 0) { throw 'winutils.exe validation failed.' }
```

Do not run `pip install pyspark`; the backend uses the PySpark and Py4J archives
already inside `$sparkHome`. Continue with section 2.3 to write these paths to
the root `.env.local`. The deployment scripts load root `.env.local` into the
Windows **process environment** each time they run; do not set permanent
machine-wide `SPARK_HOME`, `JAVA_HOME`, or `HADOOP_HOME` values. After the
backend install in section 3, execute this smoke test:

```powershell
# Spark configuration must be present in root .env.local first.
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\test-depo-spark.ps1 -EnvFile .env.local
```

Continue with the application installer in section 3, then complete section 4.
Spark jobs remain governed by the Data Pipeline
service and cannot write Neo4j directly. Add `-EnableNeo4jSparkConnector` only
after the regular smoke test passes and the Neo4j connection check in the
installer succeeds.

### 1.3 Choose document OCR on Windows; verify it immediately after section 3

DEPO extracts the native PDF text layer first. Scanned PDFs then use the OCR
provider selected by `DOCUMENT_OCR_PROVIDER`. The standard installer installs
both Python adapters; EasyOCR provides an in-process fallback and does not
require a separate Windows executable. Tesseract remains supported when the
customer already operates an approved Tesseract installation.

Do not run the verification commands before the installer. Complete sections 2
and 3 first; then return to this subsection and run these commands from the
repository root after section 3 has created the backend virtual environment:

```powershell
Set-Location 'E:\App\PMem' # Replace only when the repository is elsewhere.
& '.\backend\.dt_venv\Scripts\python.exe' -c "import easyocr, fitz, pypdf, PIL; print('EasyOCR', easyocr.__version__); print('PyMuPDF', fitz.VersionBind); print('pypdf', pypdf.__version__)"
```

For an internet-connected provisioning VM, set the following temporarily in
the root `.env.local` so EasyOCR downloads its signed package-published model
assets on the first controlled OCR smoke test:

```dotenv
DOCUMENT_OCR_PROVIDER=easyocr
DOCUMENT_OCR_LANGUAGES=en
DOCUMENT_EASYOCR_MODEL_DIR=C:\DEPO\models\easyocr
DOCUMENT_EASYOCR_ALLOW_DOWNLOAD=true
DOCUMENT_OCR_GPU=false
DOCUMENT_MAX_OCR_PAGES=100
```

Create the model directory, run the smoke test, then set downloads to `false`:

```powershell
New-Item -ItemType Directory -Force 'C:\DEPO\models\easyocr' | Out-Null
$env:DOCUMENT_OCR_PROVIDER='easyocr'
$env:DOCUMENT_OCR_LANGUAGES='en'
$env:DOCUMENT_EASYOCR_MODEL_DIR='C:\DEPO\models\easyocr'
$env:DOCUMENT_EASYOCR_ALLOW_DOWNLOAD='true'
& '.\backend\.dt_venv\Scripts\python.exe' -c "from backend.Services.document_processor import _easyocr_reader; r=_easyocr_reader(); print(type(r).__name__)"
(Get-ChildItem -LiteralPath 'C:\DEPO\models\easyocr' -File).Name
```

Change `DOCUMENT_EASYOCR_ALLOW_DOWNLOAD=false` in `.env.local` after the model
files exist. Copy the populated model directory through the customer's normal
artifact-verification process when production VMs cannot access the internet.
Never copy IIF's hardcoded `C:\krown_code` path into DEPO configuration.

If the customer selects Tesseract instead, install its approved 64-bit Windows
package, place `tesseract.exe` on the service account's `PATH`, set
`DOCUMENT_OCR_PROVIDER=tesseract`, and verify it from the same PowerShell
session:

```powershell
tesseract --version
& '.\backend\.dt_venv\Scripts\python.exe' -c "from backend.Services.document_processor import runtime_status; import json; print(json.dumps(runtime_status(), indent=2))"
```

The final JSON must show `"ocr_available": true` and the intended
`"ocr_provider"`. OCR output is retained as raw page evidence with provider,
confidence when supplied by EasyOCR, and a SHA-256 text digest. LLM correction
or summarization is a separate review proposal and never replaces raw evidence.

## 2. Create configuration

### There are exactly two `.env.local` files in a standard installation

Create and configure **only these two files**. They are ignored by Git and
must never be copied into a release package or source-control repository.

| File | Who uses it | What it contains | Do not put here |
| --- | --- | --- | --- |
| `.env.local` at the repository root | All ten backend services, migrations, Neo4j checks and Spark scripts | Database and Neo4j credentials, service settings, API keys, Spark settings | Browser configuration |
| `frontend/.env.local` | The Vite frontend build only | Public HTTPS API gateway address and optional public browser settings | Passwords, API keys, database URLs, Neo4j credentials, Spark paths |

`config/deployment.env.example` and `config/spark.env.example` are **templates**,
not extra environment files. `standalone/ontology_agentic_service/.env.example`
belongs only to that separate standalone component; do not create it for this
application deployment.

### 2.1 Create the root server file

From the repository root, run this command once. It copies the server template
and generates distinct API-key values without printing them:

```powershell
if (-not (Test-Path .env.local)) {
  powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\deployment\new-depo-deployment-config.ps1
}
```

Open the new root `.env.local` and edit these values in order:

For customer-isolated agent memory, add a unique scope and retention period.
Use the actual customer and program identifiers; do not copy the example value
unchanged. Leave `AGENT_MEMORY_ENABLED=false` when Neo4j conversation memory is
not approved. PostgreSQL conversation history remains available to the agent.

```env
DEPO_TENANT_ID=customer-acme
DEPO_PROJECT_ID=program-alpha
AGENT_MEMORY_ENABLED=true
AGENT_MEMORY_SCOPE=customer-acme:program-alpha
AGENT_MEMORY_QUERY_TIMEOUT=5
AGENT_MEMORY_RETENTION_DAYS=30
AGENT_PROMPT_VERSION=1
AGENT_FAILURE_RATE_ALERT_THRESHOLD=0.2
AGENT_STUCK_RUN_SECONDS=900
```

After the installer starts the Agentic service, verify its monitoring loop as
part of Section 4.7. Do not run these commands during configuration. The
summary and run endpoints use graph-read authentication. The Prometheus
endpoint exposes aggregate operational values and contains no prompt or
tool-input content.

```powershell
Invoke-RestMethod http://127.0.0.1:8012/healthz
Invoke-RestMethod http://127.0.0.1:8012/api/v1/observability/summary `
  -Headers @{ Authorization = "Bearer $env:GRAPH_READ_TOKEN" }
Invoke-WebRequest http://127.0.0.1:8012/api/v1/metrics | Select-Object -ExpandProperty Content
```

1. Set `DEPO_DATABASE_URL` to the PostgreSQL connection URL and
   `DEPO_DATABASE_SCHEMA=semantic` (or the customer-approved schema). For the
   local Windows service installed in section 1.1, also set
   `DEPO_POSTGRES_MODE=service` and `DEPO_POSTGRES_SERVICE_NAME` to the exact
   Windows service `Name`. For a managed or remote database, retain
   `DEPO_POSTGRES_MODE=external` and leave `DEPO_POSTGRES_SERVICE_NAME` empty.
2. Set `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASS` and `NEO4J_DATABASE`. Aura
   exports named `NEO4J_USERNAME` and `NEO4J_PASSWORD` are also accepted by
   the Spark connector, but use the canonical `NEO4J_USER` and `NEO4J_PASS`
   names for the application. For an explicitly unsecured on-premises Neo4j
   server, set `NEO4J_AUTH_MODE=none` and use `NEO4J_URI=bolt://host:7687` or
   `neo4j://host:7687`; omit the user and password. This mode is rejected for
   production preflight and is intended only for a deliberately unsecured
   non-TLS environment.
3. Set `ALLOWED_ORIGINS=https://<customer-frontend-host>` and
   `OSLC_BASE_URL=https://<customer-api-host>`.
   Set `ARTIFACT_STORAGE=C:\DEPO\data\artifacts`, create that directory, and
   grant the DEPO service account Modify permission. The API services and the
   data-pipeline worker must resolve this exact same absolute path.
4. Keep `AUTH_MODE=token`. This delivery uses API keys; it does not require
   Entra or GitHub Actions. Do not replace the generated token values unless
   the customer secret-management process supplies approved replacements.
   Confirm the generated root file contains distinct non-placeholder values
   for `GRAPH_READ_TOKEN`, `GRAPH_PUBLICATION_TOKEN`,
   `ONTOLOGY_APPROVAL_TOKEN`, `DATA_PRODUCT_APPROVAL_TOKEN`,
   `DATA_JOB_EXECUTION_TOKEN`, `INGESTION_WRITE_TOKEN`, and
   `AGENTIC_APPROVAL_TOKEN`. The API gateway supplies the appropriate token to
   backend requests; never put these server secrets in `frontend/.env.local`.
5. Leave all `DEPO_SPARK_*` values out until step 2.3 unless Spark is part of
   this installation.

Ontology agents are deterministic by default. Keep
`ONTOLOGY_AGENT_LLM_ENABLED=false` for the initial installation. To enable
review-only LLM suggestions later, configure the existing Ollama or Azure
provider in the server environment, set `ONTOLOGY_AGENT_LLM_ENABLED=true`, and
restart the Agentic service. The LLM can suggest validation questions; it cannot
approve mappings or publish to Neo4j. Keep
`ONTOLOGY_AGENT_ALLOWED_ROOTS` limited to approved ontology data directories.
Keep `ONTOLOGY_AGENT_MAX_BYTES=26214400` unless the customer has approved a
different artifact limit.

The shared parser rejects duplicate keys before changing the process
environment. Edit a key in place; never append another line with the same key.

### 2.2 Create the frontend browser file

Create this file once, then set the public API gateway URL **before** running
the frontend build. A browser can read every `VITE_*` value, so this file must
contain no credentials.

```powershell
if (-not (Test-Path .\frontend\.env.local)) {
  Copy-Item .\frontend\.env.example .\frontend\.env.local
}
notepad .\frontend\.env.local
```

For a customer deployment, set this single line and leave the individual
service URLs commented unless the customer deliberately exposes separate
gateway routes:

```text
VITE_API_GATEWAY_URL=https://api.customer.example
```

For a local developer installation, leave `VITE_API_GATEWAY_URL` empty. The
frontend then uses the local service ports listed in `infra/deployment/services.json`.

For a local installation without an API gateway, configure the file from the
repository root:

```powershell
Set-Location .\frontend
if (-not (Test-Path .\.env.local)) { Copy-Item .\.env.example .\.env.local }
notepad .\.env.local
```

Keep this line empty in the file:

```text
VITE_API_GATEWAY_URL=
```

Save the file and return to the repository root. Do not run `npm ci`, build, or
start the frontend yet; the single installer in Section 3 performs the clean
frontend installation and production build. Section 4.4 starts the completed
build for the local browser smoke test. Open `http://127.0.0.1:3000/` only
after reaching that section, and use **Ctrl+F5** after rebuilding.
The ontology registry request must go to
`http://127.0.0.1:8014/api/v1/ontology/registered`. If that endpoint returns
HTTP 200 with an `ontologies` array but the UI is blank, rebuild after checking
that `VITE_API_GATEWAY_URL` is still empty; Vite embeds environment values at
build time.

### 2.3 Add optional Spark settings to the root server file

For Spark, merge only the required values from `config/spark.env.example` into
the existing **root** `.env.local`. Do not create `spark.env.local`.
Add these values after the database and Neo4j settings:
`DEPO_SPARK_HOME`, `DEPO_JAVA_HOME`, `DEPO_HADOOP_HOME`,
`DEPO_SPARK_OUTPUT_ROOT` and `DEPO_SPARK_MASTER`.

This release uses an in-process `SparkSession` on the Windows application VM.
Apache Spark Connect was assessed but is not enabled because it requires a
separately operated Spark Connect server endpoint, and this customer topology
currently has no Linux or managed Spark cluster. Spark Connect is the preferred
future production topology when that server exists: the Windows application VM
then acts only as a client and no longer needs a local Spark JVM or
`winutils.exe`. PostgreSQL JDBC remains a data-source connector in either
topology; it is not a substitute for Spark Connect.

Example for an installation under `C:\DEPO\runtime`. This command updates each
Spark key in place, so it is safe to run again after changing a path:

```powershell
$sparkSettings = @{
  DEPO_SPARK_HOME = 'C:\DEPO\runtime\spark-4.1.2-bin-hadoop3'
  DEPO_JAVA_HOME = 'C:\Program Files\Java\jdk-21'
  DEPO_HADOOP_HOME = 'C:\DEPO\runtime\hadoop'
  DEPO_SPARK_OUTPUT_ROOT = 'C:\DEPO\data\spark-output'
  DEPO_SPARK_MASTER = 'local[2]'
  DEPO_SPARK_ENABLED = 'false'
  DEPO_SPARK_NEO4J_ENABLED = 'false'
  DEPO_SPARK_POSTGRES_ENABLED = 'false'
  DEPO_PIPELINE_SCHEDULER_ENABLED = 'false'
  DEPO_PIPELINE_EXECUTION_MODE = 'worker'
  DEPO_PIPELINE_LEASE_SECONDS = '300'
  DEPO_PIPELINE_POLL_SECONDS = '5'
}
$lines = Get-Content .\.env.local
foreach ($entry in $sparkSettings.GetEnumerator()) {
  $match = "^$([regex]::Escape($entry.Key))="
  if ($lines -match $match) {
    $lines = $lines | ForEach-Object { if ($_ -match $match) { "$($entry.Key)=$($entry.Value)" } else { $_ } }
  } else {
    $lines += "$($entry.Key)=$($entry.Value)"
  }
}
Set-Content .\.env.local $lines
```

Verify the file is valid and that the Windows process receives the expected
non-secret runtime paths. This command does not print passwords or API keys:

```powershell
. .\infra\windows\runtime-config.ps1
Import-DepoEnvironment -Root (Get-Location).Path -EnvFile .env.local
[pscustomobject]@{
  DEPO_SPARK_HOME = $env:DEPO_SPARK_HOME
  DEPO_JAVA_HOME = $env:DEPO_JAVA_HOME
  DEPO_HADOOP_HOME = $env:DEPO_HADOOP_HOME
  DEPO_SPARK_OUTPUT_ROOT = $env:DEPO_SPARK_OUTPUT_ROOT
  DEPO_SPARK_MASTER = $env:DEPO_SPARK_MASTER
  DEPO_PIPELINE_EXECUTION_MODE = $env:DEPO_PIPELINE_EXECUTION_MODE
} | Format-List
```

Set feature flags to `true` only after the Spark smoke test passes. Edit existing
keys instead of appending duplicates; duplicate keys fail validation.

#### Optional: allow Spark jobs to read PostgreSQL through JDBC

The backend services continue to use `psycopg` for migrations, transactions,
and control-plane records. Enable JDBC only when an approved Spark data job must
read PostgreSQL. Spark must not write the DEPO-owned `semantic.depo_*` tables.

Download the Java 8-or-newer PostgreSQL JDBC 4.2 driver from the official
[pgJDBC download page](https://jdbc.postgresql.org/download/). The release
validated by this guide is `postgresql-42.7.13.jar`. Run these commands from an
elevated PowerShell prompt:

```powershell
New-Item -ItemType Directory -Force 'C:\DEPO\drivers' | Out-Null
Invoke-WebRequest -Uri 'https://jdbc.postgresql.org/download/postgresql-42.7.13.jar' -OutFile 'C:\DEPO\drivers\postgresql-42.7.13.jar'
Get-Item 'C:\DEPO\drivers\postgresql-42.7.13.jar'
Get-FileHash 'C:\DEPO\drivers\postgresql-42.7.13.jar' -Algorithm SHA256
```

Record the SHA-256 value in the customer installation evidence and compare it
with the checksum approved by the customer's software-supply process. Then add
these two unique lines to the root `.env.local`:

```dotenv
DEPO_SPARK_POSTGRES_ENABLED=true
DEPO_SPARK_POSTGRES_DRIVER_JAR=C:\DEPO\drivers\postgresql-42.7.13.jar
```

The same root file must already contain the remote PostgreSQL URL, including
the application role. Keep special characters percent-encoded. For the
customer's non-TLS database configuration, the shape is:

```dotenv
DEPO_DATABASE_URL=postgresql://depo_app:<percent-encoded-password>@<database-vm-ip>:5432/depo?sslmode=disable
```

Run the dedicated read-only JDBC test before installation:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\test-depo-spark.ps1 -EnvFile .env.local -PostgresConnector
```

Success prints `DEPO Spark PostgreSQL JDBC smoke test passed.` The probe runs
only `SELECT 1`; it does not create or modify tables. To enable the connector
through the single installer, use:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\install-depo-windows.ps1 -EnvFile .env.local -Profile Production -EnableSpark -EnablePostgresSparkConnector
```

### 2.4 Confirm the two files before installation

Run this check. It must show the root server file and the frontend browser file;
it must not show a `backend/.env.local` or a `spark.env.local`.

```powershell
Get-Item .\.env.local, .\frontend\.env.local | Select-Object FullName, Length, LastWriteTime
```

## 3. Run the single Windows installation command

After PostgreSQL, Neo4j, optional Spark, and both `.env.local` files are ready,
run **one** PowerShell command from the repository root. This is the supported
customer installation path; do not run the individual migration, startup, or
validation scripts by hand.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\install-depo-windows.ps1 -EnvFile .env.local -Profile Production
```

For a Spark deployment, use this command instead. Add the connector and
scheduler switches only when those customer capabilities are required:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\install-depo-windows.ps1 -EnvFile .env.local -Profile Production -EnableSpark
# Optional: -EnableNeo4jSparkConnector -EnablePostgresSparkConnector -EnablePipelineScheduler
```

The installer performs these stages in this fixed order and stops at the first
failure:

1. Validates Python, Node.js, npm, and the frontend lockfile.
2. Creates `backend/.dt_venv`, installs backend dependencies, runs `npm ci`,
   and builds `frontend/dist`.
3. Validates root `.env.local` and the ten-service deployment configuration.
4. Applies and verifies PostgreSQL migrations.
5. Verifies Neo4j TLS, authentication, and database access.
6. When enabled, validates Spark/JDK/Hadoop paths and runs the DataFrame smoke
   job before services are started.
7. Starts the ten APIs, data-product outbox worker, and durable data-pipeline
   worker; validates all endpoints; and seeds the
   approved baseline assets and data jobs.
8. Runs release preflight, including schema, Neo4j, Spark, and production
   configuration checks.

The command is safe to run again after correcting a failure: package installs,
migrations, validation, and baseline seeding use their existing idempotent
contracts. It does not create or overwrite `.env.local`, PostgreSQL accounts,
Neo4j accounts, Spark files, or customer secrets.

### 3.1 Service ports and health checks

The standard Windows service topology does not use port `8000`. Do not test
`http://127.0.0.1:8000/health` unless a customer has separately configured a
legacy aggregate API. Test the service ports below instead:

| Port | Service | Health URL |
| --- | --- | --- |
| 8010 | Schema Sets | `http://127.0.0.1:8010/readyz` |
| 8011 | Ontology | `http://127.0.0.1:8011/readyz` |
| 8012 | Agentic | `http://127.0.0.1:8012/readyz` |
| 8013 | Graph | `http://127.0.0.1:8013/readyz` |
| 8014 | Ingestion and ontology registry | `http://127.0.0.1:8014/readyz` |
| 8015 | OSLC | `http://127.0.0.1:8015/readyz` |
| 8016 | Data Catalog | `http://127.0.0.1:8016/readyz` |
| 8017 | Data Products | `http://127.0.0.1:8017/readyz` |
| 8018 | CEIM | `http://127.0.0.1:8018/readyz` |
| 8019 | Data Pipeline | `http://127.0.0.1:8019/readyz` |

Check every HTTP service from the application VM:

```powershell
8010..8019 | ForEach-Object {
  $url = "http://127.0.0.1:$($_)/readyz"
  $response = Invoke-WebRequest $url -UseBasicParsing
  "{0}: {1}" -f $url, $response.StatusCode
}
```

The expected status is `200` for every enabled service. The browser frontend
is separate and is served at `http://127.0.0.1:3000/` during a local smoke
test.

### 3.2 What the installer installs and configures

`install-depo-windows.ps1` is the orchestration entry point. It calls
`install-depo.ps1` for the Python environment and frontend, then calls the
deployment lifecycle scripts. Do not start individual Uvicorn modules for a
customer installation.

| Component | Runtime module or output | Configuration source | Lifecycle script |
| --- | --- | --- | --- |
| Frontend | `frontend/dist` | `frontend/.env.local` (`VITE_*`) | `infra/windows/install-depo.ps1` |
| Schema Sets/QIF | `backend.qif.app:app` / 8010 | root `.env.local` | `start-depo-services.ps1` |
| Ontology | `backend.ontology_service.app:app` / 8011 | root `.env.local` | `start-depo-services.ps1` |
| Agentic | `backend.agentic_service.app:app` / 8012 | root `.env.local` plus agentic settings | `start-depo-services.ps1` |
| Graph | `backend.graph_service.app:app` / 8013 | root `.env.local`, Neo4j settings | `start-depo-services.ps1` |
| Ingestion | `backend.ingestion_service.app:app` / 8014 | root `.env.local` | `start-depo-services.ps1` |
| OSLC | `backend.oslc_service.app:app` / 8015 | root `.env.local` | `start-depo-services.ps1` |
| Catalog | `backend.data_catalog_service.app:app` / 8016 | root `.env.local` | `start-depo-services.ps1` |
| Data Products | `backend.data_product_service.app:app` / 8017 | root `.env.local` | `start-depo-services.ps1` |
| CEIM | `backend.ceim_service.app:app` / 8018 | root `.env.local`, Neo4j settings | `start-depo-services.ps1` |
| Data Pipeline | `backend.data_pipeline_service.app:app` / 8019 | root `.env.local`, Spark settings | `start-depo-services.ps1` |
| Data-product worker | `backend.data_product_service.worker` | root `.env.local` | `start-depo-services.ps1` |
| Data-pipeline worker | `backend.data_pipeline_service.worker` | root `.env.local`, PostgreSQL, artifact storage, optional Spark | `start-depo-services.ps1` |

The authoritative module and port list is
[`infra/deployment/services.json`](infra/deployment/services.json). The
installer creates the backend virtual environment, installs `backend/requirements.txt`,
runs `npm ci` in `frontend`, and runs `npm run build`; it does not install
PostgreSQL, Neo4j, Java, Hadoop, or Spark binaries. Those runtimes must be
installed and configured before the installer command in Section 3.

## 4. Complete customer deployment

Complete these steps in order after Section 3 reports success. If a step fails,
stop, fix that step, and rerun only the relevant validation; do not skip ahead.

### 4.1 Confirm the installer result

From the repository root, confirm the browser build and configuration files:

```powershell
Test-Path .\frontend\dist
Get-Item .\.env.local, .\frontend\.env.local | Select-Object FullName, Length, LastWriteTime
```

Both paths must exist. Never copy either `.env.local` file into `frontend\dist`.

### 4.2 Confirm the application processes

The supported installer starts the DEPO APIs and both workers. Confirm the
recorded processes rather than listing every unrelated Python process on the
VM:

```powershell
Get-ChildItem .\logs\windows-services\*.pid | ForEach-Object {
  $processId = [int](Get-Content -LiteralPath $_.FullName)
  $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
  [pscustomobject]@{ Service = $_.BaseName; ProcessId = $processId; Running = [bool]$process; Path = $process.Path }
} | Format-Table -AutoSize
```

Use the service inventory for the exact ports:

```powershell
Get-Content .\infra\deployment\services.json
```

For each enabled service, test its health URL from the application VM. Example:

```powershell
Invoke-WebRequest http://127.0.0.1:8010/readyz -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:8011/readyz -UseBasicParsing
```

The response must be HTTP 200. Do not expose these internal ports directly to
the browser or the public network.

### 4.3 Verify the PostgreSQL schema

For a remote deployment, use pgAdmin Query Tool on the PostgreSQL VM or admin
workstation, connected to database `depo`. For a local deployment, use pgAdmin
on the application VM. Run:

```sql
SELECT current_database(), current_user;
SELECT schema_name
FROM information_schema.schemata
WHERE schema_name = 'semantic';
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'semantic'
ORDER BY table_name;
```

The `semantic` schema must be present and the table query must return the DEPO
tables. On the application VM, confirm the runtime uses the remote mode:

```powershell
. .\infra\windows\runtime-config.ps1
Import-DepoEnvironment -Root (Get-Location).Path -EnvFile .env.local
if ($env:DEPO_POSTGRES_MODE -ne 'external') { throw 'Expected external PostgreSQL mode' }
$env:DEPO_POSTGRES_MODE
```

Do not run `Start-Service` for PostgreSQL on the application VM.

### 4.4 Serve the frontend

The installer creates static files in `frontend\dist`. For a smoke test only,
serve them locally with the already-installed backend Python runtime. This
command does not download an additional npm package:

```powershell
.\backend\.dt_venv\Scripts\python.exe -m http.server 3000 --bind 127.0.0.1 --directory .\frontend\dist
```

Open `http://127.0.0.1:3000` in a browser and confirm the DEPO landing page
loads. For a customer release, copy or mount `frontend\dist` into the approved
HTTPS web server document root and configure the single-page-application fallback
to `index.html`.

### 4.5 Configure the customer gateway

Route browser API requests through the customer HTTPS gateway to the internal
DEPO services listed in `infra\deployment\services.json`. Keep service ports
private. Configure the gateway to forward the required API-key headers and to
preserve WebSocket or streaming support when the selected UI feature needs it.

### 4.6 Switch from direct service access to a gateway

A direct installation can be migrated later. The database and backend service
configuration does not change; only the browser routing and CORS configuration
change. Complete these steps in order:

1. Configure the gateway to route these paths to the internal service ports:

   ```text
   /qif            -> 8010
   /ontology       -> 8011
   /agentic        -> 8012
   /graph          -> 8013
   /ingestion      -> 8014
   /oslc           -> 8015
   /catalog        -> 8016
   /data-products  -> 8017
   /ceim           -> 8018
   /data-pipeline  -> 8019
   ```

2. Update the root server `.env.local` CORS value to the browser origin:

   ```text
   ALLOWED_ORIGINS=https://app.customer.example
   ```

3. Update `frontend/.env.local` before building:

   ```text
   VITE_API_GATEWAY_URL=https://api.customer.example
   ```

4. Rebuild the browser bundle from the repository root:

   ```powershell
   Set-Location .\frontend
   npm ci
   npm run build
   Test-Path .\dist\index.html
   ```

5. Deploy the new `frontend\dist` directory and restart the backend services so
   the new CORS setting is loaded. The browser bundle embeds Vite environment
   values at build time; changing `.env.local` without rebuilding has no effect.

6. Verify the gateway before browser acceptance:

   ```powershell
   Invoke-WebRequest https://api.customer.example/ontology/readyz -UseBasicParsing
   Invoke-WebRequest https://api.customer.example/ingestion/readyz -UseBasicParsing
   Invoke-WebRequest https://api.customer.example/data-pipeline/readyz -UseBasicParsing
   ```

   Each enabled route must return HTTP 200. Keep ports `8010–8019` private
   after the gateway is working.

### 4.7 Perform release acceptance

Run these checks in the browser in order:

1. Sign in using the customer API-key flow.
2. Open Ontology Junction and load the registered ontology list.
3. Open Semantic Bridge, select an imported instance and ontology, create a
   preview, review candidates, and confirm that publication requires approval.
4. Open the data pipeline page and verify the configured job status.
5. If Spark is enabled, run the documented Spark smoke test and confirm its
   output artifact.
6. If Neo4j is enabled, open the graph view and verify a read-only query.

Record the installer output, dependency lock versions, PostgreSQL schema result,
Neo4j evidence, Spark smoke result when enabled, browser acceptance, process
supervision, reboot recovery, monitoring, backup/restore drill, and rollback
evidence in the customer release record.

The included launcher uses hidden user-session processes and PID files. It is
suitable for installation verification and controlled demonstrations, but it
does not register Windows services and does not provide reboot recovery. Before
production acceptance, the customer platform team must place the ten API
commands and two worker commands from `infra/deployment/services.json` under
its approved Windows service/process supervisor, using the same root
`.env.local`, repository working directory, service account and restart policy.
Treat missing supervision and reboot-recovery evidence as a release blocker.

For a controlled installation or demonstration, stop and restart the complete
set in this order from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\deployment\invoke-depo-lifecycle.ps1 -Action Stop -EnvFile .env.local
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\deployment\invoke-depo-lifecycle.ps1 -Action Start -EnvFile .env.local -Profile Production -SkipPostgres
```

`-SkipPostgres` means “do not operate a local PostgreSQL process”; database
connectivity and schema validation still run against `DEPO_DATABASE_URL`.

For service ownership and ports, use `infra/deployment/services.json`. The
scripts under `infra/windows/` are implementation stages used by the one
installer, not separate installation instructions.
