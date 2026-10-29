// Inspect paths only: ordinary query text may legitimately mention .env or Git.
export function isSecretProbe(pathname) {
  let path = pathname;
  for (let n = 0; n < 4; n++) {
    let decoded;
    try { decoded = decodeURIComponent(path); } catch { return true; }
    if (decoded === path) break;
    path = decoded;
  }
  // Reject ambiguous over-encoded separators/dot segments as well.
  if (/%(?:25|2e|2f|5c)/i.test(path)) return true;
  return path.replaceAll('\\', '/').split('/').some(segment => {
    const name = segment.toLowerCase().split(';')[0].replace(/[ .]+$/, '');
    return /^\.(?:env|dev\.vars)(?:[.~]|$)/.test(name) ||
      /^\.(?:git|svn|hg|aws|ssh|docker|npmrc|pypirc|netrc|htpasswd|htaccess|ds_store)(?:[.~]|$)/.test(name) ||
      /^(?:id_rsa|id_dsa|id_ecdsa|id_ed25519|wp-config\.php)(?:[.~]|$)/.test(name);
  });
}
