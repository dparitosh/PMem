import ast, hashlib, json, re, subprocess, sys
from pathlib import Path
ROOT=Path(r'C:\Users\Admin\Documents\Codex\2026-10-18\in\pmem-publish')
OUT=Path(r'C:\Users\Admin\Documents\Codex\2026-10-18\in\outputs\prompt-audit-20261028')
sys.path.insert(0,str(ROOT))
files=subprocess.check_output(['git','-c','safe.directory='+ROOT.as_posix(),'-C',str(ROOT),'ls-files'],text=True).splitlines()
files+=['backend/Services/ontology_semantic_runtime.py','backend/graph_service/vocabulary_evidence.py']
rows=[]; parse_errors=[]; sources={}; hits=[]
def add(path,line,kind,name,expr,variables=None):
    rows.append(dict(source=path,line=line,kind=kind,name=name,expression=expr,variables=variables or [],sha256=hashlib.sha256(expr.encode()).hexdigest()))
for relative in sorted(set(files)):
    p=ROOT/relative
    if not p.is_file() or not relative.startswith(('backend/','frontend/src/','standalone/','plugins/','infra/')):continue
    if '/tests/' in relative or relative.endswith(('.test.js','.test.ts')) or '/__pycache__/' in relative:continue
    if p.suffix not in ('.py','.js','.jsx','.json','.yaml','.yml','.ps1'):continue
    text=p.read_text(encoding='utf-8-sig');sources[relative]=hashlib.sha256(p.read_bytes()).hexdigest()
    for i,line in enumerate(text.splitlines(),1):
        if re.search(r'prompt|instructions|\bllm\b|ChatPromptTemplate|SystemMessage|HumanMessage|ReadGoalPanel|can_handoff',line,re.I):hits.append(dict(source=relative,line=i,text=line.strip()[:1800]))
    if p.suffix=='.py':
        try:tree=ast.parse(text)
        except SyntaxError as e:parse_errors.append(dict(source=relative,line=e.lineno));continue
        for node in ast.walk(tree):
            if isinstance(node,(ast.Assign,ast.AnnAssign,ast.AugAssign)):
                targets=node.targets if isinstance(node,ast.Assign) else [node.target]
                name=','.join(ast.unparse(t) for t in targets)
                if not re.search(r'prompt|instruction|template|\b(system|policy|output)\b',name,re.I):continue
                val=node.value
                if val is None:continue
                expr=ast.get_source_segment(text,val) or ast.unparse(val)
                if len(expr)<35:continue
                add(relative,node.lineno,'python-construction',name,expr,sorted({ast.unparse(x.value) for x in ast.walk(val) if isinstance(x,ast.FormattedValue)}))
            if isinstance(node,ast.Call):
                callee=ast.unparse(node.func)
                if any(x in callee for x in ('from_messages','from_template','SystemMessage','HumanMessage','prompt_messages')):
                    add(relative,node.lineno,'message-or-template',callee,ast.get_source_segment(text,node) or ast.unparse(node))
    elif p.suffix in ('.yaml','.yml'):
        # YAML block boundaries preserve exact template text without importing frameworks.
        lines=text.splitlines()
        for i,line in enumerate(lines):
            if re.match(r'^system_prompt\s*:',line):
                block=[]
                for child in lines[i+1:]:
                    if child and not child[0].isspace():break
                    block.append(child)
                add(relative,i+1,'yaml-agent','system_prompt','\n'.join(block))
    elif p.suffix=='.json':
        try:data=json.loads(text)
        except ValueError:continue
        if isinstance(data,dict):
            for agent in data.get('agents',[]):
                if 'system_prompt' in agent:
                    prompt=agent['system_prompt'];line=next((i for i,l in enumerate(text.splitlines(),1) if json.dumps(prompt,ensure_ascii=False) in l),1)
                    add(relative,line,'catalog-role',agent['id'],prompt)
    else:
        for i,line in enumerate(text.splitlines(),1):
            if re.search(r'(task=|recommendationTask|setTask\(|useState\([\x27\x22].*(?:Explain|Investigate|Find|Review)|TaskPrompt|Reply OK|Return JSON|system_prompt)',line):
                add(relative,i,'frontend-or-cli-task',relative+':'+str(i),line.strip())
from backend.agentic_service.catalog_loader import load_catalog
from backend.agentic_service.prompt_policy import proposal_instructions
catalog=load_catalog()
roles=[]
for a in catalog['agents']:
    for mode in ('structured','native'):
        prompt=proposal_instructions(a,mode)
        roles.append(dict(agent_id=a['id'],mode=mode,prompt=prompt,utf8_bytes=len(prompt.encode()),sha256=hashlib.sha256(prompt.encode()).hexdigest(),tools=a['tools'],generated=a['id'].startswith('dt-')))
(OUT/'source-inventory.json').write_text(json.dumps({'sources':sources,'prompts':rows,'parse_errors':parse_errors},indent=2,ensure_ascii=False),encoding='utf-8')
(OUT/'runtime-catalog.json').write_text(json.dumps({'roles':roles,'agents':catalog['agents'],'tools':catalog['tools'],'workflows':catalog['workflows']},indent=2,ensure_ascii=False),encoding='utf-8')
(OUT/'discovery-hits.json').write_text(json.dumps(hits,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps({'scanned_sources':len(sources),'prompt_candidates':len(rows),'lexical_hits':len(hits),'syntax_errors':parse_errors,'runtime_agents':len(catalog['agents']),'tools':len(catalog['tools']),'workflows':len(catalog['workflows'])}))
for r in rows:print(f"{r['source']}:{r['line']} | {r['kind']} | {r['name']}")
