The AP242 Edition 2 BOM imports the accompanying `common.xsd` locally so
offline validation does not depend on the standards website.

`common.xsd` was retrieved on 2026-10-11 from the ISO-hosted source:
https://standards.iso.org/iso/ts/10303/-3000/-ed-2/tech/xml-schema/common/common.xsd

SHA-256: `3088f4f7729b97217536b28b4f27c2cb518072aa22372ccdb697b546638cfcdd`

The downloaded schema is unchanged. In `bom.xsd`, only the import's
`schemaLocation` changed from its external HTTP URL to `common.xsd`.
Both target namespaces remain unchanged. The pair compiles with lxml
XMLSchema using a parser with networking disabled.

In Import → Create ontology, select `bom.xsd` as the root and complete its
ontology details with OWL generation. In Companion XSD files select
`common.xsd`, leave its relative path as `common.xsd`, then register.
Companion file selections stay in browser memory and must be reselected
after reloading the page.
