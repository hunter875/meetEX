import {execFileSync} from 'node:child_process';
import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
let info={source_commit:'unknown',source_clean:false};
if(existsSync(path.join(root,'BUILD_SOURCE.json')))info=JSON.parse(readFileSync(path.join(root,'BUILD_SOURCE.json'),'utf8'));
else try{
  info={source_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8',stdio:['ignore','pipe','ignore']}).trim(),source_clean:!execFileSync('git',['status','--porcelain','--untracked-files=no'],{cwd:root,encoding:'utf8'}).trim()};
}catch{/* An unidentified development build stays labelled unknown. */}
const version=JSON.parse(readFileSync(path.join(root,'package.json'),'utf8')).version;
writeFileSync(path.join(root,'extension/dist/build-info.json'),JSON.stringify({app_version:version,protocol_version:1,...info},null,2)+'\n');
