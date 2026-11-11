# QIF XSLT checks: source and changes

The stylesheets in this folder are copied from the QIF validation tools
repository, https://github.com/QualityInformationFramework/qif-validation-tools
(folder "Check QIF3plus Preview", master branch, fetched for this project).
They are licensed under the Boost Software License 1.0; see
LICENSE-qif-validation-tools.md.

Changes made for this project:

- CheckParameters.xml: CheckLinkedDocuments is set to false. The backend also
  rejects instances that contain ExternalQIFReferences, because the format and
  document checks load the referenced URI from the instance, and that path must
  not read arbitrary local files.
- CheckConstraints.xsl and CheckLibraryMSXML.xsl are not copied; they are not
  imported by Check.xsl and CheckLibraryMSXML requires MSXML.
