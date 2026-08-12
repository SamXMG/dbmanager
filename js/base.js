/* dbmanager 前端 - 基础: 全局状态/工具函数/连接与会话 */
let API = window.location.origin || "http://127.0.0.1:8770"; // 以当前页面来源作为后端地址（兼容本机/局域网/公网 IPv6）；init() 会用 /api/config 的 api_base 再次校正
let CONN = null;
let SESSION = null; // 按名直连的服务端会话 token（密码只存服务端内存）
let USER_TOKEN = null; // 账号体系登录 token（users.json 启用时）
let USER_ROLE = null;  // read / write
let USER_NAME = '';    // 当前登录用户名
try {
  USER_TOKEN = localStorage.getItem('dbm_user_token') || null;
  USER_ROLE = localStorage.getItem('dbm_user_role') || null;
  USER_NAME = localStorage.getItem('dbm_user_name') || '';
} catch (e) {}
// 全局 fetch 包装: 所有请求自动携带登录 token(修复连接管理/导出等直接 fetch 接口在账号体系下的 401)
// 并统一处理 401 require_login(服务端重启后 token 失效 -> 清除孤儿 token + 同步状态区 + 弹登录)
{
  const _origFetch = window.fetch.bind(window);
  window.fetch = function (url, opts) {
    opts = opts || {};
    opts.headers = opts.headers || {};
    if (USER_TOKEN && typeof url === 'string' && !url.includes('/api/login')) {
      opts.headers['X-User-Token'] = USER_TOKEN;
    }
    return _origFetch(url, opts).then(r => {
      if (r.status === 401 && USER_TOKEN) {
        r.clone().json().then(d => {
          if (d && d.require_login) {
            clearUserToken();
            applyAuthBox();
            showAuthModal();
          }
        }).catch(() => {});
      }
      return r;
    });
  };
}
let DEFAULT_CONN = null;
let CONNECTIONS = []; // 从后端发现的 Navicat 连接列表
let CONN_LIST = [];  // 已保存的“我的连接”
let editingName = null; // 正在编辑的连接名（null 表示新建）
let TABLES = [], current = null, currentPage = 1, currentMeta = null;
let curSort = null; // 列排序: {col, dir} | null
let transactionMode = false;
let filters = {}; // 表头筛选: {colName: {op, val}}
let currentTab = "data";
let editingCell = null; // {rowIdx, colName, origValue}
// ---- 深浅色主题: body[data-theme=dark] + localStorage 记忆 ----
function applyTheme() {
  let t = 'light';
  try { t = localStorage.getItem('dbm_theme') || 'light'; } catch (e) {}
  document.body.dataset.theme = t === 'dark' ? 'dark' : '';
}
function toggleTheme() {
  const dark = document.body.dataset.theme === 'dark';
  document.body.dataset.theme = dark ? '' : 'dark';
  try { localStorage.setItem('dbm_theme', dark ? 'light' : 'dark'); } catch (e) {}
  const btn = document.getElementById('themeBtn');
  if (btn) btn.textContent = dark ? '🌓 主题' : '🌞 主题';
}
applyTheme();   // 启动即应用(script 在 body 底部, body 已存在)
function encConn(c) { return btoa(String.fromCharCode.apply(null, new TextEncoder().encode(JSON.stringify(c)))); }
function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
function escAttr(s) { return String(s == null ? '' : s).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/&/g, '&amp;').replace(/"/g, '&quot;'); }
let PUB_KEY = null; // 服务端 RSA 公钥(用于加密密码, 防 HTTP 抓包)
async function rsaEncrypt(text) {
  if (!text || !PUB_KEY || !window.crypto || !crypto.subtle) return text; // 非安全上下文/无公钥时回退明文
  try {
    const b64 = PUB_KEY.replace(/-----BEGIN PUBLIC KEY-----/g, '').replace(/-----END PUBLIC KEY-----/g, '').replace(/\s+/g, '');
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const key = await crypto.subtle.importKey('spki', bytes.buffer, { name: 'RSA-OAEP', hash: 'SHA-256' }, false, ['encrypt']);
    const enc = await crypto.subtle.encrypt({ name: 'RSA-OAEP' }, key, new TextEncoder().encode(text));
    let s = '';
    const out = new Uint8Array(enc);
    for (let i = 0; i < out.length; i++) s += String.fromCharCode(out[i]);
    return 'rsa:' + btoa(s);
  } catch (e) { return text; }
}
async function encBody(obj) { if (obj && typeof obj.pwd === 'string' && obj.pwd) obj.pwd = await rsaEncrypt(obj.pwd); return JSON.stringify(obj); }
function qp(obj) { return Object.entries(obj).map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(v)).join('&'); }
// 按数据库类型生成标识符引用符号
function quoteIdent(t, name) { if (t === 'mssql') return '[' + name + ']'; if (t === 'mysql') return '`' + name + '`'; return '"' + name + '"'; } // postgresql / sqlite
function toast(msg, isErr) { const t = document.getElementById('toast'); t.textContent = msg; t.className = 'toast show' + (isErr ? ' err' : ''); setTimeout(() => t.className = 'toast', 2600); }
async function api(path, opts = {}) {
  opts.headers = opts.headers || {};
  if (USER_TOKEN) opts.headers['X-User-Token'] = USER_TOKEN;
  // 会话优先级: 显式 opts.session > 当前激活 tab 的独立会话(跨库表) > 全局 SESSION
  if (opts.session) opts.headers['X-Session'] = opts.session;
  else if (typeof activeTab === 'function') {
    let at = null;
    try { at = activeTab(); } catch (e) { at = null; }
    if (at && at.session) opts.headers['X-Session'] = at.session;
    else if (SESSION) opts.headers['X-Session'] = SESSION;
  }
  else if (SESSION) opts.headers['X-Session'] = SESSION;
  else if (CONN) {
    const cc = Object.assign({}, CONN);
    if (cc.pwd) cc.pwd = await rsaEncrypt(cc.pwd);
    opts.headers['X-Conn'] = encConn(cc);
  }
  opts.credentials = 'include';
  if (opts.body && typeof opts.body === 'string' && !SESSION) {
    try {
      const obj = JSON.parse(opts.body);
      if (obj && typeof obj.pwd === 'string' && obj.pwd) {
        obj.pwd = await rsaEncrypt(obj.pwd);
        opts.body = JSON.stringify(obj);
      }
    } catch (e) { /* 非 JSON body 不处理 */ }
  }
  const r = await fetch(path, opts);
  const d = await r.json().catch(() => ({}));
  if (d.require_gateway) { showGatewayModal(); throw new Error(d.error || '需要公网访问验证'); }
  if (d.require_login) { clearUserToken(); applyAuthBox(); showAuthModal(); throw new Error(d.error || '请先登录'); }
  if (d.error) throw new Error(d.error);
  return d;
}
function onTypeChange() { const t = document.getElementById('cType').value; const isSqlite = t === 'sqlite'; document.getElementById('hostFields').style.display = isSqlite ? 'none' : ''; document.getElementById('sqliteFields').style.display = isSqlite ? '' : 'none'; document.getElementById('loadDbsBtn').style.display = isSqlite ? 'none' : ''; const lbl = document.getElementById('dbLabel'); lbl.textContent = '数据库 (DATABASE)'; }
async function doConnect() {
  const btn = document.getElementById('connBtn');
  if (btn && btn.disabled) return; // 防重复点击
  if (btn) { btn.disabled = true; btn.textContent = '连接中...'; }
  try {
    SESSION = null;
    const type = document.getElementById('cType').value;
    let conn;
    if (type === 'sqlite') {
      const db = document.getElementById('cDbSqlite').value.trim();
      if (!db) { toast('请填写数据库文件路径', true); return; }
      conn = { db_type: 'sqlite', database: db, pwd: document.getElementById('cPwdSqlite').value };
    } else {
      const server = document.getElementById('cServer').value.trim();
      const database = document.getElementById('cDb').value.trim();
      const uid = document.getElementById('cUid').value.trim();
      const port = document.getElementById('cPort').value.trim();
      if (!server || !database || !uid) { toast('请填写服务器/数据库/账号', true); return; }
      conn = { db_type: type, server, port: port ? parseInt(port, 10) : defPort(type), database, uid, pwd: document.getElementById('cPwd').value };
    }
    const d = await api(API + '/api/connect', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(conn) });
    CONN = conn; SESSION = d.session || null;
    // 只持久化"无密码"的连接元信息, 明文密码绝不落浏览器存储(传输已 RSA 加密, 服务端有 X-Session 会话)
    const persistConn = Object.assign({}, conn); delete persistConn.pwd;
    sessionStorage.setItem('dbconn', JSON.stringify(persistConn));
    store.set('connected', { conn: CONN, tables: d.tables || [] });
    toast('连接成功');
  } catch (e) { toast('连接失败: ' + e.message, true); }
  finally { if (btn) { btn.disabled = false; btn.textContent = '连接'; } }
}
async function loadDbs() { const type = document.getElementById('cType').value; if (type === 'sqlite') { toast('SQLite 无需加载库列表', true); return; } const server = document.getElementById('cServer').value.trim(); const port = document.getElementById('cPort').value.trim(); const uid = document.getElementById('cUid').value.trim(); const pwd = document.getElementById('cPwd').value; if (!server || !uid) { toast('请先填服务器与账号', true); return; } const conn = { db_type: type, server, port: port ? parseInt(port, 10) : defPort(type), database: '', uid, pwd }; try { const d = await api(API + '/api/databases', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(conn) }); const dl = document.getElementById('dbList'); dl.innerHTML = d.map(n => `<option value="${esc(n)}">`).join(''); toast('已加载 ' + d.length + ' 个数据库'); } catch (e) { toast('加载失败: ' + e.message, true); } }
function logout() { if (transactionMode) { if (!confirm('事务模式下退出会丢失未提交的修改，确认退出吗？')) return; } sessionStorage.removeItem('dbconn'); CONN = null; SESSION = null; location.reload(); }
// ------------------------------
// 我的连接（保存/加密/一键直连）
// ------------------------------
async function openConnMgr() { document.getElementById('connMgr').classList.add('show'); await renderConnList(); }
function closeConnMgr() { document.getElementById('connMgr').classList.remove('show'); hideConnForm(); }
document.getElementById('connMgr').addEventListener('click', e => { if (e.target.id === 'connMgr') closeConnMgr(); });
async function renderConnList() {
  try {
    CONN_LIST = await fetch(API + '/api/connections').then(r => r.json());
  } catch (e) { CONN_LIST = []; }
  const box = document.getElementById('connListBox');
  if (!CONN_LIST.length) { box.innerHTML = '<div class="empty2">还没有保存的连接，点上方「+ 新建连接」添加一个。</div>'; return; }
  let statuses = {};
  try { statuses = JSON.parse(localStorage.getItem('dbm_conn_status') || '{}'); } catch (e) { statuses = {}; }
  box.innerHTML = CONN_LIST.map(c => {
    const det = [c.db_type, (c.server || '') + (c.port ? ':' + c.port : ''), c.database, c.uid].filter(Boolean).join(' · ');
    const st = statuses[c.name];
    const badge = st ? `<span class="conn-badge ${st.ok ? 'ok' : 'fail'}" title="最近测试: ${esc(st.msg || '')}">${st.ok ? '✓' : '✗'} ${esc((st.t || '').slice(5))}</span>` : '';
    return `<div class="conn-row"><div class="meta" ondblclick="connConnect('${escAttr(c.name)}')" title="双击连接"><b>${esc(c.name)}${(c.visible_to && c.visible_to.length ? ' 🔒' : '')}${c.mode === 'read_only' ? ' 🛡️' : ''}</b><div class="det">${esc(det)}</div></div>` +
      `<div class="acts">${badge}` +
      `<button class="sm primary" onclick="connConnect('${escAttr(c.name)}')">连接</button>` +
      `<button class="sm" onclick="connTest('${escAttr(c.name)}')">测试</button>` +
      `<button class="sm" onclick="connEdit('${escAttr(c.name)}')">编辑</button>` +
      `<button class="sm danger" onclick="connDelete('${escAttr(c.name)}')">删除</button></div></div>`;
  }).join('');
}
function showConnForm(name) {
  editingName = name || null; document.getElementById('connFormTitle').textContent = name ? ('编辑连接 · ' + name) : '新建连接';
  if (!name) { document.getElementById('mName').value = ''; document.getElementById('mType').value = 'mysql'; document.getElementById('mServer').value = ''; document.getElementById('mPort').value = ''; document.getElementById('mDb').value = ''; document.getElementById('mUid').value = ''; document.getElementById('mPwd').value = ''; document.getElementById('mDbSqlite').value = ''; document.getElementById('mSsh').checked = false; mSshToggle(); document.getElementById('mSshHost').value = ''; document.getElementById('mSshPort').value = ''; document.getElementById('mSshUser').value = ''; document.getElementById('mSshPwd').value = ''; document.getElementById('mSshKey').value = ''; document.getElementById('mCloud').value = ''; document.getElementById('cloudTip').style.display = 'none'; document.getElementById('mVisibleTo').value = ''; document.getElementById('mReadOnly').checked = false; }
  // ACL 字段(可见性/只读标记)仅管理员可见
  document.getElementById('mAclFields').style.display = USER_ROLE === 'admin' ? '' : 'none';
  mTypeChange(); document.getElementById('connFormBox').style.display = '';
}
function hideConnForm() { document.getElementById('connFormBox').style.display = 'none'; editingName = null; }
function mTypeChange() { const t = document.getElementById('mType').value; const isSql = t === 'sqlite'; document.getElementById('mHostFields').style.display = isSql ? 'none' : ''; document.getElementById('mSqliteFields').style.display = isSql ? '' : 'none'; }
function defPort(type) { return ({ mysql: 3306, postgresql: 5432, mssql: 1433, oracle: 1521, mongodb: 27017, redis: 6379, oceanbase: 2881, tidb: 4000, kingbase: 54321 })[type] || 3306; }
// ---- 云厂商快速模板: 纯引导(端口/类型预填+连接提示), 连接仍走标准协议 ----
const CLOUD_VENDORS = {
  aliyun: { name: '阿里云', def: 'mysql', ports: { mysql: 3306, postgresql: 5432, mssql: 1433, oracle: 1521, mongodb: 27017 }, types: 'RDS MySQL · PolarDB MySQL · RDS PostgreSQL · RDS SQL Server · 云数据库 MongoDB', tip: '需在云控制台开启公网访问并配置白名单；生产环境建议用内网地址 + SSH 隧道' },
  tencent: { name: '腾讯云', def: 'mysql', ports: { mysql: 3306, postgresql: 5432, mssql: 1433, mongodb: 27017 }, types: 'CDB MySQL · TDSQL-C MySQL · PostgreSQL · SQL Server · 云数据库 MongoDB', tip: '需在控制台开通外网地址并放行安全组；内网建议 SSH 隧道' },
  huawei: { name: '华为云', def: 'mysql', ports: { mysql: 3306, postgresql: 5432, mssql: 1433, mongodb: 27017 }, types: 'RDS MySQL · GaussDB(for MySQL) · RDS PostgreSQL · RDS SQL Server · DDS(MongoDB)', tip: '需绑定弹性IP/开启公网，并配置安全组放行来源IP' },
  aws: { name: 'Amazon AWS', def: 'postgresql', ports: { mysql: 3306, postgresql: 5432, mssql: 1433, oracle: 1521, mongodb: 27017 }, types: 'RDS MySQL · RDS PostgreSQL · Aurora · RDS SQL Server', tip: '需在安全组(Security Group)放行来源IP；VPC 内建议 SSH 隧道' },
  azure: { name: 'Microsoft Azure', def: 'mssql', ports: { mysql: 3306, postgresql: 5432, mssql: 1433, mongodb: 27017 }, types: 'Azure SQL · Azure Database for MySQL · PostgreSQL', tip: '需在防火墙规则中添加客户端IP；内网可用 SSH 隧道' },
  oracle_cloud: { name: 'Oracle Cloud', def: 'oracle', ports: { oracle: 1521, mysql: 3306, postgresql: 5432 }, types: 'Autonomous Database(Oracle) · MySQL HeatWave · PostgreSQL', tip: '需在 OCI 网络安全组放行端口；Autonomous DB 建议公网端点 + 隧道' },
  mongo_cloud: { name: 'MongoDB Atlas', def: 'mongodb', ports: { mongodb: 27017 }, types: 'MongoDB Atlas 托管集群', tip: '需在 Atlas Network Access 白名单中加入来源 IP' },
};
function mCloudChange() {
  const v = document.getElementById('mCloud').value;
  const tip = document.getElementById('cloudTip');
  if (!v) { tip.style.display = 'none'; return; }
  const c = CLOUD_VENDORS[v];
  tip.style.display = '';
  tip.innerHTML = `<b>${c.name}</b> 模板：支持 ${c.types}。<br>${c.tip}。选好类型填服务器地址即可连接。`;
  const sel = document.getElementById('mType');
  const opts = [...sel.options];
  const hasDef = opts.some(o => o.value === c.def);
  if (hasDef) {
    sel.value = c.def;
    if (opts.find(o => o.value === c.def).disabled) toast(c.name + ' 默认类型(' + c.def + ')即将支持，已预选，开发完成后可直接连接');
  } else {
    sel.value = 'mysql';
  }
  const port = c.ports[sel.value];
  if (port && document.getElementById('mHostFields').style.display !== 'none') {
    document.getElementById('mPort').value = port;
  }
  mTypeChange();
}
function mSshToggle() { document.getElementById('mSshFields').style.display = document.getElementById('mSsh').checked ? '' : 'none'; }
function collectTunnel() {
  if (!document.getElementById('mSsh').checked) return null;
  const host = document.getElementById('mSshHost').value.trim();
  if (!host) return null;
  return {
    host,
    port: parseInt(document.getElementById('mSshPort').value.trim(), 10) || 22,
    user: document.getElementById('mSshUser').value.trim(),
    password: document.getElementById('mSshPwd').value,
    key: document.getElementById('mSshKey').value.trim(),
  };
}
function connEdit(name) { const c = CONN_LIST.find(x => x.name === name); if (!c) return; showConnForm(name); document.getElementById('mName').value = c.name; document.getElementById('mType').value = c.db_type; document.getElementById('mServer').value = c.server || ''; document.getElementById('mPort').value = c.port || ''; document.getElementById('mDb').value = c.database || ''; document.getElementById('mUid').value = c.uid || ''; document.getElementById('mPwd').value = ''; document.getElementById('mDbSqlite').value = c.database || ''; document.getElementById('mVisibleTo').value = (c.visible_to || []).join(', '); document.getElementById('mReadOnly').checked = c.mode === 'read_only'; mTypeChange(); const t = c.tunnel || {}; document.getElementById('mSsh').checked = !!t.host; mSshToggle(); document.getElementById('mSshHost').value = t.host || ''; document.getElementById('mSshPort').value = t.port || ''; document.getElementById('mSshUser').value = t.user || ''; document.getElementById('mSshPwd').value = ''; document.getElementById('mSshKey').value = t.key || ''; toast('已载入连接信息，密码需重新输入（留空则保持不变）'); }
async function connSave() {
  const type = document.getElementById('mType').value;
  const name = document.getElementById('mName').value.trim();
  if (!name) { toast('请填写连接名称', true); return; }
  let conn;
  if (type === 'sqlite') { const db = document.getElementById('mDbSqlite').value.trim(); if (!db) { toast('请填写数据库文件路径', true); return; } conn = { name, db_type: 'sqlite', database: db, pwd: document.getElementById('mPwd').value }; }
  else { const server = document.getElementById('mServer').value.trim(); const port = document.getElementById('mPort').value.trim(); const uid = document.getElementById('mUid').value.trim(); if (!server || !uid) { toast('请填写服务器与账号', true); return; } conn = { name, db_type: type, server, port: port ? parseInt(port, 10) : defPort(type), database: document.getElementById('mDb').value.trim(), uid, pwd: document.getElementById('mPwd').value, tunnel: collectTunnel() }; }
  // 内网 ACL(仅 admin 可见的表单字段; 非 admin 传了也会被后端 403)
  if (USER_ROLE === 'admin') {
    const vt = document.getElementById('mVisibleTo').value.split(/[,，\s]+/).map(s => s.trim()).filter(Boolean);
    if (vt.length) conn.visible_to = vt;
    if (document.getElementById('mReadOnly').checked) conn.mode = 'read_only';
  }
  try {
    const d = await fetch(API + '/api/connections', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: await encBody(conn) }).then(r => r.json());
    if (d.error) throw new Error(d.error);
    hideConnForm(); await renderConnList(); toast('已保存连接 ' + name);
  } catch (e) { toast('保存失败: ' + e.message, true); }
}
async function connDelete(name) { if (!confirm('确认删除连接「' + name + '」？')) return; try { const d = await fetch(API + '/api/connections/delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) }).then(r => r.json()); if (d.error) throw new Error(d.error); await renderConnList(); toast('已删除 ' + name); } catch (e) { toast('删除失败: ' + e.message, true); } }
async function connConnect(name) {
  if (window.__connecting) return; // 防重复点击(等待上一个连接完成)
  window.__connecting = true;
  try {
    const d = await fetch(API + '/api/connect', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) }).then(r => r.json());
    if (d.error) throw new Error(d.error);
    SESSION = d.session; CONN = d.connection || { db_type: '', server: '', database: '' };
    store.set('connected', { conn: CONN, tables: d.tables || [] });
    closeConnMgr(); toast('已连接 ' + name);
  } catch (e) { toast('连接失败: ' + e.message, true); }
  finally { window.__connecting = false; }
}
async function connTest(name) {
  try {
    const d = await fetch(API + '/api/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) }).then(r => r.json());
    if (d.error) throw new Error(d.error);
    if (d.ok) toast('✓ ' + name + ' ' + d.message); else toast('✗ ' + name + ' 连接失败: ' + d.error, true);
    // 记录测试状态供连接列表徽标显示
    try {
      const sts = JSON.parse(localStorage.getItem('dbm_conn_status') || '{}');
      const now = new Date();
      sts[name] = { ok: !!d.ok, msg: d.ok ? (d.message || '连接成功') : (d.error || '连接失败'), t: ('0' + now.getHours()).slice(-2) + ':' + ('0' + now.getMinutes()).slice(-2) };
      localStorage.setItem('dbm_conn_status', JSON.stringify(sts));
      renderConnList();
    } catch (e) {}
  } catch (e) { toast('测试失败: ' + e.message, true); }
}
async function testFormConn() {
  const type = document.getElementById('mType').value;
  // 编辑模式且密码留空 -> 用已存连接(服务端解密原密码)测试
  if (editingName && !document.getElementById('mPwd').value) {
    return connTest(editingName);
  }
  let payload;
  if (type === 'sqlite') {
    const db = document.getElementById('mDbSqlite').value.trim();
    if (!db) { toast('请填写数据库文件路径', true); return; }
    payload = { db_type: 'sqlite', database: db, pwd: document.getElementById('mPwd').value };
  } else {
    const server = document.getElementById('mServer').value.trim();
    const port = document.getElementById('mPort').value.trim();
    const uid = document.getElementById('mUid').value.trim();
    if (!server || !uid) { toast('请填写服务器与账号', true); return; }
    payload = { db_type: type, server, port: port ? parseInt(port, 10) : defPort(type), database: document.getElementById('mDb').value.trim(), uid, pwd: document.getElementById('mPwd').value, tunnel: collectTunnel() };
  }
  try {
    const d = await fetch(API + '/api/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: await encBody(payload) }).then(r => r.json());
    if (d.error) throw new Error(d.error);
    if (d.ok) toast('✓ ' + d.message); else toast('✗ 连接失败: ' + d.error, true);
  } catch (e) { toast('测试失败: ' + e.message, true); }
}
async function stopService() { if (!confirm('确认停止服务？\n停止后页面将无法使用，需重新启动 app.py 才能再次访问。')) return; try { const r = await fetch(API + '/api/shutdown', { method: 'POST' }); const d = await r.json(); toast(d.msg || '服务已停止'); } catch (e) { toast('停止指令已发出', false); } setTimeout(() => { document.body.innerHTML = '<div class="empty" style="padding:80px">服务已停止。<br>如要再次使用，请重新运行本程序（DBManager.exe）。</div>'; }, 600); }
function toggleTransaction() { store.set('txMode', !transactionMode); }
// 状态订阅: 事务模式(按钮/操作栏/关闭时回滚) —— 状态驱动界面
store.watch('txMode', v => {
  transactionMode = v;
  const btn = document.getElementById('txBtn');
  const bar = document.getElementById('txBar');
  if (btn) { btn.textContent = '事务模式: ' + (v ? '开' : '关'); btn.classList.toggle('primary', v); }
  if (bar) bar.classList.toggle('show', v);
  if (!v) rollbackTx();
});
// 状态订阅: 连接成功(统一更新标题信息/面板切换/表树/库选择器) —— 消除各连接路径的重复 UI 代码
store.watch('connected', ({ conn, tables }) => {
  const info = (conn.db_type || '') + (conn.server ? ' · ' + conn.server : '') + (conn.database ? ' · ' + conn.database : '');
  document.getElementById('dbinfo').textContent = info;
  document.getElementById('connPanel').style.display = 'none';
  document.getElementById('app').style.display = 'flex';
  document.getElementById('switchBtn').style.display = '';
  document.getElementById('txBtn').style.display = '';
  document.getElementById('stopBtn').style.display = '';
  document.getElementById('viewSwitch').style.display = 'flex';  // 应用级视图: 数据浏览 / SQL 工作台
  TABLES = tables || [];
  FULL_TABLES = null;  // 新连接清空切库缓存
  if (typeof selectedObj !== 'undefined') selectedObj = null; // 清对象选中
  if (typeof renderCrumbs === 'function') renderCrumbs(); // 面包屑同步清空
  renderSideConns();   // 左侧连接栏(Navicat 多连接并存)
  renderTables('');
  initDbSwitch();
  loadRoutines();   // 拉取存储过程/函数/触发器, 渲染树分组
  renderStatusBar(); // 底部状态条
});
function txObj() { return transactionMode ? { tx_id: (activeTab() ? activeTab().id : 0) } : {}; } // 每个文档标签独立事务
// 常用快捷键: Ctrl+R 刷新当前数据, F5 刷新表树(输入框内不拦截)
document.addEventListener('keydown', e => {
  const tag = (e.target && e.target.tagName || '').toLowerCase();
  if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'r') {
    e.preventDefault();
    if (typeof loadData === 'function' && typeof activeTab === 'function' && activeTab()) loadData(currentPage);
  }
  if (e.key === 'F5') {
    e.preventDefault();
    if (typeof renderTables === 'function') renderTables('');
  }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'w') {
    e.preventDefault();
    if (typeof activeTab === 'function' && activeTab() && typeof closeDocTab === 'function') closeDocTab(activeTab().id, null);
  }
  if ((e.ctrlKey || e.metaKey) && e.key === 'Tab') {
    e.preventDefault();
    if (typeof switchNextTab === 'function') switchNextTab();
  }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'd') {
    e.preventDefault();
    if (typeof copySelectedRows === 'function') copySelectedRows();
  }
});async function commitTx() { if (!confirm('确认提交所有修改？提交后无法撤销。')) return; try { await api(API + '/api/transaction/commit', { method: 'POST', body: JSON.stringify(txObj()) }); toast('事务已提交'); loadData(currentPage); } catch (e) { toast('提交失败: ' + e.message, true); } }
async function rollbackTx() { try { await api(API + '/api/transaction/rollback', { method: 'POST', body: JSON.stringify(txObj()) }); toast('已回滚所有修改'); loadData(currentPage); } catch (e) { toast('回滚失败: ' + e.message, true); } }
// ------------------------------
// 公网访问网关验证（仅外部/公网客户端触发）
// ------------------------------
function showGatewayModal() { const m = document.getElementById('gwMask'); if (m) { m.classList.add('show'); const el = document.getElementById('gwToken'); if (el) el.focus(); } }
function closeGatewayModal() { const m = document.getElementById('gwMask'); if (m) m.classList.remove('show'); }
document.getElementById('gwMask').addEventListener('click', e => { if (e.target.id === 'gwMask') closeGatewayModal(); });
async function submitGateway() {
  const el = document.getElementById('gwToken'); const tok = el ? el.value : '';
  if (!tok) { toast('请输入访问令牌', true); return; }
  try {
    const r = await fetch(API + '/api/gateway/login', { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: tok }) });
    const d = await r.json().catch(() => ({}));
    if (d.ok) { closeGatewayModal(); toast('验证成功'); location.reload(); }
    else { toast('验证失败: ' + (d.error || '令牌错误'), true); }
  } catch (e) { toast('验证请求失败: ' + e.message, true); }
}
// ------------------------------
// 账号体系（users.json 启用时）
// ------------------------------
function showAuthModal() { const m = document.getElementById('authMask'); if (m) { m.classList.add('show'); showLoginView(); const el = document.getElementById('authUser'); if (el) el.focus(); } }
function closeAuthModal() { const m = document.getElementById('authMask'); if (m) m.classList.remove('show'); }
function showLoginView() { const lv = document.getElementById('authLoginView'); const rv = document.getElementById('authRegView'); if (lv) lv.style.display = ''; if (rv) rv.style.display = 'none'; }
function showRegisterView() { const lv = document.getElementById('authLoginView'); const rv = document.getElementById('authRegView'); if (lv) lv.style.display = 'none'; if (rv) rv.style.display = ''; const el = document.getElementById('regUser'); if (el) el.focus(); }
async function submitRegister() {
  const u = document.getElementById('regUser').value.trim();
  const p = document.getElementById('regPwd').value;
  const p2 = document.getElementById('regPwd2').value;
  if (!u || !p) { toast('请填写用户名和密码', true); return; }
  if (p !== p2) { toast('两次密码不一致', true); return; }
  try {
    const d = await fetch(API + '/api/register', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: u, password: p }) }).then(r => r.json());
    if (d.error) throw new Error(d.error);
    toast(d.message || '账号已创建'); showLoginView();
    document.getElementById('authUser').value = u;
    document.getElementById('authPwd').value = '';
    const el = document.getElementById('authPwd'); if (el) el.focus();
  } catch (e) { toast('创建失败: ' + e.message, true); }
}
function clearUserToken() {
  USER_TOKEN = null; USER_ROLE = null; USER_NAME = '';
  try {
    localStorage.removeItem('dbm_user_token'); localStorage.removeItem('dbm_user_role'); localStorage.removeItem('dbm_user_name');
  } catch (e) {}
}
function logoutAccount() {
  clearUserToken();
  location.reload();
}
// 登录状态区(header): 未登录显示「登录」按钮, 已登录显示用户名+登出
function applyAuthBox() {
  const box = document.getElementById('authBox');
  if (!box) return;
  box.style.display = 'flex';
  const loginBtn = document.getElementById('loginBtn');
  const userInfo = document.getElementById('userInfo');
  const logoutBtn = document.getElementById('logoutBtn');
  if (USER_TOKEN) {
    if (loginBtn) loginBtn.style.display = 'none';
    if (userInfo) { userInfo.style.display = ''; userInfo.textContent = '👤 ' + USER_NAME + (USER_ROLE === 'admin' ? '(管理)' : (USER_ROLE === 'write' ? '(读写)' : '(只读)')); }
    if (logoutBtn) logoutBtn.style.display = '';
  } else if (USER_NAME) {
    // 开发模式虚拟登录: 显示用户名但无登出(登出会死循环回 admin)
    if (loginBtn) loginBtn.style.display = 'none';
    if (userInfo) { userInfo.style.display = ''; userInfo.textContent = '👤 ' + USER_NAME + (USER_ROLE === 'admin' ? '(管理)' : (USER_ROLE === 'write' ? '(读写)' : '(只读)')) + ' (开发)'; }
    if (logoutBtn) logoutBtn.style.display = 'none';
  } else {
    if (loginBtn) loginBtn.style.display = '';
    if (userInfo) userInfo.style.display = 'none';
    if (logoutBtn) logoutBtn.style.display = 'none';
  }
  if (typeof renderStatusBar === 'function') renderStatusBar(); // 状态条用户同步
}
document.getElementById('authMask').addEventListener('click', e => { if (e.target.id === 'authMask') closeAuthModal(); });
async function submitLogin() {
  const u = document.getElementById('authUser').value.trim();
  const p = document.getElementById('authPwd').value;
  if (!u || !p) { toast('请输入用户名和密码', true); return; }
  try {
    const r = await fetch(API + '/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: u, password: p }) });
    const d = await r.json().catch(() => ({}));
    if (d.ok && d.token) {
      USER_TOKEN = d.token; USER_ROLE = d.role || 'read'; USER_NAME = d.user || u;
      try {
        localStorage.setItem('dbm_user_token', d.token);
        localStorage.setItem('dbm_user_role', USER_ROLE);
        localStorage.setItem('dbm_user_name', USER_NAME);
      } catch (e) {}
      toast('欢迎，' + USER_NAME); location.reload(); // 重新走 init 完整流程
    } else { toast('登录失败: ' + (d.error || '用户名或密码错误'), true); }
  } catch (e) { toast('登录请求失败: ' + e.message, true); }
}
// 写操作按钮(只读账号隐藏); 后端仍强制校验(403 兜底)
const WRITE_HANDLERS = ['openAdd', 'openSync', 'openSchemaDiff', 'downloadBackup', 'openRestore', 'openImport', 'openPasteInsert', 'deleteSelectedRows', 'redisNewKey', 'redisTtl', 'redisDelKey', 'toggleWriteMode', 'saveRoutine', 'execRoutine', 'dropRoutine', 'toggleTransaction', 'stopService'];
function applyRole(role) {
  document.body.dataset.role = role || 'write';
  applyAuthBox();
  const pwdBtn = document.getElementById('pwdBtn');
  const acctBtn = document.getElementById('acctBtn');
  if (pwdBtn) pwdBtn.style.display = USER_TOKEN ? '' : 'none';
  if (acctBtn) acctBtn.style.display = (USER_TOKEN && role !== 'read') ? '' : 'none'; // admin/write 均可见账号管理
  if (role === 'read') {
    document.querySelectorAll('[onclick]').forEach(el => {
      const oc = el.getAttribute('onclick') || '';
      if (WRITE_HANDLERS.some(h => oc.includes(h))) el.style.display = 'none';
    });
  }
}
// 修改密码（所有登录用户）
function showChangePwd() {
  showModal(`<h3>修改密码</h3>
    <div class="field"><label>旧密码</label><input id="cpOld" type="password"></div>
    <div class="field"><label>新密码（至少 6 位）</label><input id="cpNew" type="password"></div>
    <div class="field"><label>确认新密码</label><input id="cpNew2" type="password"></div>
    <div class="acts"><button onclick="closeModal()">取消</button><button class="primary" onclick="submitChangePwd()">修改</button></div>`);
}
async function submitChangePwd() {
  const oldP = document.getElementById('cpOld').value;
  const np = document.getElementById('cpNew').value;
  const np2 = document.getElementById('cpNew2').value;
  if (!oldP || !np) { toast('请填写完整', true); return; }
  if (np !== np2) { toast('两次新密码不一致', true); return; }
  try {
    const d = await api(API + '/api/password', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ old_password: oldP, new_password: np }) });
    if (d.error) throw new Error(d.error);
    toast(d.message || '密码已更新'); closeModal();
  } catch (e) { toast('修改失败: ' + e.message, true); }
}
// 账号管理（仅 write 角色）
async function showAcctMgr() {
  showModal(`<h3>账号管理</h3><div class="empty2" style="padding:20px">加载中...</div>`);
  try {
    const d = await api(API + '/api/users');
    let html = `<h3>账号管理</h3><div style="color:#86909c;font-size:12px;margin-bottom:8px">共 ${d.users.length} 个账号 · 密码 pbkdf2 加密存储</div>`;
    html += '<table style="width:100%"><thead><tr><th>用户名</th><th>角色</th><th style="width:170px">操作</th></tr></thead><tbody>';
    d.users.forEach(u => {
      html += `<tr><td>${esc(u.username)}</td><td><select onchange="acctRole('${escAttr(u.username)}', this.value)">${['read', 'write', 'admin'].map(r => `<option value="${r}" ${u.role === r ? 'selected' : ''}>${r === 'admin' ? '管理' : (r === 'write' ? '读写' : '只读')}</option>`).join('')}</select></td>`;
      html += `<td style="white-space:nowrap"><button class="sm" onclick="acctResetPwd('${escAttr(u.username)}')">重置密码</button><button class="sm danger" onclick="acctDelete('${escAttr(u.username)}')">删除</button></td></tr>`;
    });
    html += '</tbody></table>';
    html += `<div class="field" style="margin-top:14px"><label>新建账号</label><div class="row2"><input id="acctNewName" placeholder="用户名" style="min-width:0"><input id="acctNewPwd" type="password" placeholder="初始密码(≥6位)" style="min-width:0"><select id="acctNewRole"><option value="read">只读</option><option value="write">读写</option><option value="admin">管理</option></select><button class="sm primary" onclick="acctCreate()">创建</button></div></div>`;
    html += `<div class="acts"><button onclick="closeModal()">关闭</button></div>`;
    showModal(html);
  } catch (e) {
    toast('加载账号失败: ' + e.message, true);
    showModal(`<h3>账号管理</h3><div class="empty2">${esc(e.message)}</div><div class="acts"><button onclick="closeModal()">关闭</button></div>`);
  }
}
async function acctRole(name, role) {
  try { const d = await api(API + '/api/users', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: name, role }) }); if (d.error) throw new Error(d.error); toast('已更新角色'); } catch (e) { toast(e.message, true); }
}
async function acctResetPwd(name) {
  const p = prompt('为 ' + name + ' 设置新密码(≥6位):');
  if (!p) return;
  try { const d = await api(API + '/api/users', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: name, password: p }) }); if (d.error) throw new Error(d.error); toast('密码已重置'); } catch (e) { toast(e.message, true); }
}
async function acctCreate() {
  const n = document.getElementById('acctNewName').value.trim();
  const p = document.getElementById('acctNewPwd').value;
  const r = document.getElementById('acctNewRole').value;
  if (!n || !p) { toast('请填写用户名和密码', true); return; }
  try { const d = await api(API + '/api/users', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: n, role: r, password: p }) }); if (d.error) throw new Error(d.error); toast('已创建 ' + n); showAcctMgr(); } catch (e) { toast(e.message, true); }
}
async function acctDelete(name) {
  if (!confirm('确认删除账号 ' + name + '？')) return;
  try { const d = await api(API + '/api/users/delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: name }) }); if (d.error) throw new Error(d.error); toast('已删除'); showAcctMgr(); } catch (e) { toast(e.message, true); }
}
async function init() {
  try {
    const resp = await fetch(API + '/api/config', { credentials: 'include' });
    const cfg = await resp.json().catch(() => ({}));
    if (cfg && cfg.api_base) API = cfg.api_base;
    if (cfg && cfg.gateway_required) { showGatewayModal(); return; }
    // 自助注册开关: 关闭时注册视图给出明确提示(内网合规, 账号由管理员创建)
    if (cfg && cfg.register_enabled === false) {
      const regTip = document.getElementById('regTip');
      if (regTip) regTip.textContent = '自助注册已关闭(内网合规)；请联系管理员在「账号」管理中为你创建账号。';
    }
    if (cfg && cfg.auth_required) {
      // 孤儿 token 检测: 服务端重启后内存会话清空, localStorage 里的 token 失效
      // -> 以 /api/config 返回的 auth_user 为准, 不匹配则清除并回到未登录态
      if (USER_TOKEN && cfg.auth_user !== USER_NAME) {
        clearUserToken();
      }
      // 开发模式虚拟登录: 服务端无会话时默认返回 admin, 前端据此显示登录态
      if (!USER_TOKEN && cfg.auth_user) {
        USER_NAME = cfg.auth_user;
        USER_ROLE = cfg.auth_role || 'write';
      }
      applyAuthBox(); // header 始终显示登录态(登录按钮 / 用户名+登出); 弹窗由登录按钮或 API 401 触发
      if (USER_TOKEN || cfg.auth_user) applyRole(USER_ROLE);
    }
    try {
      const pr = await fetch(API + '/api/pubkey');
      if (pr.ok) { const pk = await pr.json(); if (pk && pk.pubkey) PUB_KEY = pk.pubkey; }
    } catch (e) { /* 无公钥则回退明文传输 */ }
    if (cfg && cfg.default_conn) DEFAULT_CONN = cfg.default_conn;
    if (cfg && Array.isArray(cfg.connections)) CONNECTIONS = cfg.connections;
  } catch (e) { /* 忽略配置获取失败 */ }
  fillQuick();
  if (DEFAULT_CONN) prefillForm(DEFAULT_CONN);
  const saved = sessionStorage.getItem('dbconn');
  // 配置了默认连接时，始终以默认连接为准（清掉可能残留的 localhost 等旧会话）
  if (DEFAULT_CONN) {
    sessionStorage.removeItem('dbconn');
    try {
      const cc = DEFAULT_CONN;
      const d = await api(API + '/api/connect', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cc) });
      SESSION = d.session || null; CONN = d.connection || cc;
      sessionStorage.setItem('dbconn', JSON.stringify(cc));
      const info = CONN.db_type + (CONN.server ? ' · ' + CONN.server : '') + (CONN.database ? ' · ' + CONN.database : '');
      document.getElementById('dbinfo').textContent = info;
      document.getElementById('connPanel').style.display = 'none';
      document.getElementById('app').style.display = 'flex';
      document.getElementById('switchBtn').style.display = '';
      document.getElementById('txBtn').style.display = '';
      document.getElementById('stopBtn').style.display = '';
      TABLES = d.tables || [];
      renderTables('');
      toast('已自动连接 ' + (CONN.database || CONN.server));
    } catch (e) { /* 自动连接失败，回退到面板（已预填正确主机） */ }
  } else if (saved) {
    try {
      CONN = JSON.parse(saved);
      const d = await api(API + '/api/tables');
      TABLES = d;
      const info = CONN.db_type + (CONN.server ? ' · ' + CONN.server : '') + (CONN.database ? ' · ' + CONN.database : '');
      document.getElementById('dbinfo').textContent = info;
      document.getElementById('connPanel').style.display = 'none';
      document.getElementById('app').style.display = 'flex';
      document.getElementById('switchBtn').style.display = '';
      document.getElementById('txBtn').style.display = '';
      document.getElementById('stopBtn').style.display = '';
      renderTables('');
    } catch (e) { /* 回退到连接面板 */ }
  }
  onTypeChange();
}
