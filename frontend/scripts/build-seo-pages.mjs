import {createHash} from 'node:crypto';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {dirname, join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const scriptDir = dirname(fileURLToPath(import.meta.url));
const frontendDir = resolve(scriptDir, '..');
const repoDir = resolve(frontendDir, '..');
const distDir = join(frontendDir, 'dist');
const siteOrigin = 'https://hkpetmap.com';
const pageSize = 80;
const snapshotPath = join(repoDir, 'data', 'pet-snapshot.json');

const categoryInfo = {
  restaurants: {
    slug: 'dog-friendly-restaurants', en: 'Dog-friendly restaurants', zh: '狗友善餐廳',
    intro: 'Browse restaurant records whose source permits dogs. A dog-entry listing does not automatically cover cats or other pets; confirm current rules with the restaurant before visiting.',
    introZh: '瀏覽來源列明可讓狗隻進入的食肆。准許狗隻進入不代表接受其他寵物；出發前請向餐廳確認最新入場安排。',
  },
  parks: {
    slug: 'public-parks', en: 'Public parks', zh: '一般公園',
    intro: 'These records describe public parks and facilities. A general park listing does not confirm that pets are permitted; check official venue notices before visiting.',
    introZh: '此分類列出一般公園及設施資料。列入一般公園不代表准許攜帶寵物；出發前請查閱場地告示及官方守則。',
  },
  pet_parks: {
    slug: 'pet-parks', en: 'Pet parks', zh: '寵物公園',
    intro: 'Browse designated pet-park records and the facilities listed by their sources. Follow posted rules and check the source for current arrangements.',
    introZh: '瀏覽寵物公園及來源列明的設施。請遵守場地告示，並向資料來源核實最新安排。',
  },
  inclusive_parks: {
    slug: 'parks-with-pet-areas', en: 'Parks with designated pet areas', zh: '設有寵物共享位置的公園',
    intro: 'These parks have source-listed designated areas for pets. Access may be limited to marked zones; follow onsite signs and the linked venue rules.',
    introZh: '這些公園的來源資料列有寵物指定位置。攜寵範圍可能只限指定區域，請遵守場內告示及連結中的場地守則。',
  },
  vets: {
    slug: 'veterinary-clinics', en: 'Veterinary clinics', zh: '獸醫診所',
    intro: 'Browse veterinary clinic entries from the linked public directory. A directory entry is not a licensing certification or endorsement; call ahead to confirm accepted animals and emergency services.',
    introZh: '瀏覽連結公共名錄中的獸醫診所資料。列入名錄不代表牌照認證或推薦；前往前請致電確認接診動物及急症服務。',
  },
  hotels: {
    slug: 'pet-boarding', en: 'Pet boarding', zh: '寵物寄養',
    intro: 'Browse listed animal boarding establishments. The source list is not a complete directory; contact each establishment about accepted animals, availability and fees.',
    introZh: '瀏覽名錄內的動物寄養所。來源名單並非全港完整名錄；請直接向寄養所查詢接收動物種類、房位及收費。',
  },
  malls: {
    slug: 'pet-friendly-malls', en: 'Shopping malls and pet access', zh: '商場攜寵資料',
    intro: 'Browse malls with published pet-access notes. Rules may differ between mall zones and individual shops; read the linked policy and confirm with the venue.',
    introZh: '瀏覽有公開攜寵資料的商場。商場不同區域及個別商戶的規則可能不同，請查閱政策連結並向場地確認。',
  },
  management: {
    slug: 'animal-management-services', en: 'Animal management services', zh: '動物管理服務',
    intro: 'Find listed animal management, licensing or inoculation facilities. Check the linked official source for service details and opening arrangements before travelling.',
    introZh: '查找名錄中的動物管理、領牌或注射設施。出發前請查閱官方來源，確認服務詳情及開放安排。',
  },
  transport: {
    slug: 'pet-transport', en: 'Pet transport', zh: '攜寵交通',
    intro: 'Browse transport services and places with published pet-carriage information. Conditions can vary by route and service; confirm current rules with the operator before boarding.',
    introZh: '瀏覽有公開攜寵安排的交通服務及地點。不同路線及服務的條件可能有別，乘搭前請向營辦商確認最新守則。',
  },
};

const districtNamesEn = {
  '中西區': 'Central and Western', '東區': 'Eastern', '南區': 'Southern', '灣仔區': 'Wan Chai',
  '九龍城區': 'Kowloon City', '觀塘區': 'Kwun Tong', '深水埗區': 'Sham Shui Po', '黃大仙區': 'Wong Tai Sin',
  '油尖旺區': 'Yau Tsim Mong', '離島區': 'Islands', '葵青區': 'Kwai Tsing', '北區': 'North',
  '西貢區': 'Sai Kung', '沙田區': 'Sha Tin', '大埔區': 'Tai Po', '荃灣區': 'Tsuen Wan',
  '屯門區': 'Tuen Mun', '元朗區': 'Yuen Long', '油尖區': 'Yau Tsim', '旺角區': 'Mong Kok',
  '新界北': 'Northern New Territories', '粉嶺': 'Fanling', '島中西及南區': 'Central, Western and Southern Hong Kong Island',
};

const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[char]));
const safeUrl = (value) => {
  if (typeof value !== 'string') return '';
  try {
    const url = new URL(value);
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : '';
  } catch { return ''; }
};
const slugify = (value) => String(value ?? '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '')
  .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 72).replace(/-+$/g, '');
