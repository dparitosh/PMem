"""Build Nexus business literature using the bundled document Python runtime.

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
    st.font.color.rgb = RGBColor(0, 0, 0)
    st.paragraph_format.space_before, st.paragraph_format.space_after = Pt(11), Pt(7)
    st.paragraph_format.keep_with_next = True

header = section.header.paragraphs[0]
r = header.add_run('Nexus')
r.font.name, r.font.size, r.bold = 'Arial', Pt(9), True
r.font.color.rgb = RGBColor.from_string(TEAL)
footer = section.footer.paragraphs[0]
footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
r = footer.add_run('Business overview  •  3 November 2026  |  ')
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



doc.add_heading('Better product decisions with Nexus', 0)
para('Know what changes. See what needs review. Reuse what the business trusts.', True, 13)
para('For product leaders, engineers, manufacturing planners and quality teams', size=11)
para('A product change rarely belongs to one team. It may involve an assembly revision, a requirement, a manufacturing activity and inspection evidence. Nexus helps teams bring the relevant records together, understand their meaning and prepare a traceable basis for review.')
heading('Why the business needs it')
para('Today, people often spend the first part of a review finding information rather than evaluating it. Different names, unclear revisions and missing associations create repeated work. A familiar part name is not enough to judge reuse, and an AI answer is not useful unless the team can inspect its evidence.')
table(['Business question', 'How Nexus helps the team'],[
('What needs review if this part changes?', 'Investigate recorded assembly, requirement and process dependencies for the selected item.'),
('Could an existing part meet this need?', 'Compare classification, property values, declared units and source context.'),
('Where is the evidence incomplete?', 'Expose missing associations and unanswered questions for the responsible specialists.'),
('Which analysis can another team reuse?', 'Prepare records, review the intended use and publish an owned data product.'),
], [2.6,4.2])
heading('A practical engineering change example')
para('A bearing design changes within a motor assembly. The engineer selects the intended revision, inspects recorded parent assemblies, follows requirement and process references, and reviews the supporting evidence. The team decides what needs further investigation and records the permitted action. Missing links remain questions; they do not prove that there is no impact.')
heading('Value to measure')
para('Measure the time to assemble an impact review, locate authoritative records and compare reusable designs. Compare the pilot with the current process; do not assume a percentage saving or a guaranteed return.')

page('A common product story across disciplines')
para('Product, systems engineering, manufacturing and quality teams each see part of the same story. Nexus connects supplied business records through reviewed definitions and relationships while retaining their source identity.')
table(['Business view', 'What the team can review'],[
('Product and portfolio','Products, families, assemblies and the part revisions within the selected scope.'),
('Systems engineering / MBSE','Available requirement, model and product relationships. Traceability is distinct from satisfaction evidence.'),
('Manufacturing','Recorded parent/child part relationships and process or activity assignments.'),
('Quality','Supplied specification, characteristic or inspection evidence with established ownership and source associations.'),
], [2.1,4.7])
heading('Industry ontology, in business terms')
para('An ontology defines concepts and how they relate. A physical part differs from its design. A requirement differs from evidence that it was satisfied. The embedded industrial reference and application business definitions help teams preserve these distinctions. Customer vocabulary is aligned through reviewed mappings rather than treating similar names as equivalent.')
heading('Who does what')
table(['Role', 'Contribution to the business workflow'],[
('Business owner and specialists','Set the intended use, review fitness for use and authorize the release scope.'),
('Governor agent','Coordinates mapping or merge proposals and the authorized publication workflow.'),
('Steward agent','Assesses meaning, ambiguity and retained validation evidence; explains accepted and held findings.'),
('Workers','Carry out authorized processing and retain results while people focus on review.'),
], [2.1,4.7])
para('The public industrial ontology snapshot supports shared meaning; it does not establish ISO certification or approved alignment to a customer domain.', size=9)

page('Industry scenarios: the question comes first')
para('These are applicability scenarios. Each needs the customer’s records, domain definitions, reviewed mappings and acceptance criteria. They are not claims of preconfigured sector solutions.')
table(['Industry', 'Business decision and functional journey'],[
('HiTech','A component revision changes. Select the intended component, trace recorded product and requirement references, compare candidates and prepare an engineering review. Measure search and comparison effort.'),
('Oil and gas','An equipment specification changes. Bring supplied equipment, engineering document and activity records into a shared context. Help specialists identify related evidence and unresolved associations.'),
('Food and beverages','A product specification changes. Establish reviewed product, ingredient, process and quality references within the agreed scope. Help development and quality teams inspect the evidence chain.'),
('Pharma and life sciences','A material or specification is reviewed. Organize supplied material, process and test evidence by version, ownership and recorded relationships for accountable specialist review.'),
], [1.65,5.15])
heading('The business journey')
for t in (
'Choose the product or operational question and the responsible reviewer.',
'Bring the relevant records together and confirm terms, revisions and scope.',
'Investigate recorded relationships and make missing evidence visible.',
'Review the proposal, authorize the intended action and verify its outcome.',
'Share the released result with ownership and source references.',
):doc.add_paragraph(t,style='List Number')
heading('Keep the decision boundary clear')
para('Similarity is not interchangeability. Recorded traceability is not requirement satisfaction. Observed links do not certify a complete BOM or manufacturing readiness. Nexus supports evidence review; it does not by itself certify food safety, regulatory compliance, GxP validation or batch release.')

page('From useful answers to reusable business knowledge')
heading('Conversation with the right context')
para('A user asks about a selected product and follows up about its requirements or properties. Nexus keeps relevant conversation context within the authorized business scope, retrieves fresh evidence and presents business names, descriptions, property values and source references. Approved, revision-scoped mapping lessons can support later reviews as advisory guidance. Live language generation requires an available, configured model; retained memory is not model training.')
heading('Business analytics and data products')
para('A portfolio team chooses registered business records, prepares a retained analysis snapshot and selects reporting dimensions. The team agrees measure definitions, denominators, units, revisions and effectivity before interpreting results. Reviewed tables and results can then be published as an owned product for discovery and reuse. Supported reporting models still require business review; there is no universal automatic KPI library.')
heading('Know what was approved, executed and released')
para('Change Control brings together status and links to the responsible review workflow. A recommendation is a proposal, approval grants authority for a scope, and publication evidence confirms the retained outcome. These states remain distinct; central visibility does not replace a full enterprise change-request/change-order process.')
heading('Keep a baseline when information changes')
para('Retained source versions and declared references show what supported a result. Supported Tracked Resource Set (TRS) notifications and source reconciliation can identify refresh needs. A change prompts review rather than silently authorizing another release. This is scoped baseline support, not global enterprise configuration management.')
heading('Start with one decision worth improving')
table(['Pilot focus', 'Agree how success will be assessed'],[
('Change review','Time to assemble the review and resolve missing associations.'),
('Reuse and reporting','Effort to compare candidates and prepare a reusable analysis.'),
('Accountability','Availability of owner, source/version, review outcome and publication evidence.'),
], [2.1,4.7])
para('Demonstrate one real product question, one governed review and one reusable analysis. Expand to another domain after the business accepts the first scenario.')
page('Connected business views and responsibilities')
heading('One shared meaning across product domains')
doc.add_picture('tools/documentation/assets/business-domains.png', width=Inches(6.8))
para('Conceptual view: connections depend on supplied business records and reviewed mappings.', size=9)
heading('People, agents and workers in the review')
doc.add_picture('tools/documentation/assets/agent-review.png', width=Inches(6.8))
para('Business authority remains with the authorized reviewer. A held proposal remains unpublished.', size=9)
page('Context, memory and controlled release')
heading('Remember the right context; retrieve fresh evidence')
doc.add_picture('tools/documentation/assets/contextual-memory.png', width=Inches(6.8))
para('Current conversation and approved mapping lessons serve different purposes. Neither is automatic model training.', size=9)
heading('From proposed change to a verified outcome')
doc.add_picture('tools/documentation/assets/change-approval.png', width=Inches(6.8))
para('Review, authorization, execution and publication are distinct states. Inspect the retained outcome before use.', size=9)
OUT.parent.mkdir(parents=True,exist_ok=True)
doc.save(OUT)
print(OUT)
