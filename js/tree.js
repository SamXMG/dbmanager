// dbmanager 前端 - 表树/多文档标签/连接内选库
    let ROUTINES = [];   // 存储过程/函数/触发器: [{schema, name, type}]
    let FULL_TABLES = null; // 连接时/全部库的完整表列表(切库前缓存, 切回恢复)
    // ---- 左侧连接栏(Navicat 多连接并存) ----
    const CONN_ICON = { mysql: '🐬', postgresql: '🐘', mssql: '🅜', sqlite: '📄', oracle: '🔶', mongodb: '🍃', redis: '🔴', oceanbase: '🌊', tidb: '🔀', kingbase: '👑' };
    function connIcon(t) { return CONN_ICON[t] || '🗄️'; }
    async function renderSideConns() {
      const box = document.getElementById('sideConns');
      if (!box) return;
      try { CONN_LIST = await fetch(API + '/api/connections').then(r => r.json()); } catch (e) { /* 保持已有 */ }
      if (!Array.isArray(CONN_LIST) || !CONN_LIST.length) { box.style.display = 'none'; return; }
      box.style.display = '';
      const curName = (CONN && CONN.name) || '';
      let html = '<div class="sc-title">我的连接</div>';
      CONN_LIST.forEach(c => {
        const active = c.name === curName ? ' active' : '';
        const det = (c.db_type || '') + (c.server ? ' · ' + c.server : '') + (c.port ? ':' + c.port : '') + (c.database ? ' · ' + c.database : '');
        html += `<div class="sc-item${active}" onclick="switchConn('${escAttr(c.name)}')" title="${esc(det)}"><span class="sc-ico">${connIcon(c.db_type)}</span><span class="sc-name">${esc(c.name)}</span>${active ? '<span class="sc-state">✓</span>' : ''}</div>`;
      });
      box.innerHTML = html;
    }
    function switchConn(name) {
      if (window.__connecting) return;
      if (transactionMode) { if (!confirm('切换连接将丢失未提交的事务修改，确认切换？')) return; }
      connConnect(name);
    }
    // ---- 底部状态条(Navicat 风格): 跟随侧边栏当前选中(连接/库/对象) ----
    const OBJ_ICON2 = { Table: '📋', View: '👁️', Procedure: 'ƒ', Function: 'ƒ', Trigger: '🔔' };
    function renderStatusBar() {
      const bar = document.getElementById('statusBar');
      if (!bar) return;
      if (!CONN) { bar.style.display = 'none'; return; }
      bar.style.display = 'flex';
      const stConn = document.getElementById('stConn');
      const stDb = document.getElementById('stDb');
      const stObj = document.getElementById('stObj');
      const stUser = document.getElementById('stUser');
      if (stConn) stConn.textContent = '🔗 ' + ((CONN && (CONN.name || CONN.server)) || '-');
      // 数据库: 优先选中对象的库, 其次当前展开库, 最后连接库
      const dbName = (selectedObj && selectedObj.db) || curDb || (CONN && CONN.database) || '全部库';
      if (stDb) stDb.textContent = '🗄️ ' + dbName;
      // 对象: 选中对象显示其名+类型图标; 未选中显示计数
      if (stObj) {
        if (selectedObj && selectedObj.name) {
          const ico = OBJ_ICON2[selectedObj.type] || '📄';
          stObj.textContent = ico + ' ' + ((selectedObj.schema && selectedObj.schema !== dbName) ? selectedObj.schema + '.' : '') + selectedObj.name + (selectedObj.type === 'Table' || selectedObj.type === 'View' ? '' : ' (' + selectedObj.type + ')');
        } else {
          const nTab = TABLES.filter(t => t.type !== 'View').length;
          const nView = TABLES.filter(t => t.type === 'View').length;
          stObj.textContent = '表 ' + nTab + ' · 视图 ' + nView + ' · 函数 ' + (ROUTINES.length || 0);
        }
      }
      if (stUser) stUser.textContent = '👤 ' + (USER_TOKEN ? (USER_NAME || '-') : '未登录');
    }
    async function loadRoutines() {
      try {
        const hdrs = {};
        if (SESSION) hdrs['X-Session'] = SESSION; else if (CONN) hdrs['X-Conn'] = encConn(CONN);
        const d = await fetch(API + '/api/routines', { headers: hdrs }).then(r => r.json());
        ROUTINES = d.routines || [];
      } catch (e) { ROUTINES = []; }
      renderTables('');
      renderStatusBar();
    }
    async function openRoutine(schema, name, kind) {
      // 双击对象: 切到 SQL 工作台 + 载入源码 + 显示编辑横幅
      try {
        const hdrs = {};
        if (SESSION) hdrs['X-Session'] = SESSION; else if (CONN) hdrs['X-Conn'] = encConn(CONN);
        const d = await fetch(API + '/api/routine/source?' + qp({ s: schema, name, kind }), { headers: hdrs }).then(r => r.json());
        if (d.error) throw new Error(d.error);
        if (typeof switchView === 'function') switchView('sql');
        const ta = document.getElementById('sqlInput');
        ta.value = d.source || '';
        if (typeof syncSqlHighlight === 'function') syncSqlHighlight();
        window.__editRoutine = { s: schema, name, kind };
        const bar = document.getElementById('procBar');
        document.getElementById('procName').textContent = `编辑 ${kind} · ${schema ? schema + '.' : ''}${name}`;
        bar.style.display = 'flex';
        toast('已载入 ' + kind + ' 源码, 可编辑后保存重建');
      } catch (e) { toast('载入源码失败: ' + e.message, true); }
    }
    function prefillForm(c) {
      const t = c.db_type || 'mysql';
      const sel = document.getElementById('cType'); if (sel) sel.value = t;
      if (t === 'sqlite') {
        const db = document.getElementById('cDbSqlite'); if (db) db.value = c.database || '';
        const pwd = document.getElementById('cPwdSqlite'); if (pwd) pwd.value = c.pwd || '';
      } else {
        const srv = document.getElementById('cServer'); if (srv) srv.value = c.server || '';
        const port = document.getElementById('cPort'); if (port) port.value = c.port || '';
        const db = document.getElementById('cDb'); if (db) db.value = c.database || '';
        const uid = document.getElementById('cUid'); if (uid) uid.value = c.uid || '';
      }
      onTypeChange();
    }
    function fillQuick() {
      const sel = document.getElementById('connQuick');
      if (!sel) return;
      sel.innerHTML = '<option value="">— 手动输入 —</option>' +
        CONNECTIONS.map(c => `<option value="${esc(c.name)}">${esc(c.name)} · ${esc(c.db_type)} · ${esc(c.server || '')}${c.port ? ':' + c.port : ''}</option>`).join('');
    }
    function applyQuick() {
      const sel = document.getElementById('connQuick');
      const name = sel && sel.value;
      if (!name) return;
      const c = CONNECTIONS.find(x => x.name === name);
      if (!c) return;
      prefillForm(c);
      // 已知库名预填到数据库框（取第一个）
      const dbEl = document.getElementById('cDb');
      if (dbEl && c.databases && c.databases.length) { dbEl.value = c.databases[0]; }
      toast('已填入「' + name + '」，请补全密码后连接');
    }
    function toggleTblGroup(head) {
      const body = head.nextElementSibling;
      if (!body) return;
      const collapsed = body.style.display === 'none';
      body.style.display = collapsed ? '' : 'none';
      const caret = head.querySelector('.tbl-group-caret');
      if (caret) caret.textContent = collapsed ? '▾' : '▸';
    }
    // ------------------------------
    // 连接内选库: 不退出连接切换 SQL 目标库, 表树按 schema 分组支持多库并行
    // ------------------------------
    let DBS = [], curDb = '';
    async function initDbSwitch() {
      const sel = document.getElementById('dbSwitch');
      if (!sel) return;
      try {
        const dbs = await api(API + '/api/databases', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
        DBS = Array.isArray(dbs) ? dbs : [];
      } catch (e) { DBS = []; }
      const opts = ['<option value="">全部库(按库分组)</option>'].concat(DBS.map(d => `<option value="${escAttr(d)}">${esc(d)}</option>`)).join('');
      sel.innerHTML = opts;
      curDb = (CONN && CONN.database && DBS.includes(CONN.database)) ? CONN.database : '';
      sel.value = curDb;
      sel.style.display = '';
      renderTables('');
    }
    async function onDbSwitch() {
      const v = document.getElementById('dbSwitch').value;
      if (!v) {
        // 选「全部库」: 恢复连接时的完整表列表
        if (FULL_TABLES != null) TABLES = FULL_TABLES;
        store.set('curDb', '');
        if (typeof loadRoutines === 'function') loadRoutines();
        return;
      }
      if (CONN && CONN.db_type !== 'mongodb' && CONN.db_type !== 'redis') {
        try {
          if (FULL_TABLES == null) FULL_TABLES = TABLES.slice(); // 首次切库前缓存完整列表
          const cc = Object.assign({}, CONN, { database: v });
          const d = await api(API + '/api/connect', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cc) });
          if (!d.error) { SESSION = d.session || SESSION; CONN = d.connection || cc; TABLES = d.tables || []; }
        } catch (e) { toast('加载该库表失败: ' + e.message, true); }
      }
      store.set('curDb', v);
      if (typeof loadRoutines === 'function') loadRoutines(); // 切库后重新拉该库 routines
    }
    // 状态订阅: 当前库变化 -> 表树/提示自动刷新(状态驱动)
    store.watch('curDb', v => {
      curDb = v;
      renderTables('');
      toast(v ? 'SQL 控制台目标库: ' + v : '显示全部库(按库分组), SQL 需写全限定名或选库');
    });
    // ---- Navicat 风格树: 连接 → 库 → schema → 类型分组(表/视图/函数/触发器), 惰性加载 ----
    let treeCache = {};      // db -> {tables, routines}  (按库惰性加载缓存)
    let treeExpanded = new Set();
    const OBJ_ICON = { Table: '📋', View: '👁️', Procedure: 'ƒ', Function: 'ƒ', Trigger: '🔔' };
    function treeDbList() {
      // 库列表: 连接库优先 + /api/databases 全部
      const cur = (CONN && CONN.database) ? CONN.database : (TABLES[0] && TABLES[0].schema) || '';
      const list = [];
      if (cur) list.push(cur);
      (DBS || []).forEach(d => { if (!list.includes(d)) list.push(d); });
      return list;
    }
    function treeObj(db) {
      // 连接库直接用内存 TABLES/ROUTINES(切库/加载后更新); 其他库用按需缓存
      const cur = (CONN && CONN.database) ? CONN.database : (TABLES[0] && TABLES[0].schema) || '';
      if (db === cur) return { tables: TABLES, routines: ROUTINES };
      return treeCache[db] || null;
    }
    async function loadDbObjects(db) {
      try {
        const hdrs = {};
        if (SESSION) hdrs['X-Session'] = SESSION; else if (CONN) hdrs['X-Conn'] = encConn(CONN);
        const r = await fetch(API + '/api/objects', { method: 'POST', headers: Object.assign({ 'Content-Type': 'application/json' }, hdrs), body: JSON.stringify({ database: db }) });
        const d = await r.json().catch(() => ({}));
        if (!d.error) treeCache[db] = { tables: d.tables || [], routines: d.routines || [] };
        else toast('加载对象失败: ' + d.error, true);
      } catch (e) { toast('加载对象失败: ' + e.message, true); }
    }
    function toggleTree(id, el) {
      if (treeExpanded.has(id)) {
        // 折叠: 移出展开集合并重渲染(否则子内容仍留在 DOM)
        treeExpanded.delete(id);
        renderTables('');
        return;
      }
      treeExpanded.add(id);
      if (id.startsWith('db:')) {
        const db = id.slice(3);
        if (!treeObj(db)) {
          loadDbObjects(db).then(() => renderTables(''));
        }
        selectedObj = null;  // 选中库级: 清对象选中
        renderProps();
        renderCrumbs();
        store.set('curDb', db);  // SQL 控制台目标库跟随树展开
      }
      renderTables('');
      renderStatusBar();
    }
    function tnode(id, label, open) {
      return `<div class="tnode${open ? ' open' : ''}" onclick="toggleTree('${id}', this)"><span class="caret">${open ? '▾' : '▸'}</span><span class="tl">${label}</span></div>`;
    }
    function tgrp(title, arr, itemFn) {
      const body = arr.length ? arr.map(itemFn).join('') : '<div class="empty2" style="padding:3px 10px;font-size:12px">无</div>';
      return `<div class="tbl-group"><div class="tbl-group-head" onclick="toggleTblGroup(this)"><span>${title} (${arr.length})</span><span class="tbl-group-caret">▾</span></div><div class="tbl-group-body">${body}</div></div>`;
    }
    function renderDbObjects(db, obj) {
      // schema 语义: 若所有对象 schema 都等于库名(MySQL), 省略 schema 层; 否则(MSSQL dbo/guest)按 schema 分组
      const sameAsDb = obj.tables.every(t => t.schema === db) && obj.routines.every(r => r.schema === db);
      if (sameAsDb) return renderObjGroups(obj, null);
      const schemas = [...new Set([...obj.tables.map(t => t.schema || '(默认)'), ...obj.routines.map(r => r.schema || '(默认)')])];
      return schemas.map(s => {
        const sid = 'sch:' + db + ':' + s;
        const sopen = !treeExpanded.has(sid); // 默认展开, 折叠后记录
        return tnode(sid, '📁 ' + esc(s), sopen) +
          (sopen ? '<div class="tbl-group-body">' + renderObjGroups(obj, s) + '</div>' : '');
      }).join('');
    }
    function renderObjGroups(obj, schema) {
      const flt = arr => arr.filter(x => !schema || x.schema === schema);
      const tables = flt(obj.tables).filter(t => t.type !== 'View');
      const views = flt(obj.tables).filter(t => t.type === 'View');
      const pros = flt(obj.routines).filter(r => r.type === 'Procedure');
      const funcs = flt(obj.routines).filter(r => r.type === 'Function');
      const trigs = flt(obj.routines).filter(r => r.type === 'Trigger');
      let h = '';
      h += tgrp(OBJ_ICON.Table + ' 表', tables, tableItemHtml);
      h += tgrp(OBJ_ICON.View + ' 视图', views, tableItemHtml);
      h += tgrp(OBJ_ICON.Function + ' 函数', [...funcs, ...pros], routineItemHtml);
      h += tgrp(OBJ_ICON.Trigger + ' 触发器', trigs, routineItemHtml);
      return h;
    }
    function renderTree() {
      const list = document.getElementById('tblList');
      const connName = (CONN && (CONN.name || CONN.server || CONN.database)) || '连接';
      const connOpen = !treeExpanded.has('conn:root'); // 默认展开, 可折叠
      let html = tnode('conn:root', '🔗 ' + esc(connName), connOpen);
      if (connOpen) {
        html += '<div class="tbl-group-body">';
        treeDbList().forEach(db => {
          const dbId = 'db:' + db;
          const open = treeExpanded.has(dbId);
          const obj = treeObj(db);
          html += tnode(dbId, '🗄️ ' + esc(db), open);
          if (open && obj) html += '<div class="tbl-group-body">' + renderDbObjects(db, obj) + '</div>';
          else if (open) html += '<div class="tbl-group-body"><div class="empty2" style="padding:3px 10px;font-size:12px">加载中...</div></div>';
        });
        html += '</div>';
      }
      list.innerHTML = html;
      renderStatusBar();
    }
    function renderFlatSearch(f) {
      // 搜索: 平铺所有匹配对象(表/视图/函数/触发器)
      const list = document.getElementById('tblList');
      const items = TABLES.filter(t => (t.schema + '.' + t.name + ' ' + (t.type || '')).toLowerCase().includes(f));
      const tables = items.filter(t => t.type !== 'View');
      const views = items.filter(t => t.type === 'View');
      const bySchema = new Map();
      for (const t of tables) {
        const k = t.schema || '(默认)';
        if (!bySchema.has(k)) bySchema.set(k, []);
        bySchema.get(k).push(t);
      }
      let html = '';
      for (const [k, arr] of bySchema) html += group('库: ' + k, arr);
      html += group('视图', views);
      const ritems = ROUTINES.filter(r => (r.schema + '.' + r.name).toLowerCase().includes(f));
      html += rgroup('存储过程', ritems.filter(r => r.type === 'Procedure'));
      html += rgroup('函数', ritems.filter(r => r.type === 'Function'));
      html += rgroup('触发器', ritems.filter(r => r.type === 'Trigger'));
      list.innerHTML = html || '<div class="empty2">无匹配的表或视图</div>';
      renderStatusBar();
    }
    // ---- 通用对象渲染(树分组/搜索平铺共用) ----
    let selectedObj = null; // 侧边栏当前选中对象: {db, schema, name, type}
    function tableItemHtml(t) {
      return `<div class="item" data-s="${esc(t.schema)}" data-t="${esc(t.name)}" data-type="${esc(t.type || 'Table')}" onclick="selectTableItem(this)" ondblclick="openTable('${escAttr(t.schema)}','${escAttr(t.name)}')" oncontextmenu="tableCtxMenu(event,'${escAttr(t.schema)}','${escAttr(t.name)}')" title="单击选中，双击打开，右键更多操作"><span>${esc(t.name)}</span><span class="ty">${esc(t.type)}</span></div>`;
    }
    function routineItemHtml(r) {
      return `<div class="item" data-s="${esc(r.schema)}" data-t="${esc(r.name)}" data-type="${esc(r.type || 'Function')}" onclick="selectTableItem(this)" ondblclick="openRoutine('${escAttr(r.schema)}','${escAttr(r.name)}','${escAttr(r.type)}')" title="双击编辑源码"><span>${esc(r.name)}</span><span class="ty">${esc(r.type)}</span></div>`;
    }
    function group(title, arr) {
      return arr.length ? `<div class="tbl-group"><div class="tbl-group-head" onclick="toggleTblGroup(this)"><span>${title} (${arr.length})</span><span class="tbl-group-caret">▾</span></div><div class="tbl-group-body">${arr.map(tableItemHtml).join('')}</div></div>` : '';
    }
    function rgroup(title, arr) {
      return `<div class="tbl-group"><div class="tbl-group-head" onclick="toggleTblGroup(this)"><span>${title} (${arr.length})</span><span class="tbl-group-caret">▾</span></div><div class="tbl-group-body">${arr.length ? arr.map(routineItemHtml).join('') : '<div class="empty2" style="padding:4px 8px;font-size:12px">无</div>'}</div></div>`;
    }
    function renderTables(filter) {
      const f = (filter || '').toLowerCase();
      if (f) { renderFlatSearch(f); return; }
      renderTree();
    }
    function selectTableItem(el) {
      document.querySelectorAll('.side .item').forEach(x => x.classList.remove('active'));
      el.classList.add('active');
      // 记录侧边栏当前选中对象 -> 底部状态条跟随
      selectedObj = {
        db: curDb || (CONN && CONN.database) || '',
        schema: el.dataset.s || '',
        name: el.dataset.t || '',
        type: el.dataset.type || 'Table'
      };
      renderStatusBar();
      renderProps();
      renderCrumbs();
    }
    // ---- 左侧树面包屑: 选中对象的完整路径(库/schema/类型/对象) ----
    const OBJ_ICON3 = { Table: '📋', View: '👁️', Procedure: 'ƒ', Function: 'ƒ', Trigger: '🔔' };
    function renderCrumbs() {
      const el = document.getElementById('treeCrumbs');
      if (!el) return;
      if (!selectedObj || !selectedObj.name) { el.style.display = 'none'; el.innerHTML = ''; return; }
      el.style.display = 'flex';
      const o = selectedObj;
      const segs = [];
      if (o.db) segs.push({ label: '🗄️ ' + o.db, type: 'database' });
      if (o.schema && o.schema !== o.db) segs.push({ label: '📁 ' + o.schema, type: 'schema' });
      const ico = OBJ_ICON3[o.type] || '📄';
      segs.push({ label: ico + ' ' + (o.type || 'Table'), type: 'kind' });
      segs.push({ label: o.name, type: 'object' });
      el.innerHTML = '<span class="crumb-label">📍</span>' + segs.map(s => `<span class="crumb-seg" title="${esc(s.label)}">${esc(s.label)}</span>`).join('<span class="crumb-sep">›</span>');
    }
    // ---- 右侧属性面板: 选中对象详情(字段/索引/基本信息) ----
    async function renderProps() {
      const panel = document.getElementById('propsPanel');
      const body = document.getElementById('propsBody');
      if (!panel || !selectedObj || !selectedObj.name) { if (panel) panel.style.display = 'none'; return; }
      panel.style.display = 'flex';
      const o = selectedObj;
      const base = () => {
        let h = '';
        h += `<div class="p-item"><label>对象</label><span>${esc(o.name)}</span></div>`;
        h += `<div class="p-item"><label>类型</label><span>${esc(o.type || '')}</span></div>`;
        if (o.schema) h += `<div class="p-item"><label>Schema</label><span>${esc(o.schema)}</span></div>`;
        if (o.db) h += `<div class="p-item"><label>数据库</label><span>${esc(o.db)}</span></div>`;
        return h;
      };
      body.innerHTML = base() + '<div class="empty2" style="padding:10px;font-size:12px">加载中...</div>';
      if (o.type === 'Table' || o.type === 'View') {
        try {
          const [cols, idxs] = await Promise.all([
            api(API + '/api/columns?' + qp({ s: o.schema, t: o.name })),
            api(API + '/api/indexes?' + qp({ s: o.schema, t: o.name }))
          ]);
          let h = base();
          h += `<div class="p-sec">字段 (${cols.length})</div><table class="p-tbl"><thead><tr><th>名</th><th>类型</th><th>可空</th><th>键</th></tr></thead><tbody>`;
          cols.forEach(c => { h += `<tr><td>${esc(c.name)}</td><td>${esc(c.type)}</td><td>${c.nullable ? '是' : '否'}</td><td>${c.is_pk ? 'PK' : ''}</td></tr>`; });
          h += '</tbody></table>';
          if (idxs && idxs.length) {
            h += `<div class="p-sec">索引 (${idxs.length})</div><table class="p-tbl"><thead><tr><th>名</th><th>字段</th><th>唯一</th></tr></thead><tbody>`;
            idxs.forEach(i => { h += `<tr><td>${esc(i.name)}</td><td>${esc(i.columns)}</td><td>${i.is_unique ? '是' : ''}</td></tr>`; });
            h += '</tbody></table>';
          }
          body.innerHTML = h;
        } catch (e) { body.innerHTML = base() + '<div class="empty2" style="padding:8px;font-size:12px">加载失败: ' + esc(e.message) + '</div>'; }
      } else {
        body.innerHTML = base();
      }
    }
    // ------------------------------
    // 多文档标签：右侧可同时打开多张表查看与切换
    // ------------------------------
    let TABS = [], activeId = null, tabSeq = 0;
    function activeTab() { return TABS.find(x => x.id === activeId) || null; }
    function tabLabel(t) {
      // 标题带数据库名: MSSQL 显示 库.schema.表; MySQL 库==schema 时去重显示 库.表
      if (t.db && t.db !== t.s) return t.db + '.' + (t.s ? t.s + '.' : '') + t.t;
      return (t.s ? t.s + '.' : '') + t.t;
    }
    function flushActive() {
      if (activeId == null) return;
      const tab = activeTab();
      if (!tab) return;
      tab.page = currentPage;
      tab.size = document.getElementById('sizeSel').value;
      tab.where = document.getElementById('whereBox').value;
      tab.filters = JSON.parse(JSON.stringify(filters));
      tab.sort = curSort;
      tab.tab = currentTab === 'sql' ? 'data' : currentTab; // SQL 视图是全局, 不写回标签
      tab.meta = currentMeta;
    }
    function renderDocTabs() {
      const bar = document.getElementById('doctabs');
      if (!TABS.length) { bar.innerHTML = ''; bar.style.display = 'none'; return; }
      bar.style.display = 'flex';
      bar.innerHTML = TABS.map(t => `<div class="doctab ${t.id === activeId ? 'active' : ''}" onclick="activateTab(${t.id})" title="${esc(tabLabel(t))}"><span class="nm">${esc(tabLabel(t))}</span><span class="x" onclick="closeDocTab(${t.id}, event)">×</span></div>`).join('');
    }
    function switchNextTab() {
      if (!TABS.length) return;
      const idx = TABS.findIndex(x => x.id === activeId);
      const next = TABS[(idx + 1) % TABS.length];
      activateTab(next.id);
    }
    async function activateTab(id) {
      if (editingCell) cancelEdit();
      if (activeId != null) flushActive();
      activeId = id;
      const tab = activeTab();
      if (!tab) return;
      current = { s: tab.s, t: tab.t };
      currentPage = tab.page;
      currentMeta = tab.meta;
      filters = JSON.parse(JSON.stringify(tab.filters));
      curSort = tab.sort || null;
      currentTab = tab.tab;
      document.getElementById('sizeSel').value = tab.size;
      document.getElementById('whereBox').value = tab.where;
      document.getElementById('curTable').textContent = tabLabel(tab);
      document.getElementById('toolbar').style.display = 'flex';
      document.getElementById('tabs').style.display = 'flex';
      document.querySelectorAll('.side .item').forEach(el => { el.classList.toggle('active', el.dataset.s === tab.s && el.dataset.t === tab.t); });
      renderDocTabs();
      if (tab.tab === 'data') {        document.getElementById('toolbar').style.display = 'flex';
        document.getElementById('grid').style.display = '';
        document.getElementById('pager').style.display = 'flex';
        if (tab.meta) { renderGrid(tab.meta); } else { await loadData(1); }
      } else {
        document.getElementById('toolbar').style.display = 'none';
        document.getElementById('grid').style.display = '';
        document.getElementById('pager').style.display = 'none';
        await loadStruct();
      }
    }
    function closeDocTab(id, ev) {
      ev.stopPropagation();
      const idx = TABS.findIndex(x => x.id === id);
      if (idx < 0) return;
      const wasActive = (id === activeId);
      TABS.splice(idx, 1);
      if (!TABS.length) {
        activeId = null; current = null; currentMeta = null; filters = {}; currentTab = 'data';
        document.getElementById('toolbar').style.display = 'none';
        document.getElementById('tabs').style.display = 'none';
        document.getElementById('grid').innerHTML = '';
        document.getElementById('pager').style.display = 'none';
        document.querySelectorAll('.side .item').forEach(el => el.classList.remove('active'));
        renderDocTabs();
        return;
      }
      if (wasActive) { activateTab(TABS[Math.min(idx, TABS.length - 1)].id); }
      else { renderDocTabs(); }
    }
    function connKey() {
      if (CONN && CONN.name) return CONN.name;
      return (CONN ? (CONN.db_type + '_' + (CONN.server || '') + '_' + (CONN.database || '')) : 'anon');
    }
    function tabStateKey(s, t) { return 'dbm_tabstate_' + connKey() + '_' + s + '.' + t; }
    function saveTabState() {
      if (!current) return;
      try { localStorage.setItem(tabStateKey(current.s, current.t), JSON.stringify({ filters, sort: curSort, size: document.getElementById('sizeSel').value })); } catch (e) {}
    }
    function loadTabStateFor(s, t) {
      try {
        const raw = localStorage.getItem(tabStateKey(s, t));
        return raw ? JSON.parse(raw) : null;
      } catch (e) { return null; }
    }
    async function openTable(s, t) {
      // 库上下文: 侧边栏选中对象的库 > 当前库 > 连接库
      const db = (selectedObj && selectedObj.db) || curDb || (CONN && CONN.database) || '';
      let tab = TABS.find(x => x.s === s && x.t === t && x.db === db);
      if (!tab) {
        const st = loadTabStateFor(s, t);
        tab = { id: ++tabSeq, db, s, t, session: null, page: 1, size: (st && st.size) || document.getElementById('sizeSel').value, where: '', filters: (st && st.filters) || {}, sort: (st && st.sort) || null, tab: 'data', meta: null };
        TABS.push(tab);
      }
      await activateTab(tab.id);
      // 跨库表: 与当前连接库不同 -> 为该库建立独立会话(数据请求自动走 tab.session)
      const curDbName = (CONN && CONN.database) || (TABLES[0] && TABLES[0].schema) || '';
      if (db && db !== curDbName && !tab.session && CONN && CONN.db_type !== 'sqlite' && CONN.db_type !== 'mongodb' && CONN.db_type !== 'redis') {
        try {
          let d;
          if (CONN && CONN.name) {
            // 按名直连 + 覆盖库: 后端取保存连接(含解密密码)再应用 database, 避免丢失凭据
            d = await api(API + '/api/connect', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: CONN.name, database: db }) });
          } else {
            // 手动连接: CONN 含明文密码(仅内存), 直接带库
            const cc = Object.assign({}, CONN, { database: db });
            d = await api(API + '/api/connect', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cc) });
          }
          if (!d.error) {
            tab.session = d.session || null;
            if (activeTab() && activeTab().id === tab.id && currentTab === 'data') loadData(1);
          }
        } catch (e) { toast('跨库加载失败: ' + e.message, true); }
      }
    }
    function switchView(view) {
      // 应用级视图切换: browse=数据浏览(表树+表tab+网格) / sql=SQL 工作台(独立全宽)
      const browse = document.getElementById('browseView');
      const sqlView = document.getElementById('sqlView');
      const bBtn = document.getElementById('viewBrowseBtn');
      const sBtn = document.getElementById('viewSqlBtn');
      if (view === 'sql') {
        browse.style.display = 'none';
        sqlView.style.display = 'flex';
        bBtn.classList.remove('primary'); sBtn.classList.add('primary');
        renderSqlHist();
      } else {
        browse.style.display = '';
        sqlView.style.display = 'none';
        sBtn.classList.remove('primary'); bBtn.classList.add('primary');
        if (currentTab === 'data') { if (currentMeta) renderGrid(currentMeta); else if (activeTab()) loadData(1); }
        else if (currentTab === 'struct' && activeTab()) loadStruct();
      }
    }
    function switchTab(tab) {
      const at = activeTab();
      if (!at) return;
      currentTab = tab; at.tab = tab;
      document.querySelectorAll('.tab').forEach(el => { el.classList.toggle('active', el.dataset.tab === tab); });
      if (tab === 'data') {
        document.getElementById('toolbar').style.display = 'flex';
        document.getElementById('grid').style.display = '';
        document.getElementById('pager').style.display = 'flex';
        if (currentMeta) renderGrid(currentMeta); else loadData(1);
      } else if (tab === 'struct') {
        document.getElementById('toolbar').style.display = 'none';
        document.getElementById('grid').style.display = '';
        document.getElementById('pager').style.display = 'none';
        loadStruct();
      }
    }