const idHash = (value) => createHash('sha256').update(String(value)).digest('hex').slice(0, 10);
const districtSlug = (district) => slugify(districtNamesEn[district] || district) || idHash(district);
const pagePath = (route) => route.endsWith('/') ? route : `${route}/`;
const datePart = (value) => {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? null : date.toISOString().slice(0, 10);
};
const snapshot = JSON.parse(await readFile(snapshotPath, 'utf8'));
if (!Array.isArray(snapshot.places) || snapshot.places.length === 0) {
  throw new Error(`No places found in ${snapshotPath}`);
}
const lastmod = datePart(snapshot.published_at) || datePart(snapshot.fetched_at);
const sitemapEntries = new Map();
const generatedFiles = [];

function registerPage(route, title, description, body, {lastModified = lastmod, htmlLang = 'en-HK'} = {}) {
  const pathname = pagePath(route);
  const canonicalUrl = `${siteOrigin}${pathname}`;
  const page = `<!doctype html>
<html lang="${escapeHtml(htmlLang)}"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${escapeHtml(title)}</title><meta name="description" content="${escapeHtml(description)}"><link rel="canonical" href="${escapeHtml(canonicalUrl)}">
<meta property="og:type" content="website"><meta property="og:site_name" content="HK PetFinder"><meta property="og:title" content="${escapeHtml(title)}"><meta property="og:description" content="${escapeHtml(description)}"><meta property="og:url" content="${escapeHtml(canonicalUrl)}">
<style>
:root{color-scheme:light;--ink:#26332a;--muted:#617064;--green:#286b47;--line:#e1e8df;--surface:#f7faf6}*{box-sizing:border-box}body{margin:0;background:#fff;color:var(--ink);font:16px/1.65 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{max-width:900px;margin:0 auto;padding:28px 22px 64px}a{color:var(--green);text-underline-offset:3px}.skip{position:absolute;left:-9999px}.skip:focus{left:16px;top:12px;background:#fff;padding:8px}.top{display:flex;justify-content:space-between;gap:16px;align-items:center;padding:0 0 20px;border-bottom:1px solid var(--line)}.brand{font-weight:750;color:var(--ink);text-decoration:none}.crumbs{font-size:14px;color:var(--muted);margin:22px 0}.crumbs a{color:inherit}h1{font-size:clamp(30px,5vw,44px);line-height:1.15;margin:10px 0 12px;letter-spacing:-.025em}h2{font-size:22px;margin:28px 0 12px}.intro{font-size:18px;max-width:760px}.zh{color:#46564a}.notice{border-left:4px solid #e6aa47;background:#fff9ec;padding:12px 16px;margin:18px 0}.list{list-style:none;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}.card{border:1px solid var(--line);border-radius:12px;padding:14px 16px;background:#fff}.card h2{font-size:17px;margin:0 0 5px}.card p{margin:4px 0;color:var(--muted);font-size:14px}.tags{color:var(--muted);font-size:14px}.facts{display:grid;grid-template-columns:minmax(120px,180px) 1fr;gap:8px 16px;margin:20px 0}.facts dt{font-weight:650}.facts dd{margin:0;white-space:pre-line}.notes{padding-left:22px}.actions{display:flex;flex-wrap:wrap;gap:12px;margin:20px 0}.button{display:inline-block;border:1px solid #cddbcf;border-radius:9px;padding:9px 13px;text-decoration:none;font-weight:650}.pagination{display:flex;flex-wrap:wrap;gap:8px;margin:22px 0}.pagination a,.pagination span{border:1px solid var(--line);border-radius:7px;padding:6px 10px;text-decoration:none}.pagination [aria-current]{background:var(--green);color:#fff;border-color:var(--green)}footer{border-top:1px solid var(--line);margin-top:36px;padding-top:18px;color:var(--muted);font-size:13px}@media(max-width:600px){main{padding:18px 16px 48px}.facts{grid-template-columns:1fr;gap:2px}.facts dd{margin-bottom:10px}.top{align-items:flex-start}}
</style></head><body><a class="skip" href="#main">Skip to content</a><main id="main">${body}<footer><p>Place information comes from the linked source. Conditions and opening details can change; verify with the venue before travelling.</p><p><a href="/">HK PetFinder interactive map</a> · <a href="/sitemap.xml">XML sitemap</a></p></footer></main></body></html>`;
  sitemapEntries.set(pathname, lastModified);
  const outputPath = join(distDir, pathname.replace(/^\//, ''), 'index.html');
  generatedFiles.push((async () => {
    await mkdir(dirname(outputPath), {recursive: true});
    await writeFile(outputPath, page);
  })());
}

function breadcrumb(items) {
  return `<nav class="crumbs" aria-label="Breadcrumb">${items.map((item, index) => `${index ? ' › ' : ''}${item.href ? `<a href="${escapeHtml(item.href)}">${escapeHtml(item.label)}</a>` : escapeHtml(item.label)}`).join('')}</nav>`;
}

function pageLinks(items, currentPage, totalPages, routeForPage) {
  if (totalPages <= 1) return '';
  const min = Math.max(1, currentPage - 2), max = Math.min(totalPages, currentPage + 2);
  const links = [];
  if (currentPage > 1) links.push(`<a rel="prev" href="${escapeHtml(routeForPage(currentPage - 1))}">← Previous</a>`);
  for (let n = min; n <= max; n++) links.push(n === currentPage
    ? `<span aria-current="page">${n}</span>`
    : `<a href="${escapeHtml(routeForPage(n))}">${n}</a>`);
  if (currentPage < totalPages) links.push(`<a rel="next" href="${escapeHtml(routeForPage(currentPage + 1))}">Next →</a>`);
  return `<nav class="pagination" aria-label="Page navigation">${links.join('')}</nav>`;
}

function placeDisplayName(place) {
  return place.name_en?.trim() || place.name?.trim() || 'Unnamed place';
}
function placeCard(place) {
  const path = placePaths.get(place.id);
  const name = placeDisplayName(place);
  const district = place.district || '';
  const districtEn = districtNamesEn[district] || district.replace(/區$/, '');
  const address = place.address_en || place.address || '';
  const chineseName = place.name && place.name !== name ? ` · ${place.name}` : '';
  const info = [districtEn, address].filter(Boolean).join(' · ');
  return `<li class="card"><h2><a href="${escapeHtml(path)}">${escapeHtml(name)}</a></h2>${chineseName ? `<p lang="zh-HK">${escapeHtml(chineseName.slice(3))}</p>` : ''}<p>${escapeHtml(info)}</p><p class="tags">${escapeHtml(categoryInfo[place.category]?.en || place.category)}</p></li>`;
}

const seenIds = new Set();
const placePaths = new Map();
for (const place of snapshot.places) {
  if (!place || typeof place.id !== 'string' || !place.id || seenIds.has(place.id)) {
    throw new Error(`Invalid or duplicate place id: ${place?.id ?? '(missing)'}`);
  }
  seenIds.add(place.id);
  const category = categoryInfo[place.category] ? place.category : 'places';
  const nameSlug = slugify(placeDisplayName(place)) || category;
  placePaths.set(place.id, pagePath(`/places/${nameSlug}-${idHash(place.id)}`));
}

function fact(label, value) {
  if (!value) return '';
  return `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd>`;
}
function linkFact(label, value, linkLabel = 'Open source ↗') {
  const href = safeUrl(value);
  if (!href) return '';
  return `<dt>${escapeHtml(label)}</dt><dd><a href="${escapeHtml(href)}" rel="noopener noreferrer">${escapeHtml(linkLabel)}</a></dd>`;
}

for (const place of snapshot.places) {
  const category = categoryInfo[place.category] || {en: place.category, zh: place.category};
  const name = placeDisplayName(place);
  const nameZh = place.name && place.name !== name ? place.name : '';
  const path = placePaths.get(place.id);
  const categoryPath = pagePath(`/categories/${category.slug || slugify(category.en)}`);
  const districtPath = place.district ? pagePath(`/districts/${districtSlug(place.district)}`) : '';
  const address = place.address_en || place.address || '';
  const addressZh = place.address && place.address !== address ? place.address : '';
  const categoryCaution = {
    restaurants: ['Confirm the restaurant’s current pet-entry rules. Dog permission does not automatically cover other animals.', '請先向餐廳確認最新攜寵安排；准許狗隻進入不代表接受其他動物。'],
    parks: ['This is a general park record; it does not confirm pet access. Check official signs and rules.', '此為一般公園資料，並不代表准許攜帶寵物；請查閱官方告示及守則。'],
    inclusive_parks: ['Pet access may be limited to designated areas. Follow signs and venue rules.', '攜寵範圍可能只限指定位置，請遵守場地告示及守則。'],
    hotels: ['Contact the establishment to confirm accepted animals, prices and availability.', '請向寄養所確認接收動物種類、收費及房位。'],
    vets: ['Call ahead to confirm accepted species, opening hours and emergency care.', '前往前請致電確認接診動物、營業時間及急症服務。'],
    malls: ['Rules may differ by mall zone and individual shop. Check the linked policy.', '商場不同區域及個別商戶的規則可能不同，請查閱政策連結。'],
    transport: ['Pet-carriage conditions vary. Confirm current route and boarding rules with the operator.', '攜寵條件可能因路線而異，乘搭前請向營辦商核實。'],
  }[place.category] || ['Check the linked official information for current service details.', '請查閱連結中的官方資料，確認最新服務安排。'];
  const mapUrl = Number.isFinite(place.latitude) && Number.isFinite(place.longitude)
    ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${place.latitude},${place.longitude}`)}` : '';
  const noteEn = Array.isArray(place.notes_en) ? place.notes_en.filter(Boolean) : [];
  const noteZh = Array.isArray(place.notes) ? place.notes.filter(Boolean) : [];
  const title = `${name}${place.district ? `, ${districtNamesEn[place.district] || place.district}` : ''} · HK PetFinder`;
  const description = `${name} in Hong Kong: ${category.en.toLowerCase()} details, address, source and pet-access notes. Check current rules with the venue.`.slice(0, 155);
  const facts = [
    fact('Category', category.en), fact('District / area', place.district ? (districtNamesEn[place.district] || place.district) : ''),
    fact('Address', address), fact('Address (中文)', addressZh), fact('Cuisine', Array.isArray(place.cuisines) ? place.cuisines.join(', ') : ''),
    fact('Opening hours', place.opening_hours_en || place.opening_hours || ''),
    fact('Telephone', place.telephone || ''), fact('Licence number', place.licence_number || ''),
    linkFact('Venue website', place.website_en || place.website, 'Visit venue website ↗'),
    linkFact('Pet-access rules', place.rules_url_en || place.rules_url, 'Read venue rules ↗'),
    linkFact('Official / listing source', place.source_url, `Source: ${place.source_name_en || place.source_name || 'listing'}`),
    linkFact('Map location', mapUrl, 'Open coordinates in Google Maps ↗'),
  ].filter(Boolean).join('');
  const body = `${breadcrumb([{label:'Home',href:'/'},{label:category.en,href:categoryPath},{label:name}])}
<article><header><p class="tags">${escapeHtml(category.en)}${place.district ? ` · ${escapeHtml(districtNamesEn[place.district] || place.district)}` : ''}</p><h1>${escapeHtml(name)}</h1>${nameZh ? `<p class="zh" lang="zh-HK">${escapeHtml(nameZh)}</p>` : ''}<p class="notice">${escapeHtml(categoryCaution[0])}<br><span lang="zh-HK">${escapeHtml(categoryCaution[1])}</span></p><div class="actions">${mapUrl ? `<a class="button" href="${escapeHtml(mapUrl)}" rel="noopener noreferrer">Open location in Google Maps ↗</a>` : ''}<a class="button" href="${escapeHtml(categoryPath)}">Browse ${escapeHtml(category.en.toLowerCase())}</a>${districtPath ? `<a class="button" href="${escapeHtml(districtPath)}">Browse ${escapeHtml(districtNamesEn[place.district] || place.district)}</a>` : ''}</div></header>
<section><h2>Place information</h2><dl class="facts">${facts}</dl>${noteEn.length ? `<h2>Notes from the source</h2><ul class="notes">${noteEn.map((n) => `<li>${escapeHtml(n)}</li>`).join('')}</ul>` : ''}${noteZh.length ? `<h2 lang="zh-HK">資料來源備註</h2><ul class="notes" lang="zh-HK">${noteZh.map((n) => `<li>${escapeHtml(n)}</li>`).join('')}</ul>` : ''}</section></article>`;
  registerPage(path, title, description, body);
}

const placesByCategory = new Map();
const placesByDistrict = new Map();
for (const place of snapshot.places) {
  placesByCategory.set(place.category, [...(placesByCategory.get(place.category) || []), place]);
  if (place.district?.trim()) placesByDistrict.set(place.district.trim(), [...(placesByDistrict.get(place.district.trim()) || []), place]);
}
const sortPlaces = (places) => [...places].sort((a, b) => placeDisplayName(a).localeCompare(placeDisplayName(b), 'en'));

for (const [key, places] of placesByCategory) {
  const info = categoryInfo[key] || {slug: slugify(key), en: key, zh: key, intro: 'Browse places in this category.', introZh: '瀏覽此分類的場地。'};
  const sorted = sortPlaces(places);
  const totalPages = Math.ceil(sorted.length / pageSize);
  for (let page = 1; page <= totalPages; page++) {
    const routeBase = `/categories/${info.slug}`;
    const route = page === 1 ? pagePath(routeBase) : pagePath(`${routeBase}/page/${page}`);
    const pagePlaces = sorted.slice((page - 1) * pageSize, page * pageSize);
    const title = `${info.en}${page > 1 ? ` · Page ${page}` : ''} | Hong Kong Pet Map`;
    const description = `${info.intro} Browse ${sorted.length} listed places across Hong Kong${page > 1 ? ` (page ${page})` : ''}.`;
    const body = `${breadcrumb([{label:'Home',href:'/'},{label:'Categories',href:'/categories/'},{label:info.en}])}
<header><p class="tags">${sorted.length} listed places${page > 1 ? ` · Page ${page} of ${totalPages}` : ''}</p><h1>${escapeHtml(info.en)}</h1><p class="intro">${escapeHtml(info.intro)}</p><p class="intro zh" lang="zh-HK">${escapeHtml(info.introZh)}</p></header>
<section><h2>Places in this category</h2><ul class="list">${pagePlaces.map(placeCard).join('')}</ul>${pageLinks(pagePlaces, page, totalPages, (n) => n === 1 ? pagePath(routeBase) : pagePath(`${routeBase}/page/${n}`))}</section>
<p>Browse by <a href="/districts/">district or area</a>, or return to the <a href="/">interactive map</a> for filters and map search.</p>`;
    registerPage(route, title, description, body);
  }
}

const districtRouteByName = new Map();
for (const district of placesByDistrict.keys()) districtRouteByName.set(district, pagePath(`/districts/${districtSlug(district)}`));
for (const [district, places] of placesByDistrict) {
  const en = districtNamesEn[district] || district.replace(/區$/, '');
  const sorted = sortPlaces(places);
  const totalPages = Math.ceil(sorted.length / pageSize);
  const routeBase = `/districts/${districtSlug(district)}`;
  for (let page = 1; page <= totalPages; page++) {
    const route = page === 1 ? pagePath(routeBase) : pagePath(`${routeBase}/page/${page}`);
    const title = `Pet places and services in ${en}${page > 1 ? ` · Page ${page}` : ''} | HK PetFinder`;
    const description = `Browse ${sorted.length} place records for ${en}, Hong Kong, with addresses, source links and pet-access notes${page > 1 ? ` (page ${page})` : ''}.`;
    const body = `${breadcrumb([{label:'Home',href:'/'},{label:'Districts and areas',href:'/districts/'},{label:en}])}
<header><p class="tags">${sorted.length} listed records${page > 1 ? ` · Page ${page} of ${totalPages}` : ''}</p><h1>Pet places and services in ${escapeHtml(en)}</h1><p class="intro">Browse the Pet Map records carrying the area label <span lang="zh-HK">${escapeHtml(district)}</span>. The label follows the source data and may describe an area rather than an administrative district.</p><p class="intro zh" lang="zh-HK">瀏覽資料來源標示為「${escapeHtml(district)}」的場地。此地區名稱沿用來源資料，可能是地區範圍而非行政區。</p></header>
<section><h2>Places in this area</h2><ul class="list">${sorted.slice((page - 1) * pageSize, page * pageSize).map(placeCard).join('')}</ul>${pageLinks(sorted, page, totalPages, (n) => n === 1 ? pagePath(routeBase) : pagePath(`${routeBase}/page/${n}`))}</section>
<p>Browse the <a href="/categories/">category directory</a> or return to the <a href="/">interactive map</a>.</p>`;
    registerPage(route, title, description, body);
  }
}

const categoryCards = [...placesByCategory.entries()].map(([key, places]) => {
  const info = categoryInfo[key] || {slug: slugify(key), en: key, zh: key};
  return `<li class="card"><h2><a href="${escapeHtml(pagePath(`/categories/${info.slug}`))}">${escapeHtml(info.en)}</a></h2><p lang="zh-HK">${escapeHtml(info.zh)}</p><p>${places.length} listed places</p></li>`;
}).join('');
registerPage('/categories/', 'Browse place categories | HK PetFinder', 'Browse Hong Kong pet places by category, including restaurants, parks, veterinary clinics, boarding and transport.',
  `${breadcrumb([{label:'Home',href:'/'},{label:'Categories'}])}<header><h1>Browse place categories</h1><p class="intro">Find Hong Kong places by facility type. Each listing links to its source and includes notes to help you verify access before visiting.</p><p class="intro zh" lang="zh-HK">按設施類型瀏覽香港場地。各項資料附有來源連結及攜寵備註，出發前請向場地核實。</p></header><ul class="list">${categoryCards}</ul><p>Or <a href="/districts/">browse by district or area</a>.</p>`);

const districtCards = [...placesByDistrict.entries()].sort(([a], [b]) => (districtNamesEn[a] || a).localeCompare(districtNamesEn[b] || b, 'en')).map(([district, places]) => {
  const en = districtNamesEn[district] || district.replace(/區$/, '');
  return `<li class="card"><h2><a href="${escapeHtml(districtRouteByName.get(district))}">${escapeHtml(en)}</a></h2><p lang="zh-HK">${escapeHtml(district)}</p><p>${places.length} listed records</p></li>`;
}).join('');
registerPage('/districts/', 'Browse pet places by district | HK PetFinder', 'Browse Hong Kong pet places and services by the district or area label recorded in each data source.',
  `${breadcrumb([{label:'Home',href:'/'},{label:'Districts and areas'}])}<header><h1>Browse districts and areas</h1><p class="intro">Choose a district or area to browse place records. Area labels follow the data source and are not always administrative district boundaries.</p><p class="intro zh" lang="zh-HK">選擇地區瀏覽場地。地區名稱沿用資料來源，未必等同行政區界線。</p></header><ul class="list">${districtCards}</ul><p>Or <a href="/categories/">browse by category</a>.</p>`);

await Promise.all(generatedFiles);
sitemapEntries.set('/', lastmod);
const sitemapXml = `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${[...sitemapEntries.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([path, modified]) => `  <url><loc>${escapeHtml(`${siteOrigin}${path}`)}</loc>${modified ? `<lastmod>${modified}</lastmod>` : ''}</url>`).join('\n')}\n</urlset>\n`;
await writeFile(join(distDir, 'sitemap.xml'), sitemapXml);
console.log(`Generated ${generatedFiles.length} crawlable HTML pages and ${sitemapEntries.size} sitemap URLs from ${snapshot.places.length} place records (${lastmod ? `snapshot ${lastmod}` : 'no snapshot date'}).`);
