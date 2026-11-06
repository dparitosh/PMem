export function bundleAuditPlugin() {
  return {name:'depo-bundle-audit',generateBundle(_options,bundle){
    const chunks=Object.values(bundle).filter(item=>item.type==='chunk').map(item=>({
      file:item.fileName,entry:item.isEntry,bytes:Buffer.byteLength(item.code),imports:item.imports,
      largestModules:Object.entries(item.modules).map(([id,value])=>({
        name:id.replaceAll('\\','/').split('/node_modules/').at(-1).split('/src/').at(-1),bytes:value.renderedLength,
      })).sort((a,b)=>b.bytes-a.bytes).slice(0,15),
    }));
    this.emitFile({type:'asset',fileName:'depo-bundle-analysis.json',source:JSON.stringify({chunks},null,2)});
  }};
}
