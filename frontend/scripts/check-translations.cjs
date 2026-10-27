const fs=require('node:fs');const path=require('node:path');const ts=require('typescript');
const root=path.resolve(__dirname,'../src');
const dict=ts.createSourceFile('en.ts',fs.readFileSync(path.join(root,'locales/en.ts'),'utf8'),ts.ScriptTarget.Latest,true);
const keys=new Set(),errors=[];const han=/[\u3400-\u9fff]/;let calls=0,conditional=0,labels=0;
for(const st of dict.statements){if(!ts.isVariableStatement(st))continue;for(const d of st.declarationList.declarations){if(d.name.getText(dict)!=='en'||!d.initializer||!ts.isObjectLiteralExpression(d.initializer))continue;for(const p of d.initializer.properties){if(!ts.isPropertyAssignment(p)||!p.name||!ts.isStringLiteral(p.name))continue;if(keys.has(p.name.text))errors.push(`locales/en.ts: duplicate ${p.name.text}`);keys.add(p.name.text);if(ts.isStringLiteral(p.initializer)&&han.test(p.initializer.text))errors.push(`locales/en.ts: English value still contains Chinese: ${p.name.text}`);}}}
function files(dir){return fs.readdirSync(dir,{withFileTypes:true}).flatMap(e=>e.isDirectory()?files(path.join(dir,e.name)):/\.tsx?$/.test(e.name)?[path.join(dir,e.name)]:[]);}
function translatedLiterals(node){if(ts.isStringLiteral(node)||ts.isNoSubstitutionTemplateLiteral(node))return [node.text];if(ts.isConditionalExpression(node)){conditional++;return [...translatedLiterals(node.whenTrue),...translatedLiterals(node.whenFalse)];}return [];}
for(const file of files(root)){
 if(file.includes('/locales/'))continue;
 const ast=ts.createSourceFile(file,fs.readFileSync(file,'utf8'),ts.ScriptTarget.Latest,true,file.endsWith('.tsx')?ts.ScriptKind.TSX:ts.ScriptKind.TS);
 const report=text=>errors.push(`${path.relative(root,file)}: ${text}`);
 function check(value){if(!keys.has(value))report(`missing ${value}`);}
 function visit(n){
  if(ts.isCallExpression(n)&&n.expression.getText(ast)==='tx'&&n.arguments[0]){calls++;translatedLiterals(n.arguments[0]).forEach(check);}
  if(ts.isPropertyAssignment(n)&&['label','question'].includes(n.name.getText(ast))&&ts.isStringLiteral(n.initializer)&&han.test(n.initializer.text)){labels++;check(n.initializer.text);}
  if(ts.isJsxText(n)&&han.test(n.getText(ast)))report(`untranslated JSX text ${n.getText(ast).trim()}`);
  if(ts.isJsxAttribute(n)&&n.initializer&&ts.isStringLiteral(n.initializer)&&han.test(n.initializer.text))report(`untranslated attribute ${n.initializer.text}`);
  ts.forEachChild(n,visit);
 }
 visit(ast);
}
if(errors.length){console.error(errors.join('\n'));process.exit(1);}
console.log(`Translation coverage passed: ${keys.size} English entries, ${calls} translation calls, ${conditional} conditional branches, ${labels} dynamic labels, no Chinese English values.`);
