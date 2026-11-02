"""Build DEPO business literature using the bundled document Python runtime.

Run from repository root. Render with the Documents skill render_docx.py and
inspect every page before publishing. PDF delivery is the verified render.
"""
from pathlib import Path

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT

OUT = Path('deliverables/DEPO-AI-Led-Engineering-Marketing.docx')
doc = Document()
section = doc.sections[0]
section.page_width, section.page_height = Inches(8.27), Inches(11.69)
section.top_margin = section.bottom_margin = Inches(.65)
section.left_margin = section.right_margin = Inches(.72)
section.header_distance = section.footer_distance = Inches(.28)
NAVY, TEAL, GREY = '16364D', '006F91', '526675'

for name in ('Normal', 'Body Text', 'List Bullet', 'List Number'):
    style = doc.styles[name]
    style.font.name, style.font.size = 'Arial', Pt(10.5)
    style.font.color.rgb = RGBColor.from_string('263746')
    style.paragraph_format.space_after = Pt(7)
    style.paragraph_format.line_spacing = 1.10
doc.styles['Title'].font.name = 'Arial'
doc.styles['Title'].font.size = Pt(30)
doc.styles['Title'].font.color.rgb = RGBColor(0, 0, 0)
doc.styles['Title'].paragraph_format.space_after = Pt(14)
for border in list(doc.styles['Title']._element.findall('.//' + qn('w:pBdr'))):
    border.getparent().remove(border)
for name, size in [('Heading 1', 22), ('Heading 2', 14), ('Heading 3', 11.5)]:
    st = doc.styles[name]
    st.font.name, st.font.size = 'Arial', Pt(size)
    st.font.color.rgb = RGBColor.from_string(NAVY if name == 'Heading 1' else TEAL)
    st.paragraph_format.space_before, st.paragraph_format.space_after = Pt(11), Pt(7)
    st.paragraph_format.keep_with_next = True

header = section.header.paragraphs[0]
r = header.add_run('DEPO  |  Semantic Intelligence')
r.font.name, r.font.size, r.bold = 'Arial', Pt(9), True
r.font.color.rgb = RGBColor.from_string(TEAL)
footer = section.footer.paragraphs[0]
footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
r = footer.add_run('Business overview  •  2 November 2026  |  ')
r.font.size = Pt(8)
r.font.color.rgb = RGBColor.from_string(GREY)
field = OxmlElement('w:fldSimple')
field.set(qn('w:instr'), 'PAGE')
footer._p.append(field)


def para(text, bold=False, size=None):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = bold
    if size:
        run.font.size = Pt(size)
    return p


def heading(text, level=2):
    return doc.add_heading(text, level=level)


def page(title):
    doc.add_page_break()
    heading(title, 1)


def table(headers, rows, widths):
    t = doc.add_table(rows=1, cols=len(headers))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    for i, value in enumerate(headers):
        t.rows[0].cells[i].text = value
    for row in rows:
        cells = t.add_row().cells
        for i, value in enumerate(row):
            cells[i].text = value
    repeat = OxmlElement('w:tblHeader')
    t.rows[0]._tr.get_or_add_trPr().append(repeat)
    for row_no, row in enumerate(t.rows):
        cant_split = OxmlElement('w:cantSplit')
        row._tr.get_or_add_trPr().append(cant_split)
        for i, cell in enumerate(row.cells):
            cell.width = Inches(widths[i])
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
            pr = cell._tc.get_or_add_tcPr()
            shading = OxmlElement('w:shd')
            shading.set(qn('w:fill'), NAVY if row_no == 0 else ('EFF5F8' if row_no % 2 else 'FFFFFF'))
            pr.append(shading)
            margins = OxmlElement('w:tcMar')
            for edge in ('top', 'left', 'bottom', 'right'):
                v = OxmlElement('w:' + edge)
                v.set(qn('w:w'), '105')
                v.set(qn('w:type'), 'dxa')
                margins.append(v)
            pr.append(margins)
            for p in cell.paragraphs:
                p.paragraph_format.space_after = Pt(3)
                p.paragraph_format.line_spacing = 1.05
                for run in p.runs:
                    run.font.name, run.font.size = 'Arial', Pt(9.5)
                    run.bold = row_no == 0
                    if row_no == 0:
                        run.font.color.rgb = RGBColor(255, 255, 255)
    doc.add_paragraph().paragraph_format.space_after = Pt(1)
    return t


