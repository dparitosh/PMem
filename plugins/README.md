# DEPO plugins

All optional plugin packages live under this directory. The current package is
`mbse_plugin`, containing the MBSE API/viewer, Teamcenter/SMW mapping support,
and Cameo MDK configuration checks:

```text
plugins/
└── mbse_plugin/
    ├── mbse_plugin/              # Python service and subpackages
    │   ├── teamcenter_smw/       # offline mapping and preview
    │   └── cameo_mdk/             # native MDK preparation checks
    ├── agents/                   # agent declaration
    ├── AgentsRegistry/           # host coded-tool adapter
    ├── scripts/                  # Windows lifecycle commands
    ├── tests/
    ├── plugin.json
    └── pyproject.toml
```

Install or build from `plugins/mbse_plugin`. Generated wheels, virtual
environments, logs, and caches are intentionally excluded from source control.
