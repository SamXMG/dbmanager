// dbmanager 前端 - SQL编辑器/补全/多查询tab/导入导出/ER/同步等
    function formatSql() {
      const ta = document.getElementById('sqlInput');
      if (!ta || !ta.value.trim()) { toast('没有可格式化的 SQL', true); return; }
      const combos = ['SELECT TOP', 'LEFT JOIN', 'RIGHT JOIN', 'INNER JOIN', 'OUTER JOIN', 'UNION ALL', 'INSERT INTO', 'DELETE FROM', 'CREATE TABLE', 'ALTER TABLE', 'DROP TABLE', 'ORDER BY', 'GROUP BY'];
      const singles = ['SELECT', 'FROM', 'WHERE', 'HAVING', 'JOIN', 'ON', 'SET', 'VALUES', 'UPDATE', 'LIMIT', 'TOP', 'CASE', 'WHEN', 'THEN', 'ELSE', 'END', 'UNION', 'AND', 'OR'];
      let out = ta.value;
      const ph = combos.map((c, i) => ['\u0001' + i + '\u0001', c]);
      for (const [p, c] of ph) out = out.replace(new RegExp('\\b' + c.replace(/ /g, '\\s+') + '\\b', 'gi'), p);
      for (const kw of singles) out = out.replace(new RegExp('\\b' + kw + '\\b', 'gi'), m => '\n' + m.toUpperCase());
      for (const [p, c] of ph) out = out.split(p).join('\n' + c.toUpperCase());
      out = out.replace(/\n\s*(AND|OR)\b/gi, '\n  $1');
      out = out.replace(/[ \t]+\n/g, '\n').replace(/\n{2,}/g, '\n').replace(/^\n+/, '').trim();
      ta.value = out;
      syncSqlHighlight();
      toast('SQL 已格式化');
    }
    function escHtml(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
    const SQL_KW_SET = new Set(('SELECT TOP DISTINCT FROM WHERE AND OR NOT IN EXISTS LIKE BETWEEN IS NULL ORDER BY GROUP HAVING AS JOIN INNER LEFT RIGHT OUTER ON SET VALUES INSERT INTO UPDATE DELETE CREATE TABLE ALTER DROP INDEX UNIQUE PRIMARY KEY FOREIGN REFERENCES CASE WHEN THEN ELSE END UNION LIMIT OFFSET COUNT SUM AVG MAX MIN COALESCE NULLIF CAST CONVERT GETDATE DATEADD DATEDIFF LEN LOWER UPPER TRIM REPLACE SUBSTRING ISNULL CURRENT_DATE NOW').toLowerCase().split(' '));
    function highlightSql(src) {
      const s = String(src);
      const tblSet = new Set();
      (TABLES || []).forEach(t => { tblSet.add(t.name.toLowerCase()); if (t.schema) tblSet.add((t.schema + '.' + t.name).toLowerCase()); });
      const colSet = new Set(((currentMeta && currentMeta.columns) || []).map(c => c.name.toLowerCase()));
      const toks = [];
      const p = x => { toks.push(x); return '\u0000A' + (toks.length - 1) + '\u0000'; };
      let t = s.replace(/(?:'(?:''|[^'])*')|(?:"(?:[^"\n]*?)")|(?:--[^\n]*)|(?:\/\*[\s\S]*?\*\/)|(\b\d+(?:\.\d+)?\b)|([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?)/g, (m, num, ident) => {
        const c0 = m.charCodeAt(0);
        if (c0 === 39 || c0 === 34) return p('<span class="sql-s">' + escHtml(m) + '</span>');
        if (m.startsWith('--') || m.startsWith('/*')) return p('<span class="sql-c">' + escHtml(m) + '</span>');
        if (num) return p('<span class="sql-n">' + m + '</span>');
        if (ident) {
          const low = m.toLowerCase();
          const last = low.includes('.') ? low.slice(low.lastIndexOf('.') + 1) : low;
          if (SQL_KW_SET.has(low) || SQL_KW_SET.has(last)) return p('<span class="sql-k">' + m.toUpperCase() + '</span>');
          if (tblSet.has(low) || tblSet.has(last)) return p('<span class="sql-tbl">' + m + '</span>');
          if (colSet.has(low) || colSet.has(last)) return p('<span class="sql-col">' + m + '</span>');
        }
        return m;
      });
      t = escHtml(t);
      return t.replace(/\u0000A(\d+)\u0000/g, (_, i) => toks[+i]);
    }
    function syncSqlHighlight() {
      const ta = document.getElementById('sqlInput');
      const pre = document.getElementById('sqlHigh');
      if (!ta || !pre) return;
      pre.innerHTML = highlightSql(ta.value) + '\n';
      pre.scrollTop = ta.scrollTop;
      pre.scrollLeft = ta.scrollLeft;
    }
    (function bindSqlHighlight() {
      const ta = document.getElementById('sqlInput');
      if (!ta) return;
      ta.addEventListener('input', () => { syncSqlHighlight(); updateSqlAc(); });
      ta.addEventListener('scroll', () => { const pre = document.getElementById('sqlHigh'); if (pre) { pre.scrollTop = ta.scrollTop; pre.scrollLeft = ta.scrollLeft; } positionSqlAc(); });
      syncSqlHighlight();
    })();
    let SQL_AC_IDX = 0;
    // MySQL/MariaDB 常见保留字: 补全表/字段名时自动加反引号, 避免 "SELECT * FROM leave" 这类语法错误
    const MYSQL_RESERVED = new Set(('LEAVE ORDER GROUP KEY DESC RANK USER REFERENCES CHECK INTERVAL NATURAL PRIMARY FOREIGN TABLE INDEX SELECT FROM WHERE AND OR NOT IN EXISTS LIKE BETWEEN IS NULL UNION JOIN INNER LEFT RIGHT OUTER ON SET VALUES UPDATE DELETE CREATE ALTER DROP TRIGGER PROCEDURE FUNCTION DATABASE SCHEMA DEFAULT CONSTRAINT UNIQUE COLLATE COLUMN VIEW VALUE').split(' '));
    function quoteSqlIdent(name) {
      const t = CONN ? CONN.db_type : '';
      if (t === 'mysql' && MYSQL_RESERVED.has(String(name).toUpperCase())) return '`' + name + '`';
      return name;
    }
    // ---- 表名/别名/系统对象 . 字段补全（点号后提示列） ----
    let SQL_AC_GEN = 0;                 // 异步拉列的竞态令牌
    const AC_COL_CACHE = {};            // "schema|table" -> 列数组（按需从后端拉取缓存）
    function getDotContext() {
      // 光标前是否处于 "<对象>." 上下文: 返回 {ref, typed, insertStart}
      const ta = document.getElementById('sqlInput');
      const pos = ta.selectionStart;
      const prefix = ta.value.slice(0, pos);
      const m = prefix.match(/([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\.([\w$]*)$/);
      if (!m) return null;
      return { ref: m[1], typed: m[2], insertStart: pos - m[2].length };
    }
    function parseSqlAliases(sqlText) {
      // 从 SQL 提取 FROM/JOIN 后的表引用与别名: {别名/表名(小写) -> 表引用}; 不传参时读当前编辑器
      const ta = document.getElementById('sqlInput');
      const src = (sqlText !== undefined && sqlText !== null) ? sqlText : (ta && ta.value) || '';
      const map = {};
      const re = /(?:FROM|JOIN)\s+([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*){0,2})(?:\s+(?:AS\s+)?([A-Za-z_$][\w$]*))?/gi;
      let m;
      while ((m = re.exec(src))) {
        const tableRef = m[1];
        map[tableRef.toLowerCase()] = tableRef;           // 表名自身也可触发
        const alias = m[2];
        if (alias && !SQL_KW_SET.has(alias.toLowerCase())) {
          map[alias.toLowerCase()] = tableRef;            // 别名 -> 真实表
        }
      }
      return map;
    }
    async function getTableColsCached(schema, table) {
      // 按需从后端拉列(缓存), 失败返回 null 不阻塞补全
      const key = (schema || '') + '|' + table;
      if (AC_COL_CACHE[key]) return AC_COL_CACHE[key];
      try {
        const d = await api(API + '/api/columns?' + qp({ s: schema || '', t: table }));
        if (Array.isArray(d)) { AC_COL_CACHE[key] = d; return d; }
      } catch (e) { /* 忽略: 未知对象/无权限等场景静默 */ }
      return null;
    }
    async function resolveDotCandidates(dc) {
      // 解析 <对象>. 到具体表并返回其字段候选
      const ref = dc.ref.toLowerCase();
      const aliases = parseSqlAliases();
      let schema = '', table = '';
      const tableRef = aliases[ref];                       // 1) 别名映射
      if (tableRef) {
        const parts = tableRef.split('.');
        if (parts.length === 2) { schema = parts[0]; table = parts[1]; }
        else { table = parts[0]; }
      } else if (ref.includes('.')) {                      // 2) schema.表 或 系统对象(sys.xxx 等)
        const idx = ref.lastIndexOf('.');
        schema = ref.slice(0, idx);
        table = ref.slice(idx + 1);
      } else {                                             // 3) 裸表名 -> 在 TABLES 中解析 schema
        table = ref;
        const hits = (TABLES || []).filter(t => t.name.toLowerCase() === ref);
        if (hits.length === 1) schema = hits[0].schema || '';
        else if (hits.length > 1) schema = (hits.find(t => t.schema) || hits[0]).schema || '';
      }
      if (!table) return null;
      const cols = await getTableColsCached(schema, table);
      if (!cols || !cols.length) return null;
      const typed = dc.typed.toLowerCase();
      const items = cols.filter(c => !typed || (c.name || '').toLowerCase().startsWith(typed))
                        .map(c => ({ label: c.name, kind: 'c' }))
                        .slice(0, 50);
      return { items, insertStart: dc.insertStart };
    }

    function buildSqlCandidates(prefix) {
      const p = prefix.toLowerCase();
      const out = [], seen = new Set();
      const push = (label, kind) => { const k = kind + ':' + label.toLowerCase(); if (!seen.has(k)) { seen.add(k); out.push({ label, kind }); } };
      SQL_KW_SET.forEach(k => { if (k.startsWith(p)) push(k.toUpperCase(), 'k'); });
      (TABLES || []).forEach(t => { if (t.name.toLowerCase().startsWith(p)) push(quoteSqlIdent(t.name), 't'); });
      ((currentMeta && currentMeta.columns) || []).forEach(c => { if (c.name.toLowerCase().startsWith(p)) push(quoteSqlIdent(c.name), 'c'); });
      return out.slice(0, 50);
    }
    function getSqlWord() {
      const ta = document.getElementById('sqlInput');
      const pos = ta.selectionStart;
      const text = ta.value;
      let start = pos;
      while (start > 0 && /[\w$]/.test(text[start - 1])) start--;
      return { start, end: pos, word: text.slice(start, pos) };
    }
    function renderSqlAc(items) {
      const ac = document.getElementById('sqlAc');
      ac._items = items;
      const tag = { k: '关', t: '表', c: '字段' };
      ac.innerHTML = items.map((it, i) => `<div class="ac-item${i === SQL_AC_IDX ? ' cur' : ''}" data-i="${i}" onmousedown="event.preventDefault();sqlAcPick(${i})"><span class="ac-tag ${it.kind}">${tag[it.kind]}</span><span>${esc(it.label)}</span></div>`).join('');
    }
    function positionSqlAc() {
      const ta = document.getElementById('sqlInput');
      const ac = document.getElementById('sqlAc');
      if (!ta || !ac || !ac.classList.contains('show')) return;
      const pos = ta.selectionStart;
      const line = ta.value.slice(0, pos).split('\n').length;
      const lineH = 17; // Consolas 13px 行高
      ac.style.top = Math.max(2, line * lineH - ta.scrollTop + 2) + 'px';
    }
    async function updateSqlAc() {
      const ac = document.getElementById('sqlAc');
      const dc = getDotContext();
      if (dc) {
        // 表名/别名/系统对象 + "." -> 异步拉该对象字段
        const gen = ++SQL_AC_GEN;
        const res = await resolveDotCandidates(dc);
        if (gen !== SQL_AC_GEN) return;              // 输入已变化, 丢弃过期结果
        if (!res || !res.items.length) { ac.classList.remove('show'); return; }
        SQL_AC_IDX = 0;
        ac._insertStart = res.insertStart;
        renderSqlAc(res.items);
        ac.classList.add('show');
        positionSqlAc();
        return;
      }
      const { word } = getSqlWord();
      if (!word) { ac.classList.remove('show'); return; }
      const items = buildSqlCandidates(word);
      if (!items.length) { ac.classList.remove('show'); return; }
      SQL_AC_IDX = 0;
      ac._insertStart = null;
      renderSqlAc(items);
      ac.classList.add('show');
      positionSqlAc();
    }
    function moveSqlAc(d) {
      const ac = document.getElementById('sqlAc');
      const items = ac._items || [];
      if (!items.length) return;
      SQL_AC_IDX = (SQL_AC_IDX + d + items.length) % items.length;
      renderSqlAc(items);
    }
    function applySqlAc(word) {
      const ta = document.getElementById('sqlInput');
      const ac = document.getElementById('sqlAc');
      let start, end;
      const dc = getDotContext();
      if (dc && typeof ac._insertStart === 'number') {
        start = ac._insertStart;                 // 点号后替换, 保留 "对象."
        end = ta.selectionStart;
      } else {
        const w = getSqlWord();
        start = w.start; end = w.end;
      }
      ta.value = ta.value.slice(0, start) + word + ta.value.slice(end);
      ta.selectionStart = ta.selectionEnd = start + word.length;
      ac.classList.remove('show');
      syncSqlHighlight();
      ta.focus();
    }
    function sqlAcPick(i) {
      const items = (document.getElementById('sqlAc')._items) || [];
      if (items[i]) applySqlAc(items[i].label);
    }
    function hideSqlAc() { document.getElementById('sqlAc').classList.remove('show'); }
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') {
        hideCtxMenu();
        document.getElementById('filterPop').classList.remove('show');
        document.getElementById('mask').classList.remove('show');
        return;
      }
      if (e.key === 'F5') {
        const at = activeTab();
        if (at && at.tab === 'data' && current) { e.preventDefault(); loadData(currentPage); }
        return;
      }
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'F' || e.key === 'f')) {
        e.preventDefault(); formatSql();
      }
    });
    function showModal(html) { document.getElementById('modal').innerHTML = html; document.getElementById('mask').classList.add('show'); }
    function closeModal() { document.getElementById('mask').classList.remove('show'); }
    document.getElementById('mask').addEventListener('click', e => { if (e.target.id === 'mask') closeModal(); });
    // ------------------------------
    // SQL 查询控制台
    // ------------------------------
    function parseCsv(text) {
      const rows = []; let row = [], cur = '', inQ = false;
      for (let i = 0; i < text.length; i++) {
        const ch = text[i];
        if (inQ) {
          if (ch === '"') { if (text[i + 1] === '"') { cur += '"'; i++; } else inQ = false; }
          else cur += ch;
        } else if (ch === '"') inQ = true;
        else if (ch === ',') { row.push(cur); cur = ''; }
        else if (ch === '\n' || ch === '\r') {
          if (ch === '\r' && text[i + 1] === '\n') i++;
          row.push(cur); cur = '';
          if (row.length > 1 || row[0] !== '') rows.push(row);
          row = [];
        } else cur += ch;
      }
      if (cur !== '' || row.length) { row.push(cur); rows.push(row); }
      return rows;
    }
    function openPasteInsert() {
      if (!current) return;
      showModal(`<h3>批量粘贴插入 · ${esc(current.s)}.${esc(current.t)}</h3>
        <div class="field"><label>从 Excel/表格复制数据后粘贴到这里(Ctrl+V)</label><textarea id="pasteBox" rows="8" style="width:100%;box-sizing:border-box" placeholder="列1&#9;列2&#9;列3&#10;值1&#9;值2&#9;值3"></textarea></div>
        <div class="field"><label style="font-size:12px;display:flex;align-items:center;gap:6px"><input type="checkbox" id="pasteHasHeader" checked> 首行是表头(自动匹配列名)</label></div>
        <div class="acts"><button onclick="closeModal()">取消</button><button class="primary" onclick="parsePasteInsert()">解析并导入</button></div>`);
    }
    function parsePasteInsert() {
      const text = document.getElementById('pasteBox').value;
      if (!text.trim()) { toast('请先粘贴数据', true); return; }
      const hasHeader = document.getElementById('pasteHasHeader').checked;
      const lines = text.replace(/\r/g, '').split('\n').filter(l => l.trim() !== '');
      const sepCounts = { '\t': 0, ',': 0, ';': 0 };
      for (const l of lines.slice(0, 5)) for (const s in sepCounts) if (l.includes(s)) sepCounts[s]++;
      const sep = Object.keys(sepCounts).sort((a, b) => sepCounts[b] - sepCounts[a])[0];
      const data = lines.map(l => l.split(sep).map(c => c.trim()));
      if (data.length < (hasHeader ? 2 : 1)) { toast('没有可导入的数据行', true); return; }
      const header = hasHeader ? data[0] : null;
      const body = hasHeader ? data.slice(1) : data;
      const cols = currentMeta.columns.filter(c => !c.identity && !c.computed);
      const n = header ? header.length : (body[0] || []).length;
      window.__pasteRows = body;
      let html = `<h3>确认导入 · ${esc(current.s)}.${esc(current.t)}</h3>`;
      html += `<div style="color:#86909c;font-size:12px;margin-bottom:8px">解析出 <b>${body.length}</b> 行 × <b>${n}</b> 列(分隔符: ${sep === '\t' ? 'Tab' : sep}), 请确认列映射:</div>`;
      for (let i = 0; i < n; i++) {
        const def = header ? header[i] : ('列' + (i + 1));
        const matched = cols.find(c => c.name.toLowerCase() === String(def).toLowerCase());
        html += `<div class="field" style="margin-bottom:6px"><label>${esc(def || ('列' + (i + 1)))}</label><select id="pm_${i}"><option value="">(跳过)</option>${cols.map(c => `<option value="${escAttr(c.name)}" ${matched && matched.name === c.name ? 'selected' : ''}>${esc(c.name)} (${esc(c.type)})</option>`).join('')}</select></div>`;
      }
      html += `<div class="field"><label style="font-size:12px;display:flex;align-items:center;gap:6px"><input type="checkbox" id="pasteTx" checked> 使用事务(可回滚)</label></div>`;
      html += `<div class="acts"><button onclick="openPasteInsert()">返回</button><button class="primary" onclick="doPasteInsert()">导入 ${body.length} 行</button></div>`;
      showModal(html);
    }
    async function doPasteInsert() {
      const body = window.__pasteRows || [];
      if (!body.length) { toast('没有可导入的数据', true); return; }
      const n = body[0].length;
      const mapping = [];
      for (let i = 0; i < n; i++) { const el = document.getElementById('pm_' + i); mapping.push(el ? el.value : ''); }
      const rows = body.map(r => { const o = {}; r.forEach((v, i) => { if (mapping[i]) o[mapping[i]] = v; }); return o; });
      const cols = mapping.filter(Boolean);
      if (!cols.length) { toast('请至少映射一列', true); return; }
      const useTx = document.getElementById('pasteTx').checked;
      try {
        const d = await api(API + '/api/import', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.assign({ s: current.s, t: current.t, columns: cols, rows, transaction: useTx }, txObj())) });
        if (d.error) throw new Error(d.error);
        toast('成功导入 ' + d.affected + ' 行'); closeModal(); loadData(1);
      } catch (e) { toast('导入失败: ' + e.message, true); }
    }
    function openImport() {
      if (!current) return;
      showModal(`<h3>导入数据 · ${esc(current.s)}.${esc(current.t)}</h3>
        <div class="field"><label>选择 CSV / Excel(xlsx) 文件(首行为列名)</label><input type="file" id="csvFile" accept=".csv,.xlsx,text/csv"></div>
        <div class="acts"><button onclick="closeModal()">取消</button><button class="primary" onclick="parseImportFile()">解析</button></div>`);
    }
    function parseImportFile() {
      const f = document.getElementById('csvFile').files[0];
      if (!f) { toast('请选择 CSV 或 Excel 文件', true); return; }
      if (f.name.toLowerCase().endsWith('.xlsx')) {
        // Excel: 上传到后端解析(纯 Python zip+xml), 返回表头+数据
        const reader = new FileReader();
        reader.onload = async e => {
          try {
            const hdrs = {};
            if (SESSION) hdrs['X-Session'] = SESSION; else if (CONN) hdrs['X-Conn'] = encConn(CONN);
            const r = await fetch(API + '/api/import/xlsx', {
              method: 'POST', headers: hdrs, body: e.target.result
            });
            const d = await r.json();
            if (d.error) throw new Error(d.error);
            if (d.rows.length < 1) { toast('Excel 内容不足(至少需要列名 + 1 行数据)', true); return; }
            window.__impCsv = { header: d.header, rows: d.rows };
            renderImportMap();
          } catch (err) { toast('Excel 解析失败: ' + err.message, true); }
        };
        reader.readAsArrayBuffer(f);
        return;
      }
      const reader = new FileReader();
      reader.onload = e => {
        const rows = parseCsv(String(e.target.result));
        if (rows.length < 2) { toast('CSV 内容不足(至少需要列名 + 1 行数据)', true); return; }
        window.__impCsv = { header: rows[0], rows: rows.slice(1) };
        renderImportMap();
      };
      reader.readAsText(f, 'utf-8');
    }
    function renderImportMap() {
      const { header, rows } = window.__impCsv;
      const cols = currentMeta ? currentMeta.columns : [];
      let html = `<h3>导入数据 · ${esc(current.s)}.${esc(current.t)}</h3>`;
      html += `<div style="color:#86909c;font-size:12px;margin-bottom:10px">CSV: ${rows.length} 行 × ${header.length} 列(已跳过表头)。为每列选择目标字段, 或选"(跳过)":</div>`;
      header.forEach((h, i) => {
        const opts = ['<option value="">(跳过)</option>'].concat(cols.map(c => `<option value="${escAttr(c.name)}" ${h.trim() === c.name ? 'selected' : ''}>${esc(c.name)}</option>`));
        html += `<div class="field"><label>CSV 列「${esc(h.trim() || ('第' + (i + 1) + '列'))}」→ 目标字段</label><select id="impMap_${i}">${opts.join('')}</select></div>`;
      });
      html += `<div class="field"><label>预览(前 3 行)</label><div style="overflow:auto;max-height:150px"><table><tr>${header.map(h => '<th>' + esc(h.trim()) + '</th>').join('')}</tr>`;
      rows.slice(0, 3).forEach(r => { html += '<tr>' + r.map(v => '<td>' + esc(String(v == null ? '' : v).slice(0, 40)) + '</td>').join('') + '</tr>'; });
      html += '</table></div></div>';
      html += `<div class="acts"><button onclick="closeModal()">取消</button><button class="primary" onclick="doImport()">开始导入</button></div>`;
      showModal(html);
    }
    async function doImport() {
      const { header, rows } = window.__impCsv;
      const mapping = header.map((h, i) => { const sel = document.getElementById('impMap_' + i); return sel ? sel.value : ''; });
      const used = mapping.filter(Boolean);
      if (!used.length) { toast('请至少映射一列', true); return; }
      if (!confirm(`确认导入 ${rows.length} 行到 ${current.t} ?`)) return;
      const data = rows.map(r => {
        const rec = {};
        header.forEach((h, i) => { const cn = mapping[i]; if (cn) rec[cn] = r[i] != null ? r[i] : null; });
        return rec;
      });
      try {
        const d = await api(API + '/api/import', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.assign({ s: current.s, t: current.t, columns: used, rows: data, transaction: transactionMode }, txObj())) });
        if (d.error) throw new Error(d.error);
        toast('已导入 ' + d.affected + ' 行'); closeModal(); loadData(1);
      } catch (e) { toast('导入失败: ' + e.message, true); }
    }
    // ---- 多标签表设计器(Navicat 风格): 字段/索引/外键/触发器/SQL预览 集合在一个弹窗 ----
    function dgTab(name, el) {
      document.querySelectorAll('#modal .dtab').forEach(x => x.classList.remove('active'));
      if (el) el.classList.add('active');
      ['dgFields', 'dgIndexes', 'dgFks', 'dgTrigs', 'dgPreview'].forEach(id => {
        const p = document.getElementById(id);
        if (p) p.style.display = (id === 'dg' + name[0].toUpperCase() + name.slice(1)) ? '' : 'none';
      });
    }
    function dgSwitchTable(name) {
      const tg = window.__alterTarget;
      if (tg) openAlter(tg.s, name);
    }
    function dropFk(name) {
      const tg = window.__alterTarget;
      if (!tg) return;
      if (!confirm('确认删除外键 ' + name + '?')) return;
      const q = n => quoteIdent(CONN && CONN.db_type, n);
      toSqlEditor('ALTER TABLE ' + q(tg.s) + '.' + q(tg.t) + ' DROP CONSTRAINT ' + q(name) + ';');
    }
    function renderDgPreview(sc, tb, cols, idxs, rels) {
      const el = document.getElementById('dgPreview');
      if (!el) return;
      const q = n => quoteIdent(CONN && CONN.db_type, n);
      const lines = [];
      lines.push('CREATE TABLE ' + q(sc) + '.' + q(tb) + ' (');
      const trailing = []; // 主键/外键约束行
      cols.forEach((c, i) => {
        let ln = '  ' + q(c.name) + ' ' + (c.type || '');
        if (!c.nullable) ln += ' NOT NULL';
        if (c.default != null && c.default !== '') ln += ' DEFAULT ' + c.default;
        lines.push(ln + ',');
      });
      (idxs || []).forEach(i => {
        if (i.is_pk) { trailing.push('  PRIMARY KEY (' + i.columns.split(',').map(x => q(x.trim())).join(', ') + ')'); return; }
        lines.push('  ' + (i.is_unique ? 'UNIQUE ' : '') + 'INDEX ' + q(i.name || 'idx') + ' (' + i.columns.split(',').map(x => q(x.trim())).join(', ') + '),');
      });
      (rels || []).forEach(r => {
        trailing.push('  CONSTRAINT ' + q(r.name || 'fk') + ' FOREIGN KEY (' + (r.columns || []).map(q).join(', ') + ') REFERENCES ' + q(r.referred_schema || sc) + '.' + q(r.referred_table) + ' (' + (r.referred_columns || []).map(q).join(', ') + ')');
      });
      if (trailing.length) {
        lines[lines.length - 1] = lines[lines.length - 1].replace(/,$/, '');
        trailing.forEach((t, i) => lines.push(t + (i < trailing.length - 1 ? ',' : '')));
      } else {
        lines[lines.length - 1] = lines[lines.length - 1].replace(/,$/, '');
      }
      lines.push(');');
      el.innerHTML = '<pre style="white-space:pre-wrap;font-family:Consolas,monospace;font-size:12px;margin:0;color:#1d2129">' + esc(lines.join('\n')) + '</pre>';
    }
    async function openAlter(s, t) {
      // 多标签设计器: 字段/索引/外键/触发器/SQL预览; 支持右键直达(未打开表也加载)
      const sc = s || (current && current.s);
      const tb = t || (current && current.t);
      if (!sc || !tb) return;
      window.__alterTarget = { s: sc, t: tb }; // 后续字段/索引/外键操作指向该表
      let cols = (currentMeta && current.s === sc && current.t === tb) ? currentMeta.columns : null;
      if (!cols) { try { cols = await api(API + '/api/columns?' + qp({ s: sc, t: tb })); } catch (e) { toast('加载字段失败: ' + e.message, true); return; } }
      let idxs = [];
      try { idxs = await api(API + '/api/indexes?' + qp({ s: sc, t: tb })); } catch (e) { }
      let rels = [];
      try { rels = (await api(API + '/api/relations?' + qp({ s: sc, t: tb }))).filter(r => r.direction === 'out'); } catch (e) { }
      const trigs = (typeof ROUTINES !== 'undefined' ? ROUTINES : []).filter(r => r.type === 'Trigger' && r.schema === sc && r.name === tb);
      // 对象切换下拉: 当前库的表
      const dbTables = [...new Set([tb, ...TABLES.filter(x => x.schema === sc).map(x => x.name)])];
      const q = n => quoteIdent(CONN && CONN.db_type, n);

      // ---- 字段标签 ----
      let fhtml = '<div style="max-height:200px;overflow:auto;border:1px solid #eee;border-radius:6px;">';
      fhtml += cols.map(c => `<div style="display:flex;align-items:center;gap:8px;padding:5px 8px;border-bottom:1px solid #f5f6f8"><span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"><b>${esc(c.name)}</b> <span style="color:#86909c;font-size:12px">${esc(c.type)}${c.nullable ? ' NULL' : ' NOT NULL'}${c.is_pk ? ' · 主键' : ''}</span></span><button class="sm" onclick="modifyColumn('${escAttr(c.name)}')">改</button><button class="sm danger" onclick="dropColumn('${escAttr(c.name)}')">删</button></div>`).join('');
      fhtml += '</div>';
      fhtml += `<h4 style="margin:10px 0 6px;font-size:13px;">添加字段</h4>
        <div class="row2"><div class="field"><label>列名</label><input id="acName" placeholder="如 remark"></div><div class="field"><label>类型</label><input id="acType" placeholder="如 NVARCHAR(50) / INT"></div></div>
        <div class="row2"><div class="field"><label>默认值(可空)</label><input id="acDefault" placeholder="如 0 或 'x' 或 CURRENT_TIMESTAMP"></div><div class="field"><label><input type="checkbox" id="acNullable" checked> 可空</label></div></div>
        <button class="sm primary" onclick="addColumn()">添加字段</button>`;
      // ---- 索引标签 ----
      let ihtml = idxs.length ? '<div style="max-height:140px;overflow:auto;border:1px solid #eee;border-radius:6px;">' + idxs.map(i => `<div style="display:flex;align-items:center;gap:8px;padding:5px 8px;border-bottom:1px solid #f5f6f8"><span style="flex:1"><b>${esc(i.name || '(未命名)')}</b> <span style="color:#86909c;font-size:12px">${esc(i.columns)}${i.is_unique ? ' · 唯一' : ''}${i.is_pk ? ' · 主键' : ''}</span></span><button class="sm danger" onclick="dropIndex('${escAttr(i.name || '')}')">删</button></div>`).join('') + '</div>' : '<div class="empty2">暂无索引</div>';
      ihtml += `<h4 style="margin:10px 0 6px;font-size:13px;">添加索引</h4>
        <div class="row2"><div class="field"><label>索引名</label><input id="aiName" placeholder="如 idx_remark"></div><div class="field"><label>列(逗号分隔)</label><input id="aiCols" placeholder="如 remark, status"></div></div>
        <div class="field"><label><input type="checkbox" id="aiUnique"> 唯一索引</label></div>
        <button class="sm primary" onclick="addIndex()">添加索引</button>`;
      // ---- 外键标签 ----
      let khtml = rels.length ? '<div style="max-height:140px;overflow:auto;border:1px solid #eee;border-radius:6px;">' + rels.map(r => `<div style="display:flex;align-items:center;gap:8px;padding:5px 8px;border-bottom:1px solid #f5f6f8"><span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"><b>${esc(r.name || '(未命名)')}</b> <span style="color:#86909c;font-size:12px">${esc((r.columns || []).join(', '))} → ${esc(r.referred_table)}(${esc((r.referred_columns || []).join(', '))})</span></span><button class="sm danger" onclick="dropFk('${escAttr(r.name || '')}')">删</button></div>`).join('') + '</div>' : '<div class="empty2">暂无外键</div>';
      khtml += `<h4 style="margin:10px 0 6px;font-size:13px;">添加外键(生成 SQL 到工作台)</h4>
        <div class="field"><label>引用表(支持 库.schema.表 / schema.表 / 表)</label><input id="afRefTable" placeholder="如 Customer 或 dbo.Customer"></div>
        <div class="row2"><div class="field"><label>本表列</label><input id="afCol" placeholder="如 CustomerId"></div><div class="field"><label>引用列</label><input id="afRefCol" placeholder="如 Id"></div></div>
        <div class="field"><label>约束名(可空, 自动命名)</label><input id="afName" placeholder="如 FK_${esc(tb)}_CustomerId"></div>
        <button class="sm primary" onclick="addForeignKey()">添加外键</button>`;
      // ---- 触发器标签 ----
      let thtml = trigs.length ? '<div style="max-height:140px;overflow:auto;border:1px solid #eee;border-radius:6px;">' + trigs.map(r => `<div style="display:flex;align-items:center;gap:8px;padding:5px 8px;border-bottom:1px solid #f5f6f8"><span style="flex:1"><b>🔔 ${esc(r.name)}</b></span><button class="sm" onclick="openRoutine('${escAttr(r.schema)}','${escAttr(r.name)}','Trigger')">编辑</button></div>`).join('') + '</div>' : '<div class="empty2">该表暂无触发器</div>';
      thtml += '<div style="margin-top:10px"><button class="sm primary" onclick="newTrigger()">新建触发器(生成模板到 SQL 台)</button></div>';

      const html = `
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;flex-wrap:wrap">
          <h3 style="margin:0;font-size:15px;">表设计器 · ${esc(sc)}.${esc(tb)}</h3>
          <div style="display:flex;align-items:center;gap:6px">
            <label style="font-size:12px;color:#86909c">表:</label>
            <select id="dgTable" onchange="dgSwitchTable(this.value)" style="max-width:220px">
              ${dbTables.map(n => `<option value="${escAttr(n)}" ${n === tb ? 'selected' : ''}>${esc(n)}</option>`).join('')}
            </select>
          </div>
          <div style="margin-left:auto"><button class="primary sm" onclick="closeModal()">完成</button></div>
        </div>
        <div class="designer-tabs">
          <div class="dtab active" onclick="dgTab('fields', this)">字段</div>
          <div class="dtab" onclick="dgTab('indexes', this)">索引</div>
          <div class="dtab" onclick="dgTab('fks', this)">外键</div>
          <div class="dtab" onclick="dgTab('trigs', this)">触发器</div>
          <div class="dtab" onclick="dgTab('preview', this)">SQL 预览</div>
        </div>
        <div id="dgFields" class="dg-panel">${fhtml}</div>
        <div id="dgIndexes" class="dg-panel" style="display:none">${ihtml}</div>
        <div id="dgFks" class="dg-panel" style="display:none">${khtml}</div>
        <div id="dgTrigs" class="dg-panel" style="display:none">${thtml}</div>
        <div id="dgPreview" class="dg-panel" style="display:none"></div>
      `;
      showModal(html);
      renderDgPreview(sc, tb, cols, idxs, rels);
    }
    // ---- 查询构建器(可视化拼 SELECT) ----
    async function openQueryBuilder() {
      if (!CONN) { toast('请先连接数据库', true); return; }
      let tables = TABLES.filter(x => x.type !== 'View' && (!curDb || x.schema === curDb));
      if (!tables.length) tables = TABLES.filter(x => x.type !== 'View');
      if (!tables.length) { toast('无可用表', true); return; }
      showModal(`<h3>查询构建器</h3>
        <div class="field"><label>表</label><select id="qbTable" onchange="qbLoadCols()">${tables.map(t => `<option value="${escAttr(t.schema + '\u0001' + t.name)}">${esc(t.schema ? t.schema + '.' : '')}${esc(t.name)}</option>`).join('')}</select></div>
        <div class="field"><label>选择列(勾选参与查询)</label><div id="qbCols" style="max-height:120px;overflow:auto;border:1px solid #eee;border-radius:6px;padding:6px"></div></div>
        <h4 style="margin:8px 0 4px;font-size:13px;">条件(WHERE, AND 连接)</h4>
        <div id="qbCond"></div>
        <button class="sm" onclick="qbAddCond()">+ 条件</button>
        <div class="field" style="margin-top:8px"><label>排序</label><div class="row2"><select id="qbSortCol"><option value="">无</option></select><select id="qbSortDir"><option value="ASC">升序</option><option value="DESC">降序</option></select></div></div>
        <div class="field"><label>LIMIT</label><input id="qbLimit" type="number" value="100" style="width:120px"></div>
        <p style="color:#86909c;font-size:12px">生成的 SQL 填入工作台, 确认后 Ctrl+Enter 执行。</p>
        <div class="acts"><button onclick="closeModal()">取消</button><button class="primary" onclick="qbBuild()">生成 SQL</button></div>`);
      await qbLoadCols();
    }
    async function qbLoadCols() {
      const sel = document.getElementById('qbTable');
      if (!sel) return;
      const [s, t] = sel.value.split('\u0001');
      try {
        const cols = await api(API + '/api/columns?' + qp({ s, t }));
        document.getElementById('qbCols').innerHTML = cols.map(c => `<label style="display:block;padding:2px 6px;cursor:pointer"><input type="checkbox" value="${escAttr(c.name)}" checked> ${esc(c.name)} <span style="color:#86909c;font-size:11px">${esc(c.type)}</span></label>`).join('');
        const sc = document.getElementById('qbSortCol');
        sc.innerHTML = '<option value="">无</option>' + cols.map(c => `<option value="${escAttr(c.name)}">${esc(c.name)}</option>`).join('');
      } catch (e) { toast('加载列失败: ' + e.message, true); }
    }
    function qbAddCond() {
      const box = document.getElementById('qbCond');
      if (!box) return;
      const cols = [...document.querySelectorAll('#qbCols input')].map(x => x.value);
      if (!cols.length) { toast('请先选择列', true); return; }
      box.insertAdjacentHTML('beforeend', `<div class="row2" style="margin-bottom:4px"><select class="qb-c">${cols.map(c => `<option value="${escAttr(c)}">${esc(c)}</option>`).join('')}</select><select class="qb-op"><option value="=">=</option><option value="!=">!=</option><option value=">">&gt;</option><option value=">=">&gt;=</option><option value="<">&lt;</option><option value="<=">&lt;=</option><option value="LIKE">LIKE</option><option value="IN">IN</option><option value="IS NULL">IS NULL</option></select><input class="qb-v" placeholder="值(IS NULL 可空)"><button class="sm danger" onclick="this.parentNode.remove()">✕</button></div>`);
    }
    function qbBuild() {
      const sel = document.getElementById('qbTable');
      const [s, t] = sel.value.split('\u0001');
      const q = n => quoteIdent(CONN && CONN.db_type, n);
      const checked = [...document.querySelectorAll('#qbCols input:checked')].map(x => x.value);
      const cols = checked.length ? checked.map(q).join(', ') : '*';
      let sql = 'SELECT ' + cols + ' FROM ' + q(s) + '.' + q(t);
      const conds = [...document.querySelectorAll('#qbCond .row2')].map(el => {
        const c = el.querySelector('.qb-c').value;
        const op = el.querySelector('.qb-op').value;
        const v = el.querySelector('.qb-v').value.trim();
        if (op === 'IS NULL') return q(c) + ' IS NULL';
        if (v === '') return null;
        const val = (op === 'LIKE' || op === 'IN') ? v : (isNaN(v) ? "'" + v.replace(/'/g, "''") + "'" : v);
        return q(c) + ' ' + op + ' ' + val;
      }).filter(Boolean);
      if (conds.length) sql += ' WHERE ' + conds.join(' AND ');
      const sortCol = document.getElementById('qbSortCol').value;
      if (sortCol) sql += ' ORDER BY ' + q(sortCol) + ' ' + document.getElementById('qbSortDir').value;
      const lim = parseInt(document.getElementById('qbLimit').value, 10);
      if (lim > 0) sql += ' LIMIT ' + lim;
      toSqlEditor(sql);
    }
    // 生成 DDL 并填入 SQL 工作台(用户确认后执行, 写操作保守)
    function toSqlEditor(sql) {
      closeModal();
      switchView('sql');
      const ta = document.getElementById('sqlInput');
      ta.value = sql;
      if (typeof syncSqlHighlight === 'function') syncSqlHighlight();
      toast('SQL 已生成, 检查后按 Ctrl+Enter 执行');
    }
    function addForeignKey() {
      const sc = current && current.s;
      const tb = current && current.t;
      const col = document.getElementById('afCol').value.trim();
      const ref = document.getElementById('afRefTable').value.trim();
      const refCol = document.getElementById('afRefCol').value.trim();
      const name = document.getElementById('afName').value.trim();
      if (!col || !ref || !refCol) { toast('请填写本表列/引用表/引用列', true); return; }
      const q = n => quoteIdent(CONN && CONN.db_type, n);
      const refParts = ref.split('.').map(x => q(x.trim())).join('.');
      const sql = 'ALTER TABLE ' + q(sc) + '.' + q(tb) + ' ADD CONSTRAINT ' + (name ? q(name) : '') +
        ' FOREIGN KEY (' + q(col) + ') REFERENCES ' + refParts + ' (' + q(refCol) + ');';
      toSqlEditor(sql);
    }
    function newTrigger(s, t) {
      // 新建触发器: 按方言生成 CREATE TRIGGER 模板
      const sc = s || (current && current.s);
      const tb = t || (current && current.t);
      if (!sc || !tb) return;
      const dt = (CONN && CONN.db_type) || 'mysql';
      const name = prompt('触发器名(如 trg_' + tb + '_ins):', 'trg_' + tb + '_ins');
      if (!name) return;
      const q = n => quoteIdent(dt, n);
      let sql;
      if (dt === 'mysql' || dt === 'mariadb') {
        sql = `DELIMITER $$\nCREATE TRIGGER ${q(name)} AFTER INSERT ON ${q(sc)}.${q(tb)}\nFOR EACH ROW\nBEGIN\n    -- 在此编写触发器逻辑\nEND$$\nDELIMITER ;`;
      } else if (dt === 'postgresql') {
        sql = `CREATE FUNCTION ${q(name)}_fn() RETURNS TRIGGER AS $$\nBEGIN\n    RETURN NEW;\nEND;\n$$ LANGUAGE plpgsql;\nCREATE TRIGGER ${q(name)} AFTER INSERT ON ${q(sc)}.${q(tb)}\nFOR EACH ROW EXECUTE FUNCTION ${q(name)}_fn();`;
      } else if (dt === 'mssql') {
        sql = `CREATE TRIGGER ${q(name)} ON ${q(sc)}.${q(tb)}\nAFTER INSERT\nAS\nBEGIN\n    -- 在此编写触发器逻辑\nEND;`;
      } else {
        toast('该数据库类型暂不支持新建触发器', true); return;
      }
      toSqlEditor(sql);
    }
    function addColumn() {
      const name = document.getElementById('acName').value.trim();
      const type = document.getElementById('acType').value.trim();
      const nullable = document.getElementById('acNullable').checked;
      const def = document.getElementById('acDefault').value.trim();
      if (!name || !type) { toast('请填写列名与类型', true); return; }
      alter('add_column', { name, type, nullable, default: def });
    }
    function modifyColumn(name) {
      const tg = alterT();
      let cols = (currentMeta && current.s === tg.s && current.t === tg.t) ? currentMeta.columns : null;
      const col = cols ? cols.find(c => c.name === name) : null;
      const nt = prompt('输入新类型(如 NVARCHAR(100)):', col ? col.type : '');
      if (!nt) return;
      const nullable = confirm('保持可空? 确定=可空, 取消=NOT NULL');
      alter('modify_column', { name, type: nt.trim(), nullable });
    }
    function dropColumn(name) {
      if (!confirm('确认删除字段 ' + name + '? 该操作不可逆!')) return;
      alter('drop_column', { name });
    }
    function addIndex() {
      const name = document.getElementById('aiName').value.trim();
      const cols = document.getElementById('aiCols').value.split(',').map(s => s.trim()).filter(Boolean);
      const unique = document.getElementById('aiUnique').checked;
      if (!cols.length) { toast('请填写索引列', true); return; }
      alter('add_index', { name, columns: cols, unique });
    }
    function dropIndex(name) {
      if (!confirm('确认删除索引 ' + name + '?')) return;
      alter('drop_index', { name });
    }
    function alterT() { return window.__alterTarget || { s: current && current.s, t: current && current.t }; }
    async function alter(action, payload) {
      try {
        const tg = alterT();
        const d = await api(API + '/api/alter', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ s: tg.s, t: tg.t, action, payload }) });
        if (d.error) throw new Error(d.error);
        toast('DDL 已执行: ' + (d.ddl || []).join('; ').slice(0, 90));
        currentMeta = null; const at = activeTab(); if (at) at.meta = null; // DDL 后清旧元数据
        closeModal();
        if (window.__alterTarget) openAlter(window.__alterTarget.s, window.__alterTarget.t); // 右键直达: 保持编辑弹窗
        else await loadStruct();
      } catch (e) { toast('DDL 失败: ' + e.message, true); }
    }
    function renderER(rels) {
      const cur = current.t;
      const outMap = new Map(); rels.filter(r => r.direction === 'out').forEach(r => outMap.set(r.referred_table, r));
      const inMap = new Map(); rels.filter(r => r.direction === 'in').forEach(r => inMap.set(r.referred_table, r));
      const W = 680, nodeW = 150, nodeH = 34, rowH = 58;
      const cx = W / 2;
      const total = Math.max(outMap.size, inMap.size, 1) * rowH + 70;
      let s = `<svg width="${W}" height="${total}" xmlns="http://www.w3.org/2000/svg" style="background:#fafbfc;border-radius:8px">`;
      const curY = 20;
      s += `<rect x="${cx - nodeW / 2}" y="${curY}" width="${nodeW}" height="${nodeH}" rx="6" fill="#E6F1FB" stroke="#185FA5"/><text x="${cx}" y="${curY + 21}" text-anchor="middle" font-size="12" fill="#0C447C">${esc(cur)}</text>`;
      let i = 0;
      outMap.forEach((r, name) => {
        const y = 20 + (i + 1) * rowH, x = cx + 130;
        s += `<rect x="${x}" y="${y}" width="${nodeW}" height="${nodeH}" rx="6" fill="#FAEEDA" stroke="#854F0B"/><text x="${x + nodeW / 2}" y="${y + 21}" text-anchor="middle" font-size="12" fill="#633806">${esc(name)}</text>`;
        s += `<line x1="${cx + nodeW / 2}" y1="${curY + nodeH}" x2="${x}" y2="${y + nodeH / 2}" stroke="#888780" stroke-width="1"/><text x="${(cx + nodeW / 2 + x) / 2}" y="${(curY + nodeH + y + nodeH / 2) / 2 - 5}" text-anchor="middle" font-size="10" fill="#5F5E5A">FK: ${esc((r.columns || []).join(','))}</text>`;
        i++;
      });
      i = 0;
      inMap.forEach((r, name) => {
        const y = 20 + (i + 1) * rowH, x = cx - 130 - nodeW;
        s += `<rect x="${x}" y="${y}" width="${nodeW}" height="${nodeH}" rx="6" fill="#EAF3DE" stroke="#3B6D11"/><text x="${x + nodeW / 2}" y="${y + 21}" text-anchor="middle" font-size="12" fill="#27500A">${esc(name)}</text>`;
        s += `<line x1="${cx - nodeW / 2}" y1="${curY + nodeH}" x2="${x + nodeW}" y2="${y + nodeH / 2}" stroke="#888780" stroke-width="1"/><text x="${(cx - nodeW / 2 + x + nodeW) / 2}" y="${(curY + nodeH + y + nodeH / 2) / 2 - 5}" text-anchor="middle" font-size="10" fill="#5F5E5A">REF: ${esc((r.columns || []).join(','))}</text>`;
        i++;
      });
      s += '</svg>';
      return s;
    }
    async function openER() {
      if (!current) return;
      try {
        const rels = await api(API + '/api/relations?' + qp({ s: current.s, t: current.t }));
        const outCnt = rels.filter(r => r.direction === 'out').length;
        const inCnt = rels.filter(r => r.direction === 'in').length;
        let html = `<h3>ER 图 · ${esc(current.s)}.${esc(current.t)}</h3>`;
        html += `<div style="color:#86909c;font-size:12px;margin-bottom:10px">出方向外键 ${outCnt} 个, 被引用 ${inCnt} 个${rels.length ? ' (右侧=本表外键指向, 左侧=引用本表的表)' : ' —— 该表未定义外键关系'}</div>`;
        if (rels.length) html += '<div style="overflow:auto;max-height:60vh">' + renderER(rels) + '</div>';
        html += '<div class="acts"><button onclick="closeModal()">关闭</button></div>';
        showModal(html);
      } catch (e) { toast('ER 图加载失败: ' + e.message, true); }
    }
    async function openUsers() {
      if (!current) return;
      showModal(`<h3>用户与权限 · ${esc(current.s)}.${esc(current.t)}</h3><div class="empty2" style="padding:20px">加载中...</div>`);
      try {
        const d = await api(API + '/api/users');
        if (!d.supported) {
          showModal(`<h3>用户与权限</h3><div class="empty2" style="padding:20px">当前数据库类型(SQLite)不支持用户与权限管理</div><div class="acts"><button onclick="closeModal()">关闭</button></div>`);
          return;
        }
        let html = `<h3>用户与权限 · ${esc(current.s)}.${esc(current.t)}</h3>`;
        html += `<div style="color:#86909c;font-size:12px;margin-bottom:10px">只读视图 — 登录 / 用户 / 角色 / 权限(不做任何修改)</div>`;
        const sec = (title, rows, cols, empty) => {
          if (!rows || !rows.length) return `<div class="section"><h3>${title} <span style="color:#86909c;font-weight:400;font-size:12px">(0)</span></h3><div class="empty2">${empty || '无数据'}</div></div>`;
          let s = `<div class="section"><h3>${title} <span style="color:#86909c;font-weight:400;font-size:12px">(${rows.length})</span></h3><table><thead><tr>${cols.map(c => `<th>${esc(c[1])}</th>`).join('')}</tr></thead><tbody>`;
          rows.forEach(r => { s += `<tr>${cols.map(c => { const v = r[c[0]]; if (v === true) return '<td>是</td>'; if (v === false) return '<td>否</td>'; return `<td>${esc(v == null ? '-' : v)}</td>`; }).join('')}</tr>`; });
          return s + '</tbody></table></div>';
        };
        html += sec('服务器登录', d.logins, [['name', '登录名'], ['type', '类型'], ['disabled', '已禁用'], ['created', '创建日期'], ['host', '主机'], ['has_pwd', '有密码']], '无登录或账号无查看权限');
        html += sec('数据库用户', d.users, [['name', '用户名'], ['type', '类型'], ['default_schema', '默认架构'], ['login', '关联登录']], '无用户或账号无查看权限');
        html += sec('角色成员', d.roles, [['role', '角色'], ['member', '成员']], '无角色成员关系');
        html += sec('显式权限', d.permissions, [['grantee', '授权对象'], ['permission', '权限'], ['state', '状态'], ['object', '对象'], ['class', '类别'], ['grant', '授权语句']], '无显式权限');
        html += `<div class="acts"><button onclick="closeModal()">关闭</button></div>`;
        showModal(html);
      } catch (e) { toast('加载用户权限失败: ' + e.message, true); showModal(`<h3>用户与权限</h3><div class="empty2" style="padding:20px">加载失败: ${esc(e.message)}</div><div class="acts"><button onclick="closeModal()">关闭</button></div>`); }
    }
    // ---- EXPLAIN 执行计划: 调 /api/explain, 结果并入 SQL 结果 tab(表格/树形渲染) ----
    async function explainSql() {
      const sql = document.getElementById('sqlInput').value.trim();
      if (!sql) { toast('请输入 SQL', true); return; }
      try {
        const payload = { sql };
        if (curDb) payload.database = curDb;
        const d = await api(API + '/api/explain', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        if (d.error) throw new Error(d.error);
        const res = Object.assign({ sql: 'EXPLAIN ' + sql, ok: true }, d);
        addSqlBatch('EXPLAIN', [res]);
        toast('执行计划已生成');
      } catch (e) { toast('解释失败: ' + e.message, true); }
    }
    // ---- 存储过程编辑横幅: 保存重建 / 执行 / 删除 ----
    function closeProcBar() {
      document.getElementById('procBar').style.display = 'none';
      window.__editRoutine = null;
    }
    async function saveRoutine() {
      const r = window.__editRoutine;
      if (!r) return;
      const src = document.getElementById('sqlInput').value;
      if (!src.trim()) { toast('源码不能为空', true); return; }
      if (!confirm(`确认保存(重建) ${r.kind}「${r.name}」?\nMySQL 将 DROP 后重建, PG/MSSQL 直接执行。`)) return;
      try {
        const d = await api(API + '/api/routine/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ s: r.s, name: r.name, kind: r.kind, source: src }) });
        if (d.error) throw new Error(d.error);
        toast('已保存 ' + r.kind + ' ' + r.name);
        if (typeof loadRoutines === 'function') loadRoutines();
      } catch (e) { toast('保存失败: ' + e.message, true); }
    }
    async function dropRoutine() {
      const r = window.__editRoutine;
      if (!r) return;
      if (!confirm(`确认删除 ${r.kind}「${r.name}」? 不可恢复。`)) return;
      try {
        const d = await api(API + '/api/routine/drop', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ s: r.s, name: r.name, kind: r.kind }) });
        if (d.error) throw new Error(d.error);
        toast('已删除 ' + r.name);
        closeProcBar();
        document.getElementById('sqlInput').value = '';
        if (typeof syncSqlHighlight === 'function') syncSqlHighlight();
        if (typeof loadRoutines === 'function') loadRoutines();
      } catch (e) { toast('删除失败: ' + e.message, true); }
    }
    async function execRoutine() {
      const r = window.__editRoutine;
      if (!r) return;
      try {
        const hdrs = {};
        if (SESSION) hdrs['X-Session'] = SESSION; else if (CONN) hdrs['X-Conn'] = encConn(CONN);
        const d = await fetch(API + '/api/routine/params?' + qp({ s: r.s, name: r.name, kind: r.kind }), { headers: hdrs }).then(r2 => r2.json());
        if (d.error) throw new Error(d.error);
        const ps = d.params || [];
        if (!ps.length) return doExecRoutine(r, {});
        let html = `<h3>执行 ${r.kind} · ${esc(r.name)}</h3>`;
        html += `<div style="color:#86909c;font-size:12px;margin-bottom:8px">共 ${ps.length} 个参数(输出参数无需填写)</div>`;
        ps.forEach((p, i) => {
          if (p.mode === 'OUT') return;
          html += `<div class="field"><label>${esc(p.name)} <span style="color:#86909c">(${esc(p.type)}${p.mode && p.mode !== 'IN' ? ' ' + p.mode : ''})</span></label><input id="rp_${i}" placeholder="${p.mode === 'INOUT' ? '输出参数也可填' : '必填'}" ${p.mode === 'INOUT' ? '' : 'value=""'}></div>`;
        });
        html += `<div class="acts"><button onclick="closeModal()">取消</button><button class="primary" onclick="submitExecRoutine()">执行</button></div>`;
        window.__execRoutine = { r, ps };
        showModal(html);
      } catch (e) { toast('参数解析失败: ' + e.message, true); }
    }
    async function submitExecRoutine() {
      const { r, ps } = window.__execRoutine || {};
      if (!r) return;
      const params = {};
      ps.forEach((p, i) => {
        if (p.mode === 'OUT') return;
        const el = document.getElementById('rp_' + i);
        if (el) params[p.name] = el.value;
      });
      closeModal();
      await doExecRoutine(r, params);
    }
    async function doExecRoutine(r, params) {
      try {
        const d = await api(API + '/api/routine/execute', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ s: r.s, name: r.name, kind: r.kind, params }) });
        if (d.error) throw new Error(d.error);
        // 结果并入 SQL 结果 tab 渲染
        const res = Object.assign({ sql: (r.kind === 'Function' ? 'SELECT' : 'CALL') + ' ' + r.name, ok: true }, d);
        addSqlBatch(r.name, [res]);
        if (typeof switchView === 'function') switchView('sql');
        toast('执行完成');
      } catch (e) { toast('执行失败: ' + e.message, true); }
    }
    // ---- 表结构对比/同步: 当前连接(src) vs 已保存连接(dst) ----
    async function openSchemaDiff() {
      if (!CONN) { toast('请先连接数据库', true); return; }
      if (!CONN_LIST.length) { toast('需要先保存至少一个目标连接(连接管理里保存)', true); return; }
      const opts = CONN_LIST.map(c => `<option value="${escAttr(c.name)}">${esc(c.name)} (${esc(c.db_type)})</option>`).join('');
      showModal(`<h3>表结构对比 · ${esc(CONN.db_type || '')}${CONN.database ? ' · ' + esc(CONN.database) : ''}</h3>
        <div class="field"><label>目标连接(对比对象, 差异将补到它)</label><select id="sdDst">${opts}</select></div>
        <div class="field"><label>表名(留空=对比全部表)</label><input id="sdTable" placeholder="如 users, 留空对比所有表"></div>
        <div class="acts"><button onclick="closeModal()">取消</button><button class="primary" onclick="runSchemaDiff()">开始对比</button></div>`);
    }
    async function runSchemaDiff() {
      const dstName = document.getElementById('sdDst').value;
      const table = document.getElementById('sdTable').value.trim();
      if (!dstName) { toast('请选择目标连接', true); return; }
      showModal(`<h3>表结构对比</h3><div class="empty">正在对比...</div>`);
      try {
        const hdrs = { 'Content-Type': 'application/json' };
        if (SESSION) hdrs['X-Session'] = SESSION; else if (CONN) hdrs['X-Conn'] = encConn(CONN);
        const d = await fetch(API + '/api/schema/diff', {
          method: 'POST', headers: hdrs,
          body: JSON.stringify({ dst: { name: dstName }, table: table || null })
        }).then(r => r.json());
        if (d.error) throw new Error(d.error);
        const diffs = d.diffs || [];
        if (!diffs.length) {
          showModal(`<h3>结构对比 · ${esc(dstName)}</h3><div class="empty">✓ 未发现结构差异${table ? `(表 ${esc(table)})` : ''}</div>
            <div class="acts"><button class="primary" onclick="closeModal()">好的</button></div>`);
          return;
        }
        window.__sdDiffs = diffs;
        const badge = t => ({ '缺表': '缺表', '缺列': '缺列', '类型不同': '类型', '可空不同': '可空', '主键不同': '主键' }[t] || t);
        showModal(`<h3>结构差异 ${diffs.length} 项 · 目标 ${esc(dstName)}</h3>
          <div style="max-height:380px;overflow:auto">
          <table class="sd-table"><thead><tr><th style="width:36px"></th><th>类型</th><th>对象</th><th>详情</th></tr></thead><tbody>
          ${diffs.map((x, i) => `<tr><td><input type="checkbox" data-i="${i}" ${x.sql.startsWith('/*') ? 'disabled' : 'checked'}></td>
            <td><span class="sd-badge">${badge(x.type)}</span></td><td>${esc(x.target)}</td><td title="${esc(x.sql)}">${esc(x.detail)}</td></tr>`).join('')}
          </tbody></table></div>
          <div style="color:#86909c;font-size:12px;margin:6px 0">勾选项将执行同步 DDL(悬停详情看 SQL)。「/* 需手动 */」项不可执行。</div>
          <div class="acts"><button onclick="closeModal()">取消</button><button class="primary" onclick="runSchemaSync('${escAttr(dstName)}')">执行所选同步</button></div>`);
      } catch (e) { showModal(`<h3>结构对比</h3><div class="empty">对比失败: ${esc(e.message)}</div><div class="acts"><button class="primary" onclick="closeModal()">关闭</button></div>`); }
    }
    async function runSchemaSync(dstName) {
      const sel = [...document.querySelectorAll('.sd-table input:checked')].map(i => window.__sdDiffs[+i.dataset.i].sql);
      if (!sel.length) { toast('没有可执行的差异', true); return; }
      if (!confirm(`确认在目标连接「${dstName}」执行 ${sel.length} 条 DDL 同步?\n该操作修改目标库结构, 不可自动回滚。`)) return;
      try {
        const d = await api(API + '/api/schema/sync', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dst: { name: dstName }, sqls: sel }) });
        if (d.error) throw new Error(d.error);
        const msg = `执行成功 ${d.executed.length} 条` + (d.failed.length ? `, 失败 ${d.failed.length} 条` : '');
        if (d.failed.length) {
          showModal(`<h3>同步完成(部分失败)</h3><div style="max-height:280px;overflow:auto"><table class="sd-table"><thead><tr><th>SQL</th><th>错误</th></tr></thead><tbody>${d.failed.map(f => `<tr><td>${esc(f.sql)}</td><td style="color:#a32d2d">${esc(f.error)}</td></tr>`).join('')}</tbody></table></div><div class="acts"><button class="primary" onclick="closeModal()">关闭</button></div>`);
        } else {
          toast(msg);
          closeModal();
        }
      } catch (e) { toast('同步失败: ' + e.message, true); }
    }
    // ---- 备份/还原: 备份=整库SQL脚本下载; 还原=执行上传的备份脚本 ----
    async function downloadBackup() {
      if (!CONN) { toast('请先连接数据库', true); return; }
      toast('正在生成备份(大表可能需要一点时间)...');
      try {
        const hdrs = {};
        if (SESSION) hdrs['X-Session'] = SESSION; else if (CONN) hdrs['X-Conn'] = encConn(CONN);
        const r = await fetch(API + '/api/backup', { headers: hdrs });
        if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(d.error || '备份失败'); }
        const blob = await r.blob();
        const cd = r.headers.get('Content-Disposition') || '';
        const m = cd.match(/filename="?([^";]+)"?/);
        const fn = m ? m[1] : 'backup.sql';
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = fn;
        document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(a.href);
        toast('备份已下载: ' + fn);
      } catch (e) { toast('备份失败: ' + e.message, true); }
    }
    function openRestore() {
      if (!CONN) { toast('请先连接数据库', true); return; }
      showModal(`<h3>还原数据 · ${esc(CONN.db_type || '')}</h3>
        <div style="color:#a32d2d;font-size:12px;margin-bottom:8px">⚠ 执行备份 SQL 会<strong>创建/覆盖</strong>当前库中的表与数据, 不可自动回滚。建议先备份当前库。</div>
        <div class="field"><label>选择备份 SQL 文件</label><input type="file" id="restoreFile" accept=".sql,text/plain"></div>
        <div class="acts"><button onclick="closeModal()">取消</button><button class="primary danger" onclick="doRestore()">执行还原</button></div>`);
    }
    async function doRestore() {
      const f = document.getElementById('restoreFile').files[0];
      if (!f) { toast('请选择备份 SQL 文件', true); return; }
      const sql = await f.text();
      if (!confirm(`确认在当前库执行还原? 将执行 ${sql.length} 字符的 SQL 脚本(创建/覆盖表与数据)。`)) return;
      try {
        const d = await api(API + '/api/restore', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sql }) });
        if (d.error) throw new Error(d.error);
        const ok = (d.executed || []).length, fail = (d.failed || []).length;
        if (fail) {
          showModal(`<h3>还原完成(成功 ${ok} 条, 失败 ${fail} 条)</h3><div style="max-height:280px;overflow:auto"><table class="sd-table"><thead><tr><th>SQL</th><th>错误</th></tr></thead><tbody>${d.failed.map(x => `<tr><td>${esc(x.sql)}</td><td style="color:#a32d2d">${esc(x.error)}</td></tr>`).join('')}</tbody></table></div><div class="acts"><button class="primary" onclick="closeModal()">关闭</button></div>`);
        } else {
          toast('还原成功 ' + ok + ' 条语句');
          closeModal();
          if (typeof loadData === 'function' && current) loadData(1);
        }
      } catch (e) { toast('还原失败: ' + e.message, true); }
    }
    async function openSync() {
      if (!current) return;
      let conns = [];
      try { conns = await fetch(API + '/api/connections').then(r => r.json()); } catch (e) { }
      let html = `<h3>同步表数据 · ${esc(current.s)}.${esc(current.t)}</h3>`;
      html += `<div style="color:#86909c;font-size:12px;margin-bottom:10px">把当前连接中该表的数据复制到目标连接的<b>同名表</b>(按同名列匹配, 主键冲突可能导致失败)</div>`;
      if (!conns.length) {
        html += '<div class="empty2">请先在「我的连接」中保存目标连接</div>';
      } else {
        html += `<div class="field"><label>目标连接</label><select id="syncDst">${conns.map(c => `<option value="${escAttr(c.name)}">${esc(c.name)} (${esc(c.db_type)} · ${esc(c.server || '')})</option>`).join('')}</select></div>`;
        html += `<div class="field"><label>模式</label><select id="syncMode"><option value="append">追加(不清空目标)</option><option value="replace">清空目标后复制</option></select></div>`;
        html += `<div class="acts"><button onclick="closeModal()">取消</button><button class="primary" onclick="doSync()">开始同步</button></div>`;
      }
      showModal(html);
    }
    async function doSync() {
      const dstName = document.getElementById('syncDst').value;
      const mode = document.getElementById('syncMode').value;
      if (!dstName) { toast('请选择目标连接', true); return; }
      if (!confirm(`确认将 ${current.s}.${current.t} 同步到「${dstName}」(${mode === 'replace' ? '清空目标后复制' : '追加'})?`)) return;
      const src = (CONN && CONN.name) ? { name: CONN.name } : CONN;
      try {
        const d = await api(API + '/api/sync', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ src, dst: { name: dstName }, schema: current.s, table: current.t, mode }) });
        if (d.error) throw new Error(d.error);
        toast('同步完成: 复制 ' + d.synced + ' 行'); closeModal();
      } catch (e) { toast('同步失败: ' + e.message, true); }
    }
    async function exportSchemaDoc() {
      if (!current) return;
      try {
        const hdrs = {};
        if (SESSION) hdrs['X-Session'] = SESSION; else if (CONN) hdrs['X-Conn'] = encConn(CONN);
        const r = await fetch(API + '/api/export/schema', { headers: hdrs });
        if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(d.error || '导出失败'); }
        const blob = await r.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'data_dictionary.md';
        document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(a.href);
        toast('已导出数据字典');
      } catch (e) { toast('导出失败: ' + e.message, true); }
    }
    // ---- SQL 写模式: 默认关; 开启后允许 DDL/DML, 执行前危险确认, 后端整批事务(失败回滚) ----
    let writeMode = false;
    function toggleWriteMode() { store.set('writeMode', !writeMode); }
    store.watch('writeMode', v => {
      writeMode = v;
      const btn = document.getElementById('writeBtn');
      const ta = document.getElementById('sqlInput');
      if (btn) {
        btn.textContent = '写模式: ' + (v ? '开' : '关');
        btn.style.background = v ? '#a32d2d' : '#fcebeb';
        btn.style.color = v ? '#fff' : '#a32d2d';
        btn.style.borderColor = v ? '#a32d2d' : '#f7c1c1';
      }
      if (ta) {
        ta.style.borderColor = v ? '#e24b4a' : '';
        ta.placeholder = v
          ? '⚠ 写模式: 可执行 INSERT/UPDATE/DELETE/DDL, 整批事务执行失败回滚; 请谨慎操作'
          : '输入只读 SQL, 如: SELECT TOP 100 * FROM dbo.PoJc WHERE 1=1\n仅支持 SELECT / SHOW / EXPLAIN / DESC, Ctrl+Enter 执行';
      }
    });
    async function runSql() {
      const sql = document.getElementById('sqlInput').value.trim();
      if (!sql) { toast('请输入 SQL', true); return; }
      try {
        const payload = { sql };
        if (curDb) payload.database = curDb;   // 连接内选库: 指定本次 SQL 的目标库
        if (writeMode) {
          payload.write = true;
          if (!confirm('写模式执行: 将真实修改数据库且不可撤销。\n建议先备份或确认 WHERE 条件准确。\n确认继续执行吗？')) return;
        }
        const d = await api(API + '/api/sql', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        if (d.error) throw new Error(d.error);
        saveSqlHist(sql);
        if (d.results && d.results.length) addSqlBatch(sql, d.results);
        else addSqlBatch(sql, [d]);
      } catch (e) { toast('SQL 执行失败: ' + e.message, true); }
    }
    function exportSqlResult() {
      const d = window.__sqlResult;
      if (!d || !d.columns || !d.columns.length) { toast('当前没有可导出的查询结果', true); return; }
      let csv = '\ufeff' + d.columns.map(c => '"' + String(c.name).replace(/"/g, '""') + '"').join(',') + '\r\n';
      d.rows.forEach(r => {
        csv += d.columns.map(c => { const v = r[c.name]; if (v == null) return ''; return '"' + String(v).replace(/"/g, '""') + '"'; }).join(',') + '\r\n';
      });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
      a.download = 'query_result.csv';
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(a.href);
      toast('已导出查询结果 CSV');
    }
    async function exportColsRows(cols, rows, filename) {
      // 通用导出: 任意 columns+rows 调后端生成 xlsx 下载(数据网格选中行/查询结果共用)
      if (!cols || !cols.length || !rows) { toast('没有可导出的数据', true); return; }
      toast(`正在导出 ${rows.length} 行 ...`);
      try {
        const hdrs = { 'Content-Type': 'application/json' };
        if (SESSION) hdrs['X-Session'] = SESSION; else if (CONN) hdrs['X-Conn'] = encConn(CONN);
        const r = await fetch(API + '/api/export/sql', {
          method: 'POST', headers: hdrs,
          body: JSON.stringify({ columns: cols, rows })
        });
        if (!r.ok) { const er = await r.json().catch(() => ({})); throw new Error(er.error || '导出失败'); }
        const blob = await r.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = filename || 'export.xlsx';
        document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(a.href);
        toast('已导出 ' + rows.length + ' 行');
      } catch (e) { toast('导出失败: ' + e.message, true); }
    }
    async function exportSqlResultXlsx() {
      const d = window.__sqlResult;
      if (!d || !d.columns || !d.columns.length) { toast('当前没有可导出的查询结果', true); return; }
      try {
        const hdrs = { 'Content-Type': 'application/json' };
        if (SESSION) hdrs['X-Session'] = SESSION; else if (CONN) hdrs['X-Conn'] = encConn(CONN);
        const r = await fetch(API + '/api/export/sql', {
          method: 'POST', headers: hdrs,
          body: JSON.stringify({ columns: d.columns, rows: d.rows })
        });
        if (!r.ok) { const er = await r.json().catch(() => ({})); throw new Error(er.error || '导出失败'); }
        const blob = await r.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'query_result.xlsx';
        document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(a.href);
        toast('已导出查询结果 Excel');
      } catch (e) { toast('导出失败: ' + e.message, true); }
    }
    // ------------------------------
    // 多查询结果 tab: 每次执行独立成 tab, 可切换/关闭; 列宽自适应内容与标题
    // ------------------------------
    const CELL_TRUNC = 300;   // 单元格字符截断阈值: 超 300 字符截断(防页面卡死), 双击截断单元格可看全文
    let SQL_TABS = [], SQL_TAB_SEQ = 0, SQL_ACTIVE = null;
    function showCellDetail(title, full) {
      // 双击被截断的单元格 -> 弹窗查看完整内容
      window.__cellDetail = full || '';
      const html = `<h3>${esc(title)} <span style="color:#86909c;font-weight:400;font-size:12px">(完整内容 ${(full || '').length} 字符)</span></h3>
        <pre style="max-height:60vh;overflow:auto;white-space:pre-wrap;word-break:break-all;background:#f7f8fa;border:1px solid #e5e6eb;padding:10px;border-radius:6px;margin:8px 0">${esc(full || '')}</pre>
        <div class="acts"><button onclick="copyCellDetail()">复制全文</button><button onclick="closeModal()">关闭</button></div>`;
      showModal(html);
    }
    function copyCellDetail() {
      const t = window.__cellDetail || '';
      const ta = document.createElement('textarea');
      ta.value = t; document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); toast('已复制 ' + t.length + ' 字符'); } catch (e) { toast('复制失败', true); }
      ta.remove();
    }
    function cellDbl(rowIdx, colName, trunc) {
      // 数据网格: 截断单元格双击看全文, 普通单元格双击编辑
      if (trunc) {
        const meta = currentMeta && currentMeta.rows && currentMeta.rows[rowIdx];
        showCellDetail(colName, meta ? String(meta[colName]) : '(无法获取完整内容)');
      } else {
        openCellEdit(rowIdx, colName);
      }
    }
    function sqlCellDbl(rowIdx, colName) {
      // SQL 结果: 截断单元格双击看全文
      const tab = SQL_TABS.find(t => t.id === SQL_ACTIVE);
      const row = tab && tab.result && tab.result.rows && tab.result.rows[rowIdx];
      showCellDetail(colName, row ? String(row[colName]) : '(无法获取完整内容)');
    }
    function estW(s) { let w = 0; for (const ch of String(s)) w += ch.charCodeAt(0) > 255 ? 2 : 1; return w; }
    // ---- 列宽跨会话记忆(localStorage, 按"表"维度): 拖拽后自动保存, 重开表/刷新自动应用, 双击重置清除 ----
    function colWKeyFor(schema, table) {
      // 表标识: db类型|服务器|库(连接内选库优先)|schema|表名 —— 同一张表在不同库/服务器宽度互不干扰
      const db = curDb || (CONN && CONN.database) || '';
      if (!table) return '';
      return 'dbm_colw|' + ((CONN && CONN.db_type) || '') + '|' + ((CONN && CONN.server) || '') + '|' + db + '|' + (schema || '') + '|' + table;
    }
    function colWKey() {
      return colWKeyFor((current && current.s) || '', (current && current.t) || '');
    }
    function getSavedColWidths(key) {
      if (!key) return null;
      try { return JSON.parse(localStorage.getItem(key) || 'null'); } catch (e) { return null; }
    }
    function saveColWidth(key, colName, w) {
      if (!key || !colName || !w) return;
      let saved = getSavedColWidths(key) || {};
      saved[colName] = w;
      try { localStorage.setItem(key, JSON.stringify(saved)); } catch (e) { /* 存储满/隐私模式忽略 */ }
    }
    function clearColWidth(key, colName) {
      if (!key) return;
      const saved = getSavedColWidths(key) || {};
      delete saved[colName];
      try {
        if (Object.keys(saved).length) localStorage.setItem(key, JSON.stringify(saved));
        else localStorage.removeItem(key);
      } catch (e) {}
    }
    function applyColWidths(table) {
      // 渲染后应用记忆列宽: 有记忆的列覆盖自动计算值, 未记忆的列保持自适应
      if (!table) return;
      const key = table.dataset.colkey;
      if (!key) return;
      const saved = getSavedColWidths(key);
      if (!saved) return;
      const cg = table.querySelector('colgroup');
      if (!cg) return;
      const ths = [...table.querySelectorAll('thead th')];
      [...cg.children].forEach((col, i) => {
        const th = ths[i];
        if (!th || !th.dataset.c) return;
        const w = saved[th.dataset.c];
        if (w) col.style.width = w + 'px';
      });
    }
    async function applySqlResultColWidths(table, sqlText) {
      // SQL 结果列宽对齐来源表字段: 解析 FROM/JOIN 的表, 结果列名匹配到该表字段时,
      // 套用该表在数据浏览里保存的记忆列宽(未匹配的列保持自适应)
      if (!table) return;
      const ths = [...table.querySelectorAll('thead th')];
      const cg = table.querySelector('colgroup');
      if (!ths.length || !cg) return;
      const aliases = parseSqlAliases(sqlText || '');
      const tables = [...new Set(Object.values(aliases))].filter(Boolean);  // 去重的表引用
      if (!tables.length) return;
      const resolved = {};   // 表引用 -> {cols, colKey} 惰性缓存
      async function resolveTable(ref) {
        if (resolved[ref] !== undefined) return resolved[ref];
        resolved[ref] = null;  // 防重复并发
        let schema = '', tname = '';
        const parts = ref.split('.');
        if (parts.length >= 3) { schema = parts[parts.length - 2]; tname = parts[parts.length - 1]; }
        else if (parts.length === 2) { schema = parts[0]; tname = parts[1]; }
        else { tname = parts[0]; }
        if (!tname) return null;
        if (!schema) {
          const hits = (TABLES || []).filter(t => (t.name || '').toLowerCase() === tname.toLowerCase());
          if (hits.length === 1) schema = hits[0].schema || '';
          else if (hits.length > 1) schema = (hits.find(t => t.schema) || hits[0]).schema || '';
        }
        const cols = await getTableColsCached(schema, tname);
        if (!cols || !cols.length) return null;
        resolved[ref] = { cols, colKey: colWKeyFor(schema, tname) };
        return resolved[ref];
      }
      for (let ci = 0; ci < ths.length; ci++) {
        if (window.__colDragging) return;  // 用户正在拖拽: 放弃本次异步应用, 避免覆盖正在拖的宽度
        const th = ths[ci];
        const colName = (th.dataset.c || '').trim();
        if (!colName) continue;
        let ref = null;
        if (colName.includes('.')) {
          // 带前缀: u.id / users.id / client.users.id —— 前缀别名或表名
          const pre = colName.slice(0, colName.lastIndexOf('.'));
          ref = aliases[pre.toLowerCase()] || pre;
        } else {
          // 裸列名: 按 FROM 表顺序找第一个含该字段的表
          for (const t of tables) {
            const r = await resolveTable(t);
            if (r && r.cols.some(c => (c.name || '') === colName)) { ref = t; break; }
          }
        }
        if (!ref) continue;
        const r = await resolveTable(ref);
        if (!r || !r.cols.some(c => (c.name || '') === colName)) continue;
        const saved = getSavedColWidths(r.colKey);
        if (!saved) continue;
        const w = saved[colName];
        // 异步期间表格可能已被重渲染(colgroup 重建), 旧 col 不在文档中则跳过
        if (w && cg.children[ci] && document.contains(cg.children[ci])) cg.children[ci].style.width = w + 'px';
      }
    }
    // ---- 双击表头: 手动输入列宽(拖动不可用的兜底, 一定可靠) ----
    function openColWidthInput(th) {
      const table = th.closest('table');
      const idx = [...th.parentElement.children].indexOf(th);
      const cg = table.querySelector('colgroup');
      if (!cg) return;
      const col = cg.children[idx] || null;
      if (!col) return;
      window.__colwTarget = { table, th, col, key: table.dataset.colkey || '' };
      const cur = parseInt(col.style.width, 10) || 120;
      const colName = th.dataset.c || '';
      showModal(`<h3>设置列宽 · ${esc(colName)}</h3>
        <div class="field"><label>列宽（像素，40 ~ 2000）</label><input id="colwVal" type="number" min="40" max="2000" step="1" value="${cur}" style="width:140px"></div>
        <div class="acts"><button onclick="closeModal()">取消</button><button onclick="resetColWidthInput()">恢复自动</button><button class="primary" onclick="applyColWidthInput()">确定</button></div>`);
      const inp = document.getElementById('colwVal');
      if (inp) { inp.focus(); inp.select(); }
    }
    function applyColWidthInput() {
      const t = window.__colwTarget;
      const inp = document.getElementById('colwVal');
      window.__colwTarget = null;
      closeModal();
      if (!t || !inp || !t.col) return;
      const w = Math.max(40, Math.min(2000, parseInt(inp.value, 10) || 0));
      t.col.style.width = w + 'px';
      // 仅数据浏览(有 colkey)保存记忆; SQL 结果列宽是纯临时调整, 不保存也不写主表
      if (t.key && t.th.dataset.c) saveColWidth(t.key, t.th.dataset.c, w);
    }
    function resetColWidthInput() {
      const t = window.__colwTarget;
      window.__colwTarget = null;
      closeModal();
      if (!t || !t.table) return;
      if (t.key && t.th.dataset.c) clearColWidth(t.key, t.th.dataset.c);
      const box = t.table.closest('.gridwrap') || t.table.parentElement;
      if (!box) return;
      fitTableWidths(box, box.id === 'grid' ? '.th-type' : null);
      if (box.id === 'grid') applyColWidths(t.table);            // 数据浏览: 恢复其他列的记忆
      else applySqlResultColWidths(t.table, box.dataset.sql || '');  // SQL 结果: 回到来源表默认宽度
    }
    function enableColResize() {
      // 表头列宽拖拽(事件委托, 全局一次绑定)
      // 方案要点(参考 segmentfault.com/a/1190000013243185):
      //  ① 用 JS 统一控制"列右缘8px内"的光标(col-resize)与可拖状态, 不依赖纯 CSS hover;
      //  ② 拖拽期间 document.onselectstart/ondragstart 返回 false, 防止文本选择与浏览器
      //     原生拖拽接管 mousemove(原生拖拽会让 mousemove 监听失效——这是"拖不动"的根因之一);
      //  ③ 右缘/把手按下立即拖, 表头其他位置按住横向移动>5px 也拖(增强); 点击仍排序
      if (window.__colResizeBound) return;
      window.__colResizeBound = true;
      // 拖宽结束后拦截紧随的 click, 防止触发表头排序
      document.addEventListener('click', e => {
        if (window.__colDragJustEnded) {
          e.preventDefault();
          e.stopPropagation();
          window.__colDragJustEnded = false;
        }
      }, true);
      // ① hover 判定: 鼠标位于可拖表格表头的列右缘 8px 内 -> col-resize 光标 + 标记可拖
      document.addEventListener('mousemove', e => {
        if (window.__colDragging) return;                 // 拖拽中不处理 hover
        const th = e.target.closest ? e.target.closest('th') : null;
        const table = th && th.closest('table');
        const active = table && table.querySelector('.th-resize');
        if (!active) {                                     // 不在可拖表头: 清理光标
          if (window.__hoverTh) { window.__hoverTh.style.cursor = ''; window.__hoverTh = null; }
          document.body.style.cursor = '';
          window.__nearRight = false;
          return;
        }
        if (window.__hoverTh && window.__hoverTh !== th) window.__hoverTh.style.cursor = '';
        window.__hoverTh = th;
        const near = (th.getBoundingClientRect().right - e.clientX) < 8;
        window.__nearRight = near;
        th.style.cursor = near ? 'col-resize' : '';
      });
      // ② mousedown(绑定到表格容器, 比 document 全局委托更就近): 右缘/把手立即拖, 任意位置 5px 阈值拖
      ['grid', 'sqlResult'].forEach(id => {
        const ct = document.getElementById(id);
        if (!ct) return;
        ct.addEventListener('mousedown', e => {
        if (e.button !== 0) return;                        // 仅左键
        const th = e.target.closest ? e.target.closest('th') : null;
        if (!th) return;
        const table = th.closest('table');
        if (!table || !table.querySelector('.th-resize')) return;  // 仅数据表格
        const handle = e.target.closest('.th-resize');
        const nearRight = window.__nearRight && window.__hoverTh === th;
        const idx = [...th.parentElement.children].indexOf(th);
        let cg = table.querySelector('colgroup');
        if (!cg) {  // 健壮性: 意外缺失 colgroup 时补建, 否则 fixed 布局下列宽无效
          cg = document.createElement('colgroup');
          table.querySelectorAll('thead th').forEach(t2 => {
            const col = document.createElement('col');
            col.style.width = (t2.style.width || '') || (t2.offsetWidth ? t2.offsetWidth + 'px' : '120px');
            cg.appendChild(col);
          });
          table.insertBefore(cg, table.firstChild);
        }
        const col = cg.children[idx] || null;
        if (!col) return;
        const startX = e.clientX;
        const startW = parseFloat(col.style.width) || (th.offsetWidth || 120);
        let dragging = false;
        if (handle || nearRight) {                         // 右缘/把手: 按下即进入拖拽
          e.preventDefault();
          e.stopPropagation();
          dragging = true;
          window.__colDragging = true;
          th.classList.add('col-dragging');
          if (handle) handle.classList.add('active');
        }
        // 文章方案: 拖拽期间禁用文本选择与浏览器原生拖拽(防 mousemove 被接管)
        document.onselectstart = () => false;
        document.ondragstart = () => false;
        const onMove = ev => {
          const dx = ev.clientX - startX;
          if (!dragging && Math.abs(dx) < 5) return;       // 非右缘按下: 5px 阈值区分点击/拖动
          if (!dragging) {
            dragging = true;
            window.__colDragging = true;
            th.classList.add('col-dragging');
          }
          col.style.width = Math.max(40, Math.round(startW + dx)) + 'px';
        };
        const onUp = () => {
          document.removeEventListener('mousemove', onMove);
          document.removeEventListener('mouseup', onUp);
          document.body.style.cursor = '';
          document.onselectstart = null;
          document.ondragstart = null;
          if (handle) handle.classList.remove('active');
          if (dragging) {
            window.__colDragging = false;
            th.classList.remove('col-dragging');
            window.__colDragJustEnded = true;             // 阻止随后的 click(排序)
            const key = table.dataset.colkey;
            const w = parseFloat(col.style.width);
            if (w && key && th.dataset.c) saveColWidth(key, th.dataset.c, w);  // 仅数据浏览保存; SQL 结果纯临时
          }
        };
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
        });
      });
      // 双击表头: 把手=恢复自动宽度; 其他位置=弹窗手动输入列宽
      document.addEventListener('dblclick', e => {
        const th = e.target.closest ? e.target.closest('th') : null;
        if (!th) return;
        const table = th.closest('table');
        if (!table || !table.querySelector('.th-resize')) return;  // 仅数据表格
        e.stopPropagation();
        if (e.target.closest('.th-resize')) {
          // 双击把手: 清除该列记忆并恢复自动宽度(其他列记忆保留)
          const key = table.dataset.colkey;
          if (key && th.dataset.c) clearColWidth(key, th.dataset.c);
          const box = table.closest('.gridwrap') || table.parentElement;
          if (box) {
            fitTableWidths(box, box.id === 'grid' ? '.th-type' : null);
            if (box.id === 'grid') applyColWidths(table);  // 数据浏览: 恢复其他列的记忆
            else applySqlResultColWidths(table, box.dataset.sql || '');  // SQL 结果: 回到来源表默认
          }
        } else {
          openColWidthInput(th);   // 双击表头: 手动输入列宽
        }
      });
    }
    function fitTableWidths(box, ignoreSub) {
      // 列宽动态变长(width): 取 标题宽 与 内容宽(按4行内显示完折算: 每行至少容纳1/4内容) 的较大者,
      // 保证长字段(如UUID/备注)通过加宽列在4行内显示完整, 不做总宽压缩(表格超宽时可横向滚动)
      const table = box.querySelector('table');
      if (!table) return;
      const oldCg = table.querySelector('colgroup');
      if (oldCg) oldCg.remove();  // 已有 colgroup 先移除, 防止重复插入
      const ths = [...table.querySelectorAll('thead th')];
      if (!ths.length) return;
      const rows = [...table.querySelectorAll('tbody tr')];
      // 注意: 必须用 createElement 构建 colgroup —— createContextualFragment('<colgroup>') 在
      // 真实浏览器(body 上下文)解析时会被 HTML 解析器剥离(表格专属元素), 导致 colgroup 为空/不插入,
      // 进而列宽设置全部失效(拖动/双击输入/记忆应用都不生效)。这是真实浏览器与 jsdom 的差异。
      const cgEl = document.createElement('colgroup');
      ths.forEach((th, i) => {
        const colEl = document.createElement('col');
        const isOp = rows.some(r => r.children[i] && r.children[i].querySelector('button'));
        if (isOp) { colEl.style.width = '110px'; cgEl.appendChild(colEl); return; }
        let titleW = 0;
        [...th.childNodes].forEach(node => {
          if (node.nodeType === 3) titleW += estW(node.textContent);
          else if (node.nodeType === 1 && !(ignoreSub && node.matches(ignoreSub))) titleW += estW(node.textContent);
        });
        let contentW = 0;
        rows.forEach(r => { const td = r.children[i]; if (td && !td.querySelector('button')) contentW = Math.max(contentW, estW(td.textContent)); });
        // 列宽 = 标题宽 与 内容宽 的较大者; 内容短(<32字符)单行完整显示,
        // 长内容按最多 32 字符宽截断显示(配合300字符截断+双击看全文), 保持表格紧凑
        const need = Math.max(titleW, Math.min(contentW, 32), 4);
        colEl.style.width = Math.max(60, Math.min(360, need * 7.5 + 14)) + 'px';
        cgEl.appendChild(colEl);
      });
      table.insertBefore(cgEl, table.firstChild);
    }
    function buildSqlResultHtml(d, rows) {
      if (!d.columns || !d.columns.length) {
        return '<div class="empty">执行成功' + (d.affected != null ? ' (影响 ' + d.affected + ' 行)' : '') + '</div>';
      }
      const srcRows = rows || d.rows || [];
      let h = '<table><thead><tr>';
      d.columns.forEach(c => { h += `<th data-c="${escAttr(c.name)}">${esc(c.name)}<span class="th-resize" title="拖动调整列宽，双击恢复自动" onclick="event.stopPropagation()"></span></th>`; });
      h += '</tr></thead><tbody>';
      srcRows.forEach((r, ri) => {
        const origIdx = (r && r._ri != null) ? r._ri : ri;   // 过滤后保留原始行索引(双击看全文取数不错位)
        h += '<tr>';
        d.columns.forEach(c => {
          let v = r[c.name];
          if (v === null) h += '<td class="null">NULL</td>';
          else {
            const s = String(v);
            const trunc = s.length > CELL_TRUNC;
            const disp = trunc ? s.slice(0, CELL_TRUNC) + '…' : s;
            const cls = (trunc ? 'trunc' : '') + cellTypeClass(c);
            h += `<td class="${cls.trim()}"${trunc ? ' title="内容过长, 双击查看完整内容"' : ''} ondblclick="sqlCellDbl(${origIdx},'${escAttr(c.name)}')"><div class="cell">${esc(disp)}</div></td>`;
          }
        });
        h += '</tr>';
      });
      h += '</tbody></table>';
      return h;
    }
    function sqlHintFor(r) {
      return (r.columns && r.columns.length)
        ? ('共 ' + r.total + ' 行' + (r.truncated ? ' (已截断, 仅显示前 ' + r.rows.length + ' 行)' : '')) : '';
    }
    function shortSqlLabel(s) {
      const oneLine = String(s || '').replace(/\s+/g, ' ').trim();
      return oneLine.length > 40 ? oneLine.slice(0, 40) + '…' : oneLine;
    }
    let LAST_BATCH = null;   // {sqls, tabIds} 同批重复执行时覆盖, 避免堆 tab
    function addSqlBatch(sql, results) {
      const sqls = (results || []).map(r => r.sql || '');
      // 与上次批量完全一致 -> 覆盖对应 tab
      if (LAST_BATCH && LAST_BATCH.sqls.length === sqls.length
          && LAST_BATCH.sqls.every((s, i) => s === sqls[i])) {
        results.forEach((r, i) => {
          const tab = SQL_TABS.find(t => t.id === LAST_BATCH.tabIds[i]);
          if (tab) { tab.sql = sqls[i]; tab.result = r; tab.html = buildSqlResultHtml(r); tab.hint = sqlHintFor(r); }
        });
        SQL_ACTIVE = LAST_BATCH.tabIds[0];
        renderSqlTabs();
        return;
      }
      // 新建: 每条语句一个 tab
      const tabIds = [];
      results.forEach((r, i) => {
        SQL_TAB_SEQ++;
        const tab = { id: SQL_TAB_SEQ, sql: sqls[i] || sql, result: r,
                      html: buildSqlResultHtml(r), hint: sqlHintFor(r),
                      label: shortSqlLabel(sqls[i] || sql) };
        SQL_TABS.push(tab);
        tabIds.push(tab.id);
      });
      LAST_BATCH = { sqls, tabIds };
      SQL_ACTIVE = tabIds[0];
      renderSqlTabs();
    }
    function renderSqlFiltered() {
      // 结果集内过滤: 按关键词过滤当前激活 tab 的结果行(不重新查库); 空关键词=原结果
      const box = document.getElementById('sqlResult');
      const tab = SQL_TABS.find(t => t.id === SQL_ACTIVE);
      if (!tab) { box.innerHTML = ''; return; }
      const d = tab.result;
      const info = document.getElementById('sqlFilterInfo');
      if (!d || !d.columns || !d.columns.length) { box.innerHTML = tab.html; if (info) info.textContent = ''; return; }
      const kw = document.getElementById('sqlFilter').value.trim().toLowerCase();
      if (!kw) {
        box.innerHTML = tab.html;
        if (info) info.textContent = '';
      } else {
        const hits = [];
        (d.rows || []).forEach((r, i) => {
          const hit = d.columns.some(c => {
            const v = r[c.name];
            return v != null && String(v).toLowerCase().includes(kw);
          });
          if (hit) hits.push(Object.assign({ _ri: i }, r));   // _ri 保留原始行索引
        });
        box.innerHTML = buildSqlResultHtml(d, hits);
        if (info) info.textContent = `过滤: ${hits.length} / 共 ${d.rows.length} 行`;
      }
      fitTableWidths(box, null);
    }
    function renderSqlTabs() {
      const bar = document.getElementById('sqlTabs');
      const box = document.getElementById('sqlResult');
      const hint = document.getElementById('sqlHint');
      const fbar = document.getElementById('sqlFilterBar');
      if (!SQL_TABS.length) { bar.style.display = 'none'; box.innerHTML = ''; hint.textContent = ''; if (fbar) fbar.style.display = 'none'; return; }
      bar.style.display = 'flex';
      bar.innerHTML = SQL_TABS.map(t => `<div class="sql-tab ${t.id === SQL_ACTIVE ? 'active' : ''}" onclick="switchSqlTab(${t.id})" title="${esc(t.sql)}">Q${t.id}: ${esc(t.label)}<span class="x" onclick="event.stopPropagation();closeSqlTab(${t.id})">×</span></div>`).join('');
      const tab = SQL_TABS.find(t => t.id === SQL_ACTIVE);
      if (tab) {
        if (fbar) fbar.style.display = 'flex';
        box.dataset.sql = tab.sql || '';   // 供 SQL 结果列宽保存到来源表记忆
        hint.textContent = tab.hint || '';
        window.__sqlResult = tab.result;   // 导出跟随激活 tab
        renderSqlFiltered();
        applySqlResultColWidths(box.querySelector('table'), tab.sql);  // 列宽对齐来源表字段记忆
      }
    }
    function switchSqlTab(id) { SQL_ACTIVE = id; renderSqlTabs(); }
    function closeSqlTab(id) {
      SQL_TABS = SQL_TABS.filter(t => t.id !== id);
      if (SQL_ACTIVE === id) SQL_ACTIVE = SQL_TABS.length ? SQL_TABS[SQL_TABS.length - 1].id : null;
      renderSqlTabs();
    }
    function renderSqlResult(d) { addSqlBatch('', d.results || [d]); }   // 兼容旧调用
    // ---- SQL 格式化: 不引库的实用美化(关键字换行/逗号列表缩进/括号深度/字符串保护) ----
    function formatSql(sql) {
      if (!sql) return sql;
      const strs = [];
      const s0 = String(sql).replace(/'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"/g,
        m => { strs.push(m); return '\x01S' + (strs.length - 1) + 'S\x01'; });
      let s = s0.replace(/\s+/g, ' ');
      // 主关键字前换行 + 关键字转大写
      s = s.replace(/\b(SELECT|FROM|WHERE|GROUP\s+BY|ORDER\s+BY|HAVING|LIMIT|OFFSET|UNION\s+ALL|UNION|(?:LEFT|RIGHT|INNER|CROSS|FULL|OUTER)?\s*JOIN|ON|SET|VALUES|AND|OR)\b/gi,
        (m, k) => '\n' + k.toUpperCase());
      // 逗号换行(不带头空格, 缩进交给下方深度逻辑: 列表项缩进 +1)
      s = s.replace(/,\s*/g, ',\n');
      // 括号深度缩进; 列表项(上一行以逗号结尾)额外缩进 1 级
      const lines = s.split('\n').map(l => l.trim()).filter(Boolean);
      let depth = 0, out = [];
      lines.forEach((l, i) => {
        const opens = (l.match(/\(/g) || []).length;
        const closes = (l.match(/\)/g) || []).length;
        let d = depth;
        if (closes > opens) d = Math.max(0, depth - (closes - opens));
        const isListItem = i > 0 && lines[i - 1].endsWith(',');
        out.push('  '.repeat(d + (isListItem ? 1 : 0)) + l);
        depth = Math.max(0, depth + opens - closes);
      });
      return out.join('\n').replace(/\x01S(\d+)S\x01/g, (_, i) => strs[+i] || '');
    }
    function formatSqlInput() {
      const ta = document.getElementById('sqlInput');
      const f = formatSql(ta.value);
      if (f === ta.value) { toast('SQL 已是最佳格式'); return; }
      ta.value = f;
      syncSqlHighlight();
      ta.focus();
      toast('已格式化');
    }
    // ---- SQL 历史: 对象数组 {sql, t(时间戳)}, 兼容旧纯字符串数组; 收藏独立存储 ⭐ ----
    function loadSqlHist() {
      try {
        const raw = JSON.parse(localStorage.getItem('dbm_sql_hist') || '[]');
        return raw.map(x => typeof x === 'string' ? { sql: x, t: 0 } : x);
      } catch (e) { return []; }
    }
    function saveSqlHist(sql) {
      let h = loadSqlHist().filter(x => x.sql !== sql);
      h.unshift({ sql, t: Date.now() });
      if (h.length > 50) h = h.slice(0, 50);
      localStorage.setItem('dbm_sql_hist', JSON.stringify(h));
      renderSqlHist();
    }
    function loadSqlFavs() { try { return JSON.parse(localStorage.getItem('dbm_sql_fav') || '[]'); } catch (e) { return []; } }
    function toggleFav(sql) {
      let f = loadSqlFavs();
      f = f.includes(sql) ? f.filter(x => x !== sql) : [sql].concat(f);
      try { localStorage.setItem('dbm_sql_fav', JSON.stringify(f)); } catch (e) {}
      renderSqlHist();
    }
    function fmtHistTime(t) {
      if (!t) return '';
      const d = new Date(t), now = new Date();
      const hm = ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2);
      return d.toDateString() === now.toDateString() ? hm : ((d.getMonth() + 1) + '/' + d.getDate() + ' ' + hm);
    }
    function renderSqlHist() {
      const box = document.getElementById('sqlHist');
      const itemsBox = document.getElementById('sqlHistItems');
      const lbl = document.getElementById('histLbl');
      const h = loadSqlHist();
      if (!h.length) { box.style.display = 'none'; return; }
      box.style.display = '';
      const kw = (document.getElementById('sqlHistSearch').value || '').trim().toLowerCase();
      const favs = loadSqlFavs();
      const hit = h.filter(x => !kw || x.sql.toLowerCase().includes(kw));
      const itemHtml = x => `<span class="hist-item${favs.includes(x.sql) ? ' fav' : ''}" title="${esc(x.sql)}">
        <span class="hist-star" onclick="event.stopPropagation();toggleFav('${escAttr(x.sql)}')">${favs.includes(x.sql) ? '★' : '☆'}</span>
        <span class="hist-text" onclick="useSqlHist('${escAttr(x.sql)}')" ondblclick="useSqlHist('${escAttr(x.sql)}', true)">${esc(x.sql.length > 60 ? x.sql.slice(0, 60) + '…' : x.sql)}</span>
        ${x.t ? `<span class="hist-time">${fmtHistTime(x.t)}</span>` : ''}</span>`;
      const favPart = hit.filter(x => favs.includes(x.sql));
      const restPart = hit.filter(x => !favs.includes(x.sql));
      itemsBox.innerHTML = (favPart.length ? '<span class="hist-group">⭐ 收藏</span>' + favPart.map(itemHtml).join('') : '')
        + (restPart.length ? '<span class="hist-group">历史</span>' + restPart.map(itemHtml).join('') : '')
        + (hit.length ? '' : '<span class="hist-empty">无匹配历史</span>');
      lbl.textContent = favs.length ? `${favs.length} 收藏 · ${h.length} 条` : `${h.length} 条`;
    }
    function useSqlHist(sql, run) {
      if (!sql) return;
      document.getElementById('sqlInput').value = sql;
      syncSqlHighlight();
      if (run) runSql();
    }
    function clearSqlHist() { localStorage.removeItem('dbm_sql_hist'); localStorage.removeItem('dbm_sql_fav'); renderSqlHist(); }
    document.getElementById('sqlHistSearch').addEventListener('input', renderSqlHist);
    document.getElementById('sqlInput').addEventListener('keydown', e => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); runSql(); return; }
      const ac = document.getElementById('sqlAc');
      if (ac.classList.contains('show')) {
        if (e.key === 'ArrowDown') { e.preventDefault(); moveSqlAc(1); }
        else if (e.key === 'ArrowUp') { e.preventDefault(); moveSqlAc(-1); }
        else if (e.key === 'Enter') { e.preventDefault(); const it = (ac._items || [])[SQL_AC_IDX]; if (it) applySqlAc(it.label); }
        else if (e.key === 'Tab') { e.preventDefault(); const it = (ac._items || [])[SQL_AC_IDX]; if (it) applySqlAc(it.label); }
        else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); hideSqlAc(); }
      }
    });
    // ---- 全局快捷键: F5 刷新当前表 / Ctrl+Shift+F 聚焦SQL结果过滤 / Ctrl+1|2 切表tab / Ctrl+Enter 执行SQL(已有) ----
    document.addEventListener('keydown', e => {
      const tag = (e.target.tagName || '').toLowerCase();
      const inInput = tag === 'input' || tag === 'textarea' || tag === 'select';
      if (e.key === 'F5') {
        e.preventDefault();
        if (typeof loadData === 'function' && current && currentTab === 'data') loadData(currentPage);
        else if (typeof runSql === 'function') runSql();
        return;
      }
      if (e.key === 'F' && (e.ctrlKey || e.metaKey) && e.shiftKey) {
        e.preventDefault();
        const sf = document.getElementById('sqlFilter');
        if (sf && sf.offsetParent) { sf.focus(); sf.select(); }
        else {
          const wb = document.getElementById('whereBox');
          if (wb && wb.offsetParent) { wb.focus(); wb.select(); }
        }
        return;
      }
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !inInput && (e.key === '1' || e.key === '2')) {
        e.preventDefault();
        if (typeof switchTab === 'function') switchTab(e.key === '1' ? 'data' : 'struct');
      }
    });
    document.getElementById('sqlFilter').addEventListener('input', renderSqlFiltered);
    // 大表虚拟滚动: 数据网格滚动时按可视区重渲染(仅在虚拟模式 dataset.virtual=1 时生效)
    document.getElementById('grid').addEventListener('scroll', () => {
      const g = document.getElementById('grid');
      if (g && g.dataset.virtual === '1') renderVirtualRows();
    }, { passive: true });
    enableColResize();
    init();