def link(label, url):
    p = doc.add_paragraph()
    rel = p.part.relate_to(url, 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink', is_external=True)
    h = OxmlElement('w:hyperlink')
    h.set(qn('r:id'), rel)
    r = OxmlElement('w:r')
    props = OxmlElement('w:rPr')
    c = OxmlElement('w:color')
    c.set(qn('w:val'), TEAL)
    props.append(c)
    sz = OxmlElement('w:sz')
    sz.set(qn('w:val'), '18')
    props.append(sz)
    r.append(props)
    text = OxmlElement('w:t')
    text.text = label
    r.append(text)
    h.append(r)
    p._p.append(h)
    p.paragraph_format.space_after = Pt(4)


doc.add_heading('DEPO for AI Led Engineering', 0)
para('Industry ontology and governed intelligence for product decisions', True, 13)
para('DEPO helps engineering organizations turn information from product, systems, manufacturing and quality sources into connected evidence for decisions. It combines shared definitions, a contextual knowledge graph, repeatable processing and governed agents so teams can investigate a question and inspect the information behind the answer.', size=11.5)

heading('Why this application is needed')
para('A product decision rarely belongs to one system. A part change may depend on an assembly revision, a requirement, a manufacturing process and inspection evidence. Teams need a way to connect those records without losing their meaning, version or source. DEPO provides that knowledge layer around the available enterprise information.')
table(['Business gap', 'DEPO contribution'], [
    ('Information is fragmented', 'Connect supplied business records and retain their source references.'),
    ('Terminology differs across teams', 'Review source terms against shared industrial and application definitions.'),
    ('Change consequences are unclear', 'Explore recorded dependencies and expose missing evidence for review.'),
    ('AI answers lack context', 'Retrieve scoped business entities, property values and relationships.'),
    ('Data preparation is repeatedly rebuilt', 'Use governed workers to prepare reusable records, reporting tables and products.'),
], [2.35, 4.45])
heading('Questions that matter to the business')
for t in (
    'What recorded dependencies should we review if this component changes?',
    'Which requirements and process records are connected to this product revision?',
    'Which engineering candidates deserve a reuse comparison?',
    'Which released dataset can another team consume, and who approved it?',
):
    doc.add_paragraph(t, style='List Bullet')
para('The intended benefit is less effort assembling evidence and a clearer basis for review. Measure that benefit in a customer pilot rather than assuming a percentage improvement.', size=9.5)

page('Industry ontology and application ontology')
para('An ontology makes the meaning of information explicit. It defines kinds of things and the relationships that are valid between them. DEPO uses an industrial foundation, an application reference model and reviewed customer mappings to connect that meaning to actual records.')
table(['Knowledge layer', 'Role in DEPO'], [
    ('Industry ontology', 'A reusable industrial reference for physical objects, information and activities. DEPO embeds a public PCA Industrial Data Ontology snapshot as its foundation.'),
    ('Application ontology', 'DEPO business core applies the foundation to Physical Part, Part Design, Engineering Document, Requirement Specification and Manufacturing Activity.'),
    ('Domain and customer ontologies', 'Imported definitions describe the customer’s products and disciplines. They remain distinct until explicit mappings are reviewed.'),
    ('Product knowledge graph', 'Published business records, property values and relationships retain source identity and publication evidence.'),
], [2.1, 4.7])
heading('Why the distinction matters')
para('A physical manufactured part is different from its design definition. A requirement document is different from evidence that a requirement was satisfied. Explicit meaning helps prevent these concepts being collapsed simply because their names look similar.')
heading('From source terminology to connected evidence')
para('Source records → reviewed term and relationship mappings → shared business context → traceable investigation and reusable analytics', True, 11)
para('For example, a customer can map relevant source concepts from PLM, MBSE and quality vocabularies while preserving the original identifiers. Users can then investigate recorded connections between a product, a part revision and its requirement or inspection references. A mapping proposal still needs the applicable validation and authority.')
heading('Product merits')
para('Shared meaning supports consistent interpretation across teams. Preserved identities make similar labels distinguishable. Versioned definitions and retained evidence make results explainable. New sources can be incorporated through registered definitions and reviewed mappings instead of treating every label as a new business rule.')
para('Foundation scope: the embedded PCA IDO 4.2 resource is a public FDIS proposal snapshot with attribution; its presence is not ISO certification or approved customer alignment. Structural checks and OWL-DL evidence are distinct. Full checks remain conditional on supported profiles and available imports. [1]', size=9)

page('Workers agents and accountable execution')
para('AI-led engineering needs reliable execution as well as useful recommendations. DEPO separates repeatable processing, investigation and authorization so an answer or proposed connection can be reviewed before it changes released knowledge.')
table(['Capability', 'What it does', 'Business merit'], [
    ('Workers', 'Execute approved processing, validate sources, prepare analytics and retain durable run results.', 'Repeatable work with visible status, recovery and output evidence.'),
    ('AI agents', 'Use registered tools to investigate context, explain findings and propose scoped actions.', 'Assistance grounded in the available business evidence.'),
    ('Ontology Governor', 'Coordinates retained mapping or merge proposals and authorized publication workflows.', 'A visible route from proposal to release.'),
    ('Ontology Steward', 'Assesses proposals, compatibility, ambiguity and available validation evidence.', 'Accepted and held findings remain understandable.'),
    ('People and policy', 'Define intended use, accountable owners and the authority to release changes.', 'Business accountability remains explicit.'),
], [1.35, 3.15, 2.3])
heading('The connected workflow')
para('Retain sources → establish meaning → prepare and assess connections → authorize intended changes → publish and verify → consume evidence', True, 11)
para('Import, Data Flow, Ontology Junction, Metadata Registry, Data Products and Data Catalog expose their part of this journey. Change Control brings together authorization, execution and delivery evidence and links users to the responsible workspace. An executed job and an approved product are separate outcomes.')
heading('Context and memory')
para('The Knowledge Companion uses conversation context and graph-grounded retrieval of business entities, relationships and property values. Reviewed mapping outcomes can become approved, revision-scoped advisory lessons. Retained task/tool records help explain execution. Optional graph memory requires configuration and populated evidence; persistence alone is not model training.')
heading('Change awareness and reproducibility')
para('Configuration baselines retain selected source versions and declared dependencies. Supported OSLC TRS changes and source reconciliation help identify refresh needs. Changes are assessed before another preparation or release; a notification does not silently authorize publication.')
para('Live model planning and response generation require an available, capable LLM. DEPO’s current change view and analytics configuration extensions are not a complete enterprise CR/CO or global configuration provider.', size=9)

page('Engineering scenarios across discrete industries')
para('The following are applicability scenarios for a scoped deployment. They describe the business gap and how the knowledge layer can help when the relevant source records and mappings are available; they are not claims of installed sector-specific integrations.')
table(['Industry', 'Decision and information gap', 'How DEPO can help'], [
    ('Automotive and mobility', 'A component change needs context across variants, product revisions, requirements and manufacturing records.', 'Scope recorded dependencies, compare relevant versions and retain evidence for an engineering change review.'),
    ('Aerospace and defense', 'Design, requirement and verification information must be interpreted within an applicable configuration.', 'Connect supplied traceability and source evidence to the selected baseline; make missing links visible for accountable review.'),
    ('Industrial machinery', 'Part design, assembly structure and manufacturing process references are split across teams.', 'Explore connected product context, compare candidate parts and prepare governed portfolio or process evidence.'),
    ('HiTech electronics and telecom', 'Component classifications, engineering revisions and requirement references do not share one consistent vocabulary.', 'Align terminology, preserve source identity and support comparison and impact investigation across supplied records.'),
    ('Semiconductors and equipment', 'Equipment, design documents, component definitions and process references need consistent relationships.', 'Organize registered evidence and investigate dependencies. Design automation and EDA solver execution need separate tool integration.'),
], [1.30, 2.70, 2.8])
heading('A practical engineering change example')
para('A team selects an assembly part revision and asks what needs review if it changes. DEPO follows the recorded assembly, requirement and process paths, presents source evidence and identifies missing context. The engineer evaluates suitability and effectivity; the responsible workflow records the authorized scope and release outcome.')
heading('Measures for a pilot')
para('Compare time to assemble an impact review, effort to find authoritative source records, unresolved relationships and time to prepare a reusable analysis. Similarity is a reason to compare candidates, not proof of interchangeability.')

page('Process and regulated industry scenarios')
para('The same knowledge approach applies to equipment, materials, process definitions and quality evidence. Each vertical needs its own registered vocabulary, source access, identity rules and business acceptance criteria.')
table(['Industry', 'Decision and information gap', 'How DEPO can help'], [
    ('Oil and gas', 'Equipment information, engineering documents, activities and inspection references use different identifiers and classifications.', 'Use an industrial vocabulary to connect supplied equipment and document evidence, investigate change scope and identify missing associations.'),
    ('Energy and utilities', 'Asset design, requirements, maintenance references and project information are difficult to review together.', 'Retain a selected evidence baseline and expose recorded dependencies for technical and operational review.'),
    ('Food and beverages', 'Recipe or product specifications, ingredient references, process definitions and quality records are fragmented.', 'With supplied recipe, batch and quality data, establish reviewed relationships and prepare traceable analysis for the agreed process scope.'),
    ('Pharmaceuticals and life sciences', 'Specification, material, process and test evidence require consistent meaning and controlled versions.', 'Organize supplied evidence for review, show ownership and approval context, and retain lineage for a defined dataset or decision.'),
    ('Infrastructure and capital projects', 'Equipment, systems, requirements and engineering documents cross organizational and project boundaries.', 'Link available project evidence, inspect selected configurations and make the basis of handover or change review visible.'),
], [1.30, 2.70, 2.8])
heading('What must be established for each vertical')
para('Agree the business entities, source systems, applicable revisions and effective scope. Validate source relationships, units, KPI formulas and access. Register or integrate the required domain tools before claiming execution in them.')
para('These scenarios do not establish a live process-control system, a complete batch genealogy engine, a validated pharmaceutical application or regulatory compliance. Those outcomes require additional source integration, controls and formal customer validation. Existing supported engineering inputs offer the most direct starting point.')

page('DEPO in the AI led engineering landscape')
para('Engineering AI is moving toward agents that use domain tools and project context. Siemens describes agents working inside automation engineering systems; NVIDIA describes agents assembling engineering inputs for digital-twin preparation and downstream simulation. These developments reinforce the importance of usable context and engineering review. [2][3]')
heading('The functional role of DEPO')
para('DEPO contributes shared meaning, contextual graph evidence, governed worker execution and reusable data products around the supplied engineering information. It supports investigation and review; CAD generation, simulation, PLC programming or EDA automation must be delivered by separately integrated domain tools. References to other products do not imply a DEPO integration or endorsement.')
heading('Product merits for the enterprise')
para('A consistent vocabulary helps teams interpret records. Retained lineage and versions make the basis of an answer inspectable. Durable processing supports continuity across browser sessions. Governed analytics turn prepared records into owned datasets, reporting tables and supported KPIs. Separate authorization, execution and delivery states make release status clearer.')
para('Short-term conversation, reusable knowledge and recorded task execution serve different memory needs. Current graph-memory guidance also distinguishes these layers and makes clear that retained records do not automatically train a model. DEPO’s scoped context and reviewed lessons follow that practical distinction. [4]')
heading('Start with a measurable business problem')
para('Choose one product or asset scope and one decision: change impact, requirement traceability, classification/reuse or preparation of a governed analytics product. Confirm source coverage and ownership, rehearse the evidence path, and agree acceptance measures. Evaluate time to find evidence, review effort and data reuse against the customer’s baseline; no percentage return is assumed.')
heading('Further reading')
link('[1] PCA guidance on ontology based industrial interoperability', 'https://github.com/PCA-POSC-Caesar-Association/Public_ISO23726-1')
link('[2] Siemens Eigen Engineering Agent announcement 20 April 2026', 'https://press.siemens.com/global/en/pressrelease/siemens-launches-eigen-engineering-agent-bringing-purpose-built-ai-industrial')
link('[3] NVIDIA agent assisted digital twin workflow 21 October 2026', 'https://developer.nvidia.com/blog/developing-an-ai-factory-digital-twin-with-an-agent-assisted-workflow/')
link('[4] Neo4j explanation of agent memory types', 'https://neo4j.com/labs/agent-memory/explanation/memory-types/')
para('Product scope reviewed against the DEPO implementation on 2 November 2026. Capabilities depend on deployment configuration, supplied data, model availability and authorized workflows. Industry examples are illustrative; customer acceptance remains specific to the intended use.', size=8.5)

doc.core_properties.title = 'DEPO for AI Led Engineering'
doc.core_properties.subject = 'Industry ontology application ontology and business merits'
doc.core_properties.author = 'DEPO'
OUT.parent.mkdir(parents=True, exist_ok=True)
doc.save(OUT)
print(OUT.resolve())
