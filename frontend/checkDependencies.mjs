import {readFileSync,existsSync} from 'node:fs';
import {dirname,join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
export function checkDependencies(root) {
  const manifest=JSON.parse(readFileSync(join(root,'package.json'),'utf8'));
  const lock=JSON.parse(readFileSync(join(root,'package-lock.json'),'utf8'));
  const mismatches=[];
  for(const name of Object.keys({...manifest.dependencies,...manifest.devDependencies})) {
    if(!/^(?:@[a-z0-9_.-]+\/)?[a-z0-9_.-]+$/i.test(name))throw new Error('Invalid package name');
    const path=join(root,'node_modules',name,'package.json');
    const expected=lock.packages?.[`node_modules/${name}`]?.version;
    let actual;
    try { if(existsSync(path))actual=JSON.parse(readFileSync(path,'utf8')).version; } catch { /* Unreadable installs need repair. */ }
    if(!expected || actual!==expected)mismatches.push(name);
  }
  return {current:mismatches.length===0,mismatches};
}
if(process.argv[1] && resolve(process.argv[1])===fileURLToPath(import.meta.url))
 console.log(JSON.stringify(checkDependencies(dirname(fileURLToPath(import.meta.url)))));
