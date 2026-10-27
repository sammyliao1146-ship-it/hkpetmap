const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript');
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(module,file)=>module._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2021}}).outputText,file);
const {formatOpeningHours,formatActivityDates,initialLanguage,makeLanguage}=require('../src/language.tsx');
const html=fs.readFileSync(require.resolve('../index.html'),'utf8');assert.match(html,/<html lang="en-HK">/);assert.match(html,/<title>HK Pet Map \| Hong Kong Pet-Friendly Places &amp; Map<\/title>/);
global.window={location:{search:''}};global.localStorage={getItem:()=>null};assert.equal(initialLanguage(),'en','fresh visits should start in English');
global.window.location.search='?lang=zh-Hant';assert.equal(initialLanguage(),'zh-Hant','an explicit Cantonese link should be respected');
global.window.location.search='';global.localStorage={getItem:()=> 'zh-Hant'};assert.equal(initialLanguage(),'zh-Hant','a saved Cantonese choice should be respected');
global.window.location.search='?lang=en';assert.equal(initialLanguage(),'en','an explicit English link should override a saved Cantonese choice');
assert.equal(formatOpeningHours('星期一: 休息','en'),'Monday: Closed');
assert.equal(formatOpeningHours('星期日: 24 小時營業','en'),'Sunday: Open 24 hours');
assert.equal(formatOpeningHours('星期天: 全日營業','en'),'Sunday: Open 24 hours');
assert.equal(formatOpeningHours('星期一: 09:00 – 21:00','zh-Hant'),'星期一: 09:00 – 21:00');
assert.equal(formatActivityDates('2026年9月30日（星期三）– 10月31日 · 每日 2PM – 7PM','en'),'30 Sep 2026(Wednesday)– 31 Oct · Daily 2PM – 7PM');
assert.equal(formatActivityDates('2026年10月24日 · 下午 2 時至 6 時','en'),'24 Oct 2026 · 2–6 PM');
assert.equal(formatActivityDates('7 Nov 2026 (Sat) · 10:00-17:00','en'),'7 Nov 2026 (Sat) · 10:00-17:00');
const english=makeLanguage('en',()=>{});assert.equal(english.tx('粵語'),'Cantonese');assert.equal(english.districtName('旺角區'),'Mong Kok');assert.equal(english.districtName('油尖區'),'Yau Tsim');assert.equal(english.districtName('粉嶺區'),'Fanling');assert.equal(english.districtName('新界北區'),'New Territories North');assert(!/[\u3400-\u9fff]/.test(english.districtName('島中西及南區')));assert(!/[\u3400-\u9fff]/.test(english.errorText('未預期的新錯誤')));assert(english.errorText('意圖分類模型未設定。').includes('classifier'));assert.equal(english.placeName({name:'官方中文名',name_en:'Official English',restaurant_details:{display_name:'Google 店名'}}),'Google 店名');assert.equal(english.placeAddress({address:'中文地址',address_en:'English address'}),'English address');
const {renderToStaticMarkup}=require('react-dom/server');const React=require('react');const Icon=require('../src/components/Icon.tsx').default;
for(const name of ['directions','menu-book','reservation','phone','globe','paw','vet','boarding','park','pet-park','shared-park','animal-care','mall']){const html=renderToStaticMarkup(React.createElement(Icon,{name}));assert(html.includes('aria-hidden="true"')&&html.includes(`data-icon="${name}"`));assert(/<(path|circle|ellipse|rect)/.test(html),`Empty icon ${name}`);}
console.log('Language and icon checks passed: English hours/closed/24h, dynamic errors, Google-name priority, and 13 nonempty decorative SVG icons.');
