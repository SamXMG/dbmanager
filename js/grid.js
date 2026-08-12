// dbmanager 前端 - 数据网格/筛选/编辑/右键菜单/结构
    async function loadStruct() { if (!current) return; try { const [cols, indexes] = await Promise.all([api(API + '/api/columns?' + qp({ s: current.s, t: current.t })), api(API + '/api/indexes?' + qp({ s: current.s, t: current.t }))]); let html = '<div class="struct-panel"><div style="margin-bottom:12px;display:flex;gap:8px;align-items:center;flex-wrap:wrap"><button class="sm primary" onclick="openAlter()">编辑表结构</button><button class="sm" onclick="openER()">ER 图</button><button class="sm" onclick="openUsers()">用户与权限</button><button class="sm" onclick="exportSchemaDoc()">导出数据字典(全库 Markdown)</button> <span style="color:#86909c;font-size:12px">含全部表的字段/索引/主键</span></div>'; html += '<div class="section"><h3>字段信息</h3><table><thead><tr>'; html += '<th>字段名</th><th>类型</th><th>可空</th><th>自增</th><th>默认值</th><th>精度/长度</th></tr></thead><tbody>'; cols.forEach(c => { html += `<tr><td>${esc(c.name)}</td><td>${esc(c.type)}</td><td>${c.nullable ? '是' : '否'}</td><td>${c.identity ? '是' : '否'}</td><td>${esc(c.default || '-')}</td><td>${c.precision ? c.precision + ',' + c.scale : (c.max_length != null ? c.max_length + '字节' : '-')}</td></tr>`; }); html += '</tbody></table></div>'; html += '<div class="section"><h3>索引与约束</h3><table><thead><tr>'; html += '<th>索引名</th><th>类型</th><th>字段</th><th>主键</th><th>唯一</th></tr></thead><tbody>'; indexes.forEach(i => { html += `<tr><td>${esc(i.name)}</td><td>${esc(i.type)}</td><td>${esc(i.columns)}</td><td>${i.is_pk ? '是' : '否'}</td><td>${i.is_unique ? '是' : '否'}</td></tr>`; }); html += '</tbody></table></div>'; html += '</div>'; document.getElementById('grid').innerHTML = html; document.getElementById('grid').style.display = 'block'; } catch (e) { toast('加载结构失败: ' + e.message, true); } }
    async function loadData(page) {
      const at = activeTab();
      if (!current || currentTab !== 'data' || !at) return;
      currentPage = page;
      selectedRows.clear(); lastSelIdx = null;   // 换页/刷新清空选中(旧索引无意义)
      const where = buildWhere();
      const size = document.getElementById('sizeSel').value;
      const order = curSort ? curSort.col + ':' + curSort.dir : '';
      const wb = document.getElementById('whereBox');
      wb.placeholder = (current.db_type === 'mongodb') ? 'MongoDB 查询条件(JSON)，如 {"age": {"$gt": 30}}' : '筛选条件(不含 WHERE)，如 name like \'%test%\'';
      try {
        const d = await api(API + '/api/data?' + qp({ s: current.s, t: current.t, page, size, where, order }));
        current.db_type = d.db_type || current.db_type;   // 后端回传类型: 供筛选/按钮语义判断
        currentMeta = d; at.meta = d; at.page = page; at.size = size; at.where = document.getElementById('whereBox').value;
        renderGrid(d);
        updateRedisBtns();
      } catch (e) { toast('查询失败: ' + e.message, true); }
    }
    let sortTimer = null;
    function toggleSortDelayed(ci) {
      // 单击排序延迟 250ms: 双击表头(手动输入列宽)时两次 click 会取消排序, 避免弹窗前排序乱跳
      if (sortTimer) { clearTimeout(sortTimer); sortTimer = null; return; }
      sortTimer = setTimeout(() => { sortTimer = null; toggleSort(ci); }, 250);
    }
    function toggleSort(ci) {
      const col = currentMeta.columns[ci];
      const name = col.name;
      if (!curSort || curSort.col !== name) curSort = { col: name, dir: 'asc' };
      else if (curSort.dir === 'asc') curSort.dir = 'desc';
      else curSort = null;
      loadData(1);
      saveTabState();
    }
    async function exportData(fmt) {
      if (!current) return;
      toast('正在导出 ' + current.t + '.' + fmt + ' ...');
      try {
        const hdrs = {};
        if (SESSION) hdrs['X-Session'] = SESSION; else if (CONN) hdrs['X-Conn'] = encConn(CONN);
        const r = await fetch(API + '/api/export?' + qp({ s: current.s, t: current.t, where: buildWhere(), fmt }), { headers: hdrs });
        if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(d.error || '导出失败'); }
        const blob = await r.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = current.t + '.' + fmt;
        document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(a.href);
        toast('已导出 ' + current.t + '.' + fmt);
      } catch (e) { toast('导出失败: ' + e.message, true); }
    }
    function buildWhere() {
      if (current && current.db_type === 'mongodb') return document.getElementById('whereBox').value.trim();
      const manual = document.getElementById('whereBox').value.trim(); const clauses = []; if (manual) clauses.push("(" + manual + ")"); for (const col in filters) { const f = filters[col]; if (!f || !f.op) continue; clauses.push(buildFilterClause(col, f)); } return clauses.join(' AND '); }
    function isStrType(t) { return ['varchar', 'nvarchar', 'char', 'nchar', 'text', 'ntext', 'uniqueidentifier', 'xml', 'sysname', 'uuid', 'string', 'clob', 'blob', 'json', 'longtext', 'mediumtext', 'tinytext', 'character varying', 'character', 'bpchar'].some(x => t === x || t.startsWith(x)); }
    function isDateType(t) { return ['date', 'datetime', 'datetime2', 'smalldatetime', 'time', 'datetimeoffset', 'timestamp', 'timestamptz'].some(x => t === x || t.startsWith(x)); }
    function quoteSql(v) { return "'" + String(v).replace(/'/g, "''") + "'"; }
    function buildFilterClause(col, f) { const colMeta = currentMeta.columns.find(c => c.name === col); const t = (colMeta ? colMeta.type : '').toLowerCase(); const needsQuote = isStrType(t) || isDateType(t); const qcol = quoteIdent(CONN ? CONN.db_type : 'mssql', col); const op = f.op, val = f.val; if (op === 'isnull') return `${qcol} IS NULL`; if (op === 'isnotnull') return `${qcol} IS NOT NULL`; if (op === 'between') { if (isDateType(t) && f.val2) { const d = new Date(String(f.val2) + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + 1); const nx = d.toISOString().slice(0, 10); return `${qcol} >= ${quoteSql(val)} AND ${qcol} < ${quoteSql(nx)}`; } const v1 = needsQuote ? quoteSql(val) : val; const v2 = needsQuote ? quoteSql(f.val2) : f.val2; return `${qcol} BETWEEN ${v1} AND ${v2}`; } let v; if (needsQuote) { if (op === 'contains') v = quoteSql('%' + val + '%'); else if (op === 'starts') v = quoteSql(val + '%'); else if (op === 'ends') v = quoteSql('%' + val); else v = quoteSql(val); } else { v = val; } if (op === 'contains' || op === 'starts' || op === 'ends') return `${qcol} LIKE ${v}`; const map = { eq: '=', ne: '<>', gt: '>', lt: '<', ge: '>=', le: '<=' }; return `${qcol} ${map[op]} ${v}`; } // 数字 / bit 等不引号
    function onFilterOpChange() {
      const op = document.getElementById('fpOp').value;
      const isBetween = op === 'between';
      const isNull = (op === 'isnull' || op === 'isnotnull');
      const v1 = document.getElementById('fpVal');
      if (v1) { v1.disabled = isNull; v1.placeholder = isBetween ? '最小值' : '值'; }
      const v2 = document.getElementById('fpVal2');
      if (v2) v2.style.display = isBetween ? '' : 'none';
    }
    async function openFilter(ci, thEl) { const col = currentMeta.columns[ci]; const t = col.type.toLowerCase(); const isStr = isStrType(t), isDate = isDateType(t); let ops; if (isStr) { ops = [['contains', '包含'], ['starts', '开头为'], ['ends', '结尾为'], ['eq', '等于'], ['ne', '不等于'], ['between', '介于...之间'], ['isnull', '为空'], ['isnotnull', '不为空']]; } else if (isDate) { ops = [['eq', '等于'], ['ne', '不等于'], ['gt', '大于'], ['lt', '小于'], ['ge', '大于等于'], ['le', '小于等于'], ['between', '介于...之间'], ['isnull', '为空'], ['isnotnull', '不为空']]; } else { ops = [['eq', '='], ['ne', '≠'], ['gt', '>'], ['lt', '<'], ['ge', '≥'], ['le', '≤'], ['between', '介于...之间'], ['isnull', '为空'], ['isnotnull', '不为空']]; } const ex = filters[col.name] || {}; const pop = document.getElementById('filterPop'); const isBetween = ex.op === 'between'; const needVal = !(ex.op === 'isnull' || ex.op === 'isnotnull'); const dtVal = v => { if (!isDate || !v) return v || ''; const m = String(v).match(/\d{4}-\d{2}-\d{2}/); return m ? m[0] : ''; }; const inType = isDate ? 'date' : 'text'; let html = `<div class="fp-head">筛选: <b>${esc(col.name)}</b> <span style="color:#86909c">(${esc(col.type)})</span></div>`; html += `<div class="fp-row"><select id="fpOp" onchange="onFilterOpChange()">${ops.map(o => `<option value="${o[0]}" ${ex.op === o[0] ? 'selected' : ''}>${o[1]}</option>`).join('')}</select></div>`; html += `<div class="fp-row"><input id="fpVal" type="${inType}" placeholder="${isBetween ? '最小值' : '值'}" value="${esc(dtVal(ex.val))}" ${needVal ? '' : 'disabled'}></div>`; html += `<div class="fp-row"><input id="fpVal2" type="${inType}" placeholder="最大值" value="${esc(dtVal(ex.val2))}" ${(needVal && isBetween) ? '' : 'style="display:none"'}></div>`; html += `<div class="fp-acts"><button class="sm" onclick="clearFilter('${escAttr(col.name)}')">清除</button><button class="sm primary" onclick="applyFilter('${escAttr(col.name)}')">应用</button></div>`; pop.innerHTML = html; pop.classList.add('show'); const rect = thEl.getBoundingClientRect(); pop.style.top = (window.scrollY + rect.bottom + 4) + 'px'; pop.style.left = Math.min(window.scrollX + rect.left, window.scrollX + window.innerWidth - 250) + 'px'; }
    async function applyFilter(col) { const op = document.getElementById('fpOp').value; const val = document.getElementById('fpVal').value; const val2 = document.getElementById('fpVal2') ? document.getElementById('fpVal2').value : ''; if (op === 'isnull' || op === 'isnotnull') { filters[col] = { op, val: '' }; } else if (op === 'between') { if (val.trim() === '' || val2.trim() === '') { delete filters[col]; } else { filters[col] = { op, val: val.trim(), val2: val2.trim() }; } } else if (val.trim() === '') { delete filters[col]; } else { filters[col] = { op, val: val.trim() }; } document.getElementById('filterPop').classList.remove('show'); await loadData(1); saveTabState(); }
    async function clearFilter(col) { delete filters[col]; document.getElementById('filterPop').classList.remove('show'); await loadData(1); saveTabState(); }
    async function clearAllFilters() { filters = {}; document.getElementById('filterPop').classList.remove('show'); await loadData(1); saveTabState(); }
    function updateFilterBadge() { const n = Object.keys(filters).length; const btn = document.getElementById('filterClear'); if (btn) btn.style.display = n > 0 ? '' : 'none'; }
    document.addEventListener('click', e => { const pop = document.getElementById('filterPop'); if (pop && pop.classList.contains('show') && !pop.contains(e.target) && !e.target.closest('.th-head')) { pop.classList.remove('show'); } });
    // ---- 表格组件化: 表头/行/单元格 拆成独立渲染函数(转义集中在单元格组件, 调用方免操心) ----
    // 类型着色 class: 数字绿/日期蓝/布尔紫(空值灰斜体), 深浅主题 CSS 已适配
    function cellTypeClass(col) {
      const t = String((col && col.type) || '').toLowerCase();
      if (/(int|float|double|decimal|number|numeric|real|money|smallint|bigint|tinyint)/.test(t)) return ' cell-num';
      if (/(date|time|timestamp|datetime)/.test(t)) return ' cell-date';
      if (/(bool|boolean|bit)/.test(t)) return ' cell-bool';
      return '';
    }
    function gridCellHtml(col, v, rowIdx) {
      const name = esc(col.name), nameAttr = escAttr(col.name);
      const tcls = cellTypeClass(col);
      if (v === null) {
        return `<td class="null" data-row="${rowIdx}" data-col="${name}" ondblclick="openCellEdit(${rowIdx},'${nameAttr}')" oncontextmenu="cellCtxMenu(event,${rowIdx},'${nameAttr}')">NULL</td>`;
      }
      const s = String(v);
      const disp = s.length > 2000 ? s.slice(0, 2000) + '…' : s;
      return `<td class="${tcls.trim()}" data-row="${rowIdx}" data-col="${name}" ondblclick="openCellEdit(${rowIdx},'${nameAttr}')" oncontextmenu="cellCtxMenu(event,${rowIdx},'${nameAttr}')"><div class="cell">${esc(disp)}</div></td>`;
    }
    // ---- 行选中: 单击选中(高亮), Ctrl/Shift 多选; 供批量删除/导出选中/统计栏使用 ----
    let selectedRows = new Set();   // 原始行索引集合(虚拟滚动/翻页重渲染后依然有效)
    let lastSelIdx = null;
    function toggleRowSelect(e, idx) {
      if (e.shiftKey && lastSelIdx != null) {
        // 范围选择: lastSelIdx -> idx
        const a = Math.min(lastSelIdx, idx), b = Math.max(lastSelIdx, idx);
        for (let i = a; i <= b; i++) selectedRows.add(i);
      } else if (e.ctrlKey || e.metaKey) {
        if (selectedRows.has(idx)) selectedRows.delete(idx); else selectedRows.add(idx);
      } else {
        if (selectedRows.size === 1 && selectedRows.has(idx)) { selectedRows.clear(); }
        else { selectedRows.clear(); selectedRows.add(idx); }
      }
      lastSelIdx = idx;
      refreshRowSelection();
    }
    function refreshRowSelection() {
      // 给当前渲染的行加/去 selected class(普通渲染与虚拟滚动都覆盖)
      const grid = document.getElementById('grid');
      grid.querySelectorAll('tbody tr').forEach(tr => {
        const i = parseInt(tr.dataset.i, 10);
        tr.classList.toggle('selected', Number.isInteger(i) && selectedRows.has(i));
      });
      updateSelUi();
      updateStatBar();
    }
    function toggleSelectAll() {
      const n = currentMeta ? currentMeta.rows.length : 0;
      if (!n) return;
      if (selectedRows.size === n) selectedRows.clear();
      else { selectedRows.clear(); for (let i = 0; i < n; i++) selectedRows.add(i); }
      lastSelIdx = null;
      refreshRowSelection();
    }
    function updateSelUi() {
      const n = selectedRows.size;
      const del = document.getElementById('delSelBtn');
      const exp = document.getElementById('expSelBtn');
      const all = document.getElementById('selectAllBtn');
      if (del) del.style.display = n ? '' : 'none';
      if (exp) exp.style.display = n ? '' : 'none';
      if (all) all.textContent = (currentMeta && n === currentMeta.rows.length && n > 0) ? '取消全选' : '全选';
    }
    async function deleteSelectedRows() {
      const idxs = [...selectedRows].sort((a, b) => b - a);   // 倒序删, 避免索引漂移
      if (!idxs.length) return;
      if (!confirm(`确认删除选中的 ${idxs.length} 行? 该操作不可撤销`)) return;
      try {
        const tx = txObj();
        for (const i of idxs) {
          const row = currentMeta.rows[i];
          const pkVals = {};
          (currentMeta.pk.length ? currentMeta.pk : currentMeta.columns.map(c => c.name)).forEach(cn => { pkVals[cn] = row[cn]; });
          const d = await api(API + '/api/row', { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.assign({ s: current.s, t: current.t, orig: pkVals, transaction: transactionMode }, tx)) });
          if (d.error) throw new Error(d.error);
        }
        selectedRows.clear(); lastSelIdx = null;
        toast('已删除 ' + idxs.length + ' 行');
        loadData(currentPage);
      } catch (e) { toast('删除失败: ' + e.message, true); }
    }
    function exportSelectedRows() {
      const idxs = [...selectedRows].sort((a, b) => a - b);
      if (!idxs.length || !currentMeta) return;
      const cols = currentMeta.columns.map(c => ({ name: c.name }));
      const rows = idxs.map(i => currentMeta.rows[i]);
      exportColsRows(cols, rows, 'selected_rows.xlsx');
    }
    // 复制选中行(TSV 带表头到剪贴板)
    async function copySelectedRows() {
      const idxs = [...selectedRows].sort((a, b) => a - b);
      if (!idxs.length || !currentMeta) { toast('请先选中行', true); return; }
      const cols = currentMeta.columns.map(c => c.name);
      const lines = idxs.map(i => {
        const row = currentMeta.rows[i] || {};
        return cols.map(c => row[c] == null ? '' : String(row[c])).join('\t');
      });
      await copyText([cols.join('\t'), ...lines].join('\n'));
    }
    // ---- 列级统计(COUNT/MIN/MAX + 数值列 SUM/AVG) ----
    function showStats() {
      if (!current || !currentMeta || !currentMeta.columns) { toast('请先打开表', true); return; }
      const cols = currentMeta.columns;
      showModal(`<h3>列统计 · ${esc(current.s)}.${esc(current.t)}</h3>
        <div class="field"><label>选择列</label><select id="stCol">${cols.map(c => `<option value="${escAttr(c.name)}">${esc(c.name)} (${esc(c.type)})</option>`).join('')}</select></div>
        <p style="color:#86909c;font-size:12px">按当前筛选条件统计(WHERE 生效)。</p>
        <div class="acts"><button onclick="closeModal()">取消</button><button class="primary" onclick="runStats()">统计</button></div>`);
    }
    async function runStats() {
      const col = document.getElementById('stCol').value;
      if (!col || !current) return;
      const where = (typeof buildWhere === 'function') ? buildWhere() : '';
      try {
        const d = await api(API + '/api/stats', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ s: current.s, t: current.t, col, where }) });
        if (d.error) throw new Error(d.error);
        let html = `<h3>统计结果 · ${esc(current.s)}.${esc(current.t)}.${esc(col)}</h3><table class="p-tbl" style="width:100%"><tbody>`;
        html += `<tr><td>记录数</td><td><b>${d.count != null ? d.count : '-'}</b></td></tr>`;
        [['最小值', d.min], ['最大值', d.max], ['总和', d.sum], ['平均值', d.avg]].forEach(([k, v]) => {
          if (v != null) html += `<tr><td>${k}</td><td><b>${esc(String(v))}</b></td></tr>`;
        });
        html += '</tbody></table><div class="acts"><button onclick="closeModal()">关闭</button></div>';
        showModal(html);
      } catch (e) { toast('统计失败: ' + e.message, true); }
    }
    // ---- 生成测试数据 ----
    function genTestData() {
      if (!current) { toast('请先打开表', true); return; }
      showModal(`<h3>生成测试数据 · ${esc(current.s)}.${esc(current.t)}</h3>
        <div class="field"><label>行数(1-50000)</label><input id="gdRows" type="number" value="100" min="1" max="50000"></div>
        <p style="color:#d4660a;font-size:12px">⚠ 按字段类型生成随机数据并真实插入(自增/只读列跳过)。</p>
        <div class="acts"><button onclick="closeModal()">取消</button><button class="primary" onclick="runGenData()">生成</button></div>`);
    }
    async function runGenData() {
      const rows = parseInt(document.getElementById('gdRows').value, 10) || 0;
      if (!current || rows < 1) { toast('请填写有效行数', true); return; }
      try {
        const d = await api(API + '/api/gen-data', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ s: current.s, t: current.t, rows }) });
        if (d.error) throw new Error(d.error);
        toast('已生成 ' + d.inserted + ' 条测试数据'); closeModal(); loadData(1);
      } catch (e) { toast('生成失败: ' + e.message, true); }
    }
    // ---- 统计栏: 共/选中行数 + 数字列求和均值(选中时按选中行, 否则全页) ----
    function isNumType(t) { return /int|float|double|decimal|number|numeric|real|money|smallint|bigint|tinyint|bit/i.test(String(t || '')); }
    function updateStatBar() {
      const bar = document.getElementById('statBar');
      if (!bar || !currentMeta) return;
      const rows = currentMeta.rows || [];
      const idxs = selectedRows.size ? [...selectedRows] : rows.map((_, i) => i);
      const cols = currentMeta.columns || [];
      let parts = [`共 ${rows.length} 行`, selectedRows.size ? `已选 ${selectedRows.size} 行` : ''];
      let numParts = [];
      cols.forEach(c => {
        if (numParts.length >= 3 || !isNumType(c.type)) return;
        let sum = 0, cnt = 0;
        idxs.forEach(i => {
          const v = rows[i] ? rows[i][c.name] : undefined;
          if (v != null && v !== '') { const n = Number(v); if (isFinite(n)) { sum += n; cnt++; } }
        });
        if (cnt) numParts.push(`${esc(c.name)}: 和 ${fmtNum(sum)} · 均 ${fmtNum(sum / cnt)}`);
      });
      bar.innerHTML = parts.filter(Boolean).join(' · ') + (numParts.length ? ' · ' + numParts.join(' · ') : '');
      bar.style.display = 'flex';
    }
    function fmtNum(v) {
      if (Math.abs(v) >= 1e8 || (Math.abs(v) < 1e-4 && v !== 0)) return v.toExponential(2);
      const s = Number(v.toFixed(2)).toString();
      return s.length > 16 ? v.toExponential(2) : s;
    }
    function gridRowHtml(row, rowIdx, cols) {
      const sel = selectedRows.has(rowIdx) ? ' selected' : '';
      let h = `<tr class="grid-row${sel}" data-i="${rowIdx}" onclick="toggleRowSelect(event,${rowIdx})">`;
      cols.forEach(c => { h += gridCellHtml(c, row[c.name], rowIdx); });
      if (current && current.db_type === 'redis') {
        // Redis 键无"行"概念: 只留改(编辑元素), 删除必须走工具栏「删除键」(整键)
        h += `<td style="white-space:nowrap" oncontextmenu="rowCtxMenu(event,${rowIdx})" title="右键更多操作"><button class="sm" onclick="event.stopPropagation();openEdit(${rowIdx})">改</button></td>`;
      } else {
        h += `<td style="white-space:nowrap" oncontextmenu="rowCtxMenu(event,${rowIdx})" title="右键更多操作"><button class="sm" onclick="event.stopPropagation();openEdit(${rowIdx})">改</button><button class="sm danger" onclick="event.stopPropagation();doDelete(${rowIdx})">删</button></td>`;
      }
      return h + '</tr>';
    }
    function gridHeadHtml(cols, pk) {
      let h = '<tr>';
      cols.forEach((c, ci) => {
        const isPk = pk.includes(c.name);
        const flag = filters[c.name] ? ' ▾' : '';
        const cls = filters[c.name] ? ' th-head th-filtered' : ' th-head';
        const isSorted = curSort && curSort.col === c.name;
        const arrow = isSorted ? (curSort.dir === 'asc' ? ' ▲' : ' ▼') : '';
        h += `<th class="${cls}" data-c="${escAttr(c.name)}" onclick="toggleSortDelayed(${ci})" title="点击排序, 双击设置列宽">${esc(c.name)}<span class="sort-arrow">${arrow}</span><span class="th-filter" title="筛选" onclick="event.stopPropagation();openFilter(${ci}, this)">▽</span><span class="th-flag">${flag}</span><br><span class="th-type" style="font-weight:400;color:#86909c">${esc(c.type)}${isPk ? ' ·PK' : ''}</span><span class="th-resize" title="拖动调整列宽，双击恢复自动" onclick="event.stopPropagation()"></span></th>`;
      });
      return h + '<th style="width:100px">操作</th></tr>';
    }
    // ---- 大表虚拟滚动: 只渲染可视区行(行高固定32px, 上下占位行撑高) ----
    const VIRTUAL_ROW_H = 32, VIRTUAL_THRESHOLD = 300, VIRTUAL_BUFFER = 10;
    function renderVirtualRows() {
      const grid = document.getElementById('grid');
      if (grid.dataset.virtual !== '1') return;
      const rows = currentMeta.rows, cols = currentMeta.columns;
      if (!rows || !rows.length) return;
      const total = rows.length;
      const st = grid.scrollTop || 0;
      const vh = grid.clientHeight || 400;
      let start = Math.max(0, Math.floor(st / VIRTUAL_ROW_H) - VIRTUAL_BUFFER);
      let end = Math.min(total, Math.ceil((st + vh) / VIRTUAL_ROW_H) + VIRTUAL_BUFFER);
      let h = `<tr class="vs-spacer"><td style="height:${start * VIRTUAL_ROW_H}px;padding:0;border:none"></td></tr>`;
      for (let i = start; i < end; i++) h += gridRowHtml(rows[i], i, cols);
      h += `<tr class="vs-spacer"><td style="height:${(total - end) * VIRTUAL_ROW_H}px;padding:0;border:none"></td></tr>`;
      grid.querySelector('tbody').innerHTML = h;
    }
    function renderGrid(d) {
      const cols = d.columns, pk = d.pk, rows = d.rows;
      const grid = document.getElementById('grid');
      if (!rows.length && !d.total) {
        grid.innerHTML = '<div class="empty">无数据' + (d.total === -1 ? ' (总数未知)' : ' (total=' + d.total + ')') + '</div>';
      } else if (rows.length >= VIRTUAL_THRESHOLD) {
        // 虚拟滚动模式: 只渲染表头 + 占位, 滚动时按可视区重渲染 tbody
        grid.dataset.virtual = '1';
        let h = '<table class="virtual"><thead>' + gridHeadHtml(cols, pk) + '</thead><tbody>';
        h += `<tr class="vs-spacer"><td style="height:${rows.length * VIRTUAL_ROW_H}px;padding:0;border:none"></td></tr></tbody></table>`;
        grid.innerHTML = h;
        const gtable = grid.querySelector('table');
        if (gtable) gtable.dataset.colkey = colWKey();
        fitTableWidths(grid, '.th-type');
        applyColWidths(gtable);
        renderVirtualRows();
      } else {
        grid.dataset.virtual = '';
        let h = '<table><thead>' + gridHeadHtml(cols, pk) + '</thead><tbody>';
        h += rows.map((row, idx) => gridRowHtml(row, idx, cols)).join('');
        h += '</tbody></table>';
        grid.innerHTML = h;
        const gtable = grid.querySelector('table');
        if (gtable) gtable.dataset.colkey = colWKey();   // 表级列宽记忆标识
        fitTableWidths(grid, '.th-type');
        applyColWidths(gtable);                            // 应用跨会话记忆的列宽
      }
      const tp = Math.max(1, Math.ceil(d.total / d.size));
      const pager = document.getElementById('pager');
      pager.style.display = 'flex';
      pager.innerHTML = `共 ${d.total} 行 · 第 ${d.page}/${tp} 页<button class="sm" ${d.page <= 1 ? 'disabled' : ''} onclick="loadData(${d.page - 1})">上一页</button><button class="sm" ${d.page >= tp ? 'disabled' : ''} onclick="loadData(${d.page + 1})">下一页</button>`;
      updateFilterBadge();
      updateSelUi();
      updateStatBar();
    }
    function openCellEdit(rowIdx, colName) {
      const col = currentMeta.columns.find(c => c.name === colName);
      if (!col || col.identity || col.computed) { toast('该字段不可编辑(自增/计算列)', true); return; }
      const val = currentMeta.rows[rowIdx][colName];
      const t = col.type.toLowerCase();
      const isStr = isStrType(t), isDate = isDateType(t);
      const isLong = isStr && (col.max_length === -1 || (col.max_length || 0) > 255);
      const isPk = currentMeta.pk.includes(colName);
      const disp = val == null ? '' : String(val);
      let ctrl;
      if (isDate) ctrl = `<input id="cellEditVal" type="date" value="${esc(disp.slice(0, 10))}" style="width:100%">`;
      else if (isLong || isStr) ctrl = `<textarea id="cellEditVal" rows="8" style="width:100%;min-width:420px;max-width:640px;box-sizing:border-box">${esc(disp)}</textarea>`;
      else ctrl = `<input id="cellEditVal" type="text" value="${esc(disp)}" style="width:100%">`;
      let html = `<h3>编辑字段 · ${esc(current.s)}.${esc(current.t)}</h3>`;
      html += `<div class="field"><label>${esc(col.name)} <span style="color:#86909c">(${esc(col.type)}${col.nullable ? ' 可空' : ''}${isPk ? ' ·PK' : ''}${col.identity ? ' ·自增' : ''})</span></label>${ctrl}</div>`;
      html += `<label style="font-size:12px;display:flex;align-items:center;gap:6px;margin:8px 0"><input type="checkbox" id="cellEditNull" ${val === null ? 'checked' : ''}> 设为 NULL</label>`;
      html += `<div class="acts"><button onclick="closeModal()">取消</button><button class="primary" onclick="submitCellEditModal()">保存</button></div>`;
      window.__cellEdit = { rowIdx, colName, origValue: val };
      showModal(html);
    }
    async function submitCellEditModal() {
      const c = window.__cellEdit;
      if (!c) return;
      const isNull = document.getElementById('cellEditNull').checked;
      const newVal = isNull ? null : document.getElementById('cellEditVal').value;
      const orig = {};
      currentMeta.columns.forEach(col => orig[col.name] = currentMeta.rows[c.rowIdx][col.name]);
      if (!isNull && String(newVal) === String(c.origValue == null ? '' : c.origValue)) { closeModal(); return; }
      try {
        const d = await api(API + '/api/row', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.assign({ s: current.s, t: current.t, orig, values: { [c.colName]: newVal }, transaction: transactionMode }, txObj())) });
        toast('已更新 ' + d.affected + ' 行'); closeModal(); loadData(currentPage);
      } catch (e) { toast('更新失败: ' + e.message, true); }
    }
    function startEdit(rowIdx, colName) { if (editingCell) cancelEdit(); const col = currentMeta.columns.find(c => c.name === colName); if (!col || col.identity || col.computed) return; const td = document.querySelector(`td[data-row="${rowIdx}"][data-col="${colName}"]`); if (!td) return; const val = currentMeta.rows[rowIdx][colName]; editingCell = { rowIdx, colName, origValue: val }; td.classList.add('editing'); td.innerHTML = `<input type="text" value="${esc(val == null ? '' : String(val))}" id="editInput" onblur="submitCellEdit()" onkeydown="handleEditKey(event)">`; document.getElementById('editInput').focus(); document.getElementById('editInput').select(); }
    function handleEditKey(e) { if (e.key === 'Enter') { e.preventDefault(); submitCellEdit(); } if (e.key === 'Escape') { e.preventDefault(); cancelEdit(); } }
    function cancelEdit() { if (!editingCell) return; const { rowIdx, colName, origValue } = editingCell; const td = document.querySelector(`td[data-row="${rowIdx}"][data-col="${colName}"]`); if (td) { td.classList.remove('editing'); if (origValue === null) td.innerHTML = 'NULL'; else td.innerHTML = `<div class="cell">${esc(String(origValue))}</div>`; } editingCell = null; }
    async function submitCellEdit() { if (!editingCell) return; const { rowIdx, colName, origValue } = editingCell; const input = document.getElementById('editInput'); const newValue = input ? input.value : ''; if (String(newValue) === String(origValue || '')) { cancelEdit(); return; } const cols = currentMeta.columns; const row = currentMeta.rows[rowIdx]; const orig = {}; cols.forEach(c => orig[c.name] = row[c.name]); try { const d = await api(API + '/api/row', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.assign({ s: current.s, t: current.t, orig, values: { [colName]: newValue }, transaction: transactionMode }, txObj())) }); toast('已更新 ' + d.affected + ' 行'); editingCell = null; loadData(currentPage); } catch (e) { toast('更新失败: ' + e.message, true); cancelEdit(); } }
    function fieldHtml(col, val, isEdit) {
      // 从 <template id="tpl-field"> 克隆字段控件: 结构在 HTML, JS 只填数据; 值用 .value 免转义
      const node = document.getElementById('tpl-field').content.cloneNode(true);
      const isPk = currentMeta.pk.includes(col.name);
      const disabled = col.identity || col.computed;
      const label = node.querySelector('label');
      label.innerHTML = esc(col.name) + ' <span style="color:#86909c">(' + esc(col.type) + (col.nullable ? ' 可空' : '') + ')</span>' + (isPk ? '<span style="color:#f53f3f"> ·PK</span>' : '') + (col.identity ? ' ·自增' : '');
      const input = node.querySelector('input');
      input.id = 'f_' + col.name;
      input.value = (val == null ? '' : String(val));
      if (disabled) input.disabled = true;
      return node;
    }
    async function openAdd() {
      if (!current) return;
      const cols = currentMeta.columns;
      let html = `<h3>新增行 · ${esc(current.s)}.${esc(current.t)}</h3><div id="modalFields"></div><div class="acts"><button onclick="closeModal()">取消</button><button class="primary" onclick="submitAdd()">保存</button></div>`;
      showModal(html);
      const holder = document.getElementById('modalFields');
      cols.forEach(c => holder.appendChild(fieldHtml(c, '', false)));
    }
    async function openEdit(idx) {
      const cols = currentMeta.columns, row = currentMeta.rows[idx];
      let html = `<h3>修改行 · ${esc(current.s)}.${esc(current.t)}</h3><div id="modalFields"></div><div class="acts"><button onclick="closeModal()">取消</button><button class="primary" onclick="submitEdit(${idx})">保存</button></div>`;
      showModal(html);
      const holder = document.getElementById('modalFields');
      cols.forEach(c => holder.appendChild(fieldHtml(c, row[c.name], true)));
    }
    function collectValues() { const cols = currentMeta.columns, vals = {}; cols.forEach(c => { const el = document.getElementById('f_' + c.name); if (el && !el.disabled) vals[c.name] = el.value; }); return vals; }
    async function submitAdd() { const values = collectValues(); try { const d = await api(API + '/api/row', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.assign({ s: current.s, t: current.t, values, transaction: transactionMode }, txObj())) }); toast('已新增 ' + d.affected + ' 行'); closeModal(); loadData(currentPage); } catch (e) { toast('新增失败: ' + e.message, true); } }
    async function submitEdit(idx) { const cols = currentMeta.columns, row = currentMeta.rows[idx]; const orig = {}; cols.forEach(c => orig[c.name] = row[c.name]); const values = collectValues(); try { const d = await api(API + '/api/row', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.assign({ s: current.s, t: current.t, orig, values, transaction: transactionMode }, txObj())) }); toast('已更新 ' + d.affected + ' 行'); closeModal(); loadData(currentPage); } catch (e) { toast('更新失败: ' + e.message, true); } }
    async function doDelete(idx) { const cols = currentMeta.columns, row = currentMeta.rows[idx]; const orig = {}; cols.forEach(c => orig[c.name] = row[c.name]); const pk = currentMeta.pk; let summary = pk.length ? pk.map(k => `${k}=${row[k]}`).join(', ') : '整行匹配'; if (!confirm('确认删除该行?\n' + summary)) return; try { const d = await api(API + '/api/row', { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.assign({ s: current.s, t: current.t, orig, transaction: transactionMode }, txObj())) }); toast('已删除 ' + d.affected + ' 行'); loadData(currentPage); } catch (e) { toast('删除失败: ' + e.message, true); } }

    // ---- Redis 键级操作: 新建键 / TTL / 删除键(确认) ----
    function updateRedisBtns() {
      const on = current && current.db_type === 'redis';
      const ids = ['redisNewKeyBtn', 'redisTtlBtn', 'redisDelKeyBtn'];
      ids.forEach(id => { const el = document.getElementById(id); if (el) el.style.display = on ? '' : 'none'; });
    }
    async function redisAlter(action, payload) {
      return api(API + '/api/alter', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ s: current.s, t: current.t, action, payload }) });
    }
    function redisNewKey() {
      if (!current) return;
      showModal(`<h3>新建 Redis 键</h3>
        <div class="field"><label>键名</label><input id="rkName" placeholder="如 user:1001"></div>
        <div class="field"><label>类型</label><select id="rkType">
          <option value="string">String</option><option value="hash">Hash</option>
          <option value="list">List</option><option value="set">Set</option><option value="zset">ZSet</option>
        </select></div>
        <div class="field"><label>初始值</label><input id="rkVal" placeholder="String 为值；Hash/List/Set 为单个元素；ZSet 为成员(score=0)"></div>
        <div class="field"><label>过期秒数(留空=永久)</label><input id="rkTtl" type="number" placeholder="如 3600"></div>
        <div class="acts"><button onclick="closeModal()">取消</button><button class="primary" onclick="redisNewKeySubmit()">创建</button></div>`);
    }
    async function redisNewKeySubmit() {
      const name = document.getElementById('rkName').value.trim();
      if (!name) { toast('请填写键名', true); return; }
      const type = document.getElementById('rkType').value;
      const value = document.getElementById('rkVal').value;
      const ttl = document.getElementById('rkTtl').value;
      try {
        await redisAlter('create', { type, value, ttl: ttl ? parseInt(ttl, 10) : 0 });
        toast('已创建键 ' + name);
        closeModal();
        refreshTables();
      } catch (e) { toast('创建失败: ' + e.message, true); }
    }
    async function redisTtl() {
      if (!current) return;
      let cur = '';
      try { const d = await redisAlter('set_ttl', {}); cur = (d.ttl != null && d.ttl > 0) ? d.ttl + ' 秒' : '永久(-1)'; } catch (e) { cur = '(获取失败)'; }
      showModal(`<h3>键 ${esc(current.t)} 的 TTL</h3>
        <div class="field"><label>当前过期时间</label><div style="color:var(--text2)">${cur}</div></div>
        <div class="field"><label>新过期秒数(0=永久)</label><input id="rtTtl" type="number" placeholder="如 3600"></div>
        <div class="acts"><button onclick="closeModal()">取消</button><button class="primary" onclick="redisTtlSubmit()">应用</button></div>`);
    }
    async function redisTtlSubmit() {
      const ttl = document.getElementById('rtTtl').value;
      if (ttl === '') { toast('请输入过期秒数(0=永久)', true); return; }
      try {
        await redisAlter('set_ttl', { ttl: parseInt(ttl, 10) });
        toast('TTL 已更新');
        closeModal();
      } catch (e) { toast('设置失败: ' + e.message, true); }
    }
    function redisDelKey() {
      if (!current) return;
      if (!confirm(`⚠️ 将删除整个键 "${current.t}"，该键下所有数据不可恢复！\n确定继续吗？`)) return;
      (async () => {
        try {
          await redisAlter('drop', {});
          toast('已删除键 ' + current.t);
          const tab = TABS.find(x => x.s === current.s && x.t === current.t);
          if (tab) closeDocTab(tab.id, { stopPropagation: () => {} });
          renderTables(document.getElementById('treeFilter') ? document.getElementById('treeFilter').value : '');
        } catch (e) { toast('删除失败: ' + e.message, true); }
      })();
    }
    function showCtxMenu(x, y, items) {
      const m = document.getElementById('ctxMenu');
      const tpl = document.getElementById('tpl-ctx-item');
      m.innerHTML = '';
      items.forEach((it, i) => {
        if (it.sep) {
          const s = document.createElement('div');
          s.className = 'cm-sep';
          m.appendChild(s);
          return;
        }
        const node = tpl.content.cloneNode(true);
        const el = node.querySelector('.cm-item');
        el.textContent = it.label;                 // textContent 填值: 免转义
        if (it.danger) el.classList.add('danger');
        el.addEventListener('click', () => { hideCtxMenu(); items[i].fn(); });
        m.appendChild(node);
      });
      m.classList.add('show');
      const r = m.getBoundingClientRect();
      m.style.left = Math.max(4, Math.min(x, window.innerWidth - r.width - 8)) + 'px';
      m.style.top = Math.max(4, Math.min(y, window.innerHeight - r.height - 8)) + 'px';
    }
    function hideCtxMenu() { document.getElementById('ctxMenu').classList.remove('show'); }
    document.addEventListener('click', e => { if (!e.target.closest('#ctxMenu')) hideCtxMenu(); });
    document.addEventListener('contextmenu', e => { if (!e.target.closest('#ctxMenu')) hideCtxMenu(); });
    window.addEventListener('scroll', hideCtxMenu, true);
    function copyText(t) { if (navigator.clipboard) { navigator.clipboard.writeText(t).then(() => toast('已复制'), () => toast('复制失败', true)); } else toast('当前环境不支持剪贴板', true); }
    async function setCellNull(rowIdx, colName) {
      const orig = {};
      currentMeta.columns.forEach(c => orig[c.name] = currentMeta.rows[rowIdx][c.name]);
      try {
        const d = await api(API + '/api/row', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.assign({ s: current.s, t: current.t, orig, values: { [colName]: null }, transaction: transactionMode }, txObj())) });
        toast('已置空 ' + d.affected + ' 行'); loadData(currentPage);
      } catch (e) { toast('操作失败: ' + e.message, true); }
    }
    function cellCtxMenu(e, idx, colName) {
      e.preventDefault(); e.stopPropagation();
      const col = currentMeta.columns.find(c => c.name === colName);
      const row = currentMeta.rows[idx];
      const val = row[colName];
      const items = [
        { label: '编辑此字段', fn: () => openCellEdit(idx, colName) },
        { label: '复制值', fn: () => copyText(val == null ? 'NULL' : String(val)) },
      ];
      if (col && col.nullable && val !== null && !col.identity && !col.computed) items.push({ label: '设为 NULL', danger: true, fn: () => setCellNull(idx, colName) });
      items.push({ sep: true }, { label: '复制整行 JSON', fn: () => copyText(JSON.stringify(row, null, 2)) });
      showCtxMenu(e.clientX, e.clientY, items);
    }
    function rowCtxMenu(e, idx) {
      e.preventDefault(); e.stopPropagation();
      showCtxMenu(e.clientX, e.clientY, [
        { label: '编辑行', fn: () => openEdit(idx) },
        { label: '复制行 JSON', fn: () => copyText(JSON.stringify(currentMeta.rows[idx], null, 2)) },
        { sep: true },
        { label: '删除行', danger: true, fn: () => doDelete(idx) },
      ]);
    }
    function tableCtxMenu(e, schema, name) {
      e.preventDefault(); e.stopPropagation();
      showCtxMenu(e.clientX, e.clientY, [
        { label: '打开', fn: () => openTable(schema, name) },
        { label: '查看结构', fn: () => { openTable(schema, name); switchTab('struct'); } },
        { sep: true },
        { label: '刷新', fn: () => renderTables('') },
        { label: '复制表名', fn: () => copyText(schema ? schema + '.' + name : name) },
        { label: '复制 SELECT SQL', fn: () => copySelectSql(schema, name) },
        { label: '生成 INSERT 模板', fn: () => genInsertSql(schema, name) },
        { sep: true },
        { label: '表设计器(字段/索引/外键/触发器)', fn: () => openAlter(schema, name) },
        { label: '新建触发器', fn: () => newTrigger(schema, name) },
        { sep: true },
        { label: 'ER 关系图', fn: () => showEr(schema, name) },
        { sep: true },
        { label: '导出 CSV', fn: () => exportTableCsv(schema, name) },
        { label: '同步到...(结构)', fn: () => { openTable(schema, name); openSync(); } },
        { label: '数据同步到...(数据)', fn: () => openDataTransfer(schema, name) },
      ]);
    }
    // ---- 数据级同步: 源表数据 → 目标表(同连接/跨库) ----
    function openDataTransfer(s, t) {
      if (!s || !t) { toast('请先选中表', true); return; }
      const dbs = (typeof DBS !== 'undefined' ? DBS : []) || [];
      const cur = curDb || (CONN && CONN.database) || '';
      const opts = [cur, ...dbs.filter(d => d && d !== cur)];
      showModal(`<h3>数据同步 · ${esc(s)}.${esc(t)}</h3>
        <div class="field"><label>目标库</label><select id="trDb">${opts.map(d => `<option value="${escAttr(d)}" ${d === cur ? 'selected' : ''}>${esc(d)}</option>`).join('')}</select></div>
        <div class="field"><label>目标表(须已存在)</label><input id="trTable" placeholder="如 ${esc(t)}_copy"></div>
        <p style="color:#d4660a;font-size:12px">⚠ 源表全部数据将插入目标表(同名列交集); 目标自增主键由数据库生成。</p>
        <div class="acts"><button onclick="closeModal()">取消</button><button class="primary" onclick="runTransfer()">开始同步</button></div>`);
    }
    async function runTransfer() {
      if (!current) { toast('请先打开源表', true); return; }
      const toDb = document.getElementById('trDb').value;
      const toT = document.getElementById('trTable').value.trim();
      if (!toT) { toast('请填写目标表', true); return; }
      try {
        const d = await api(API + '/api/transfer', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ s: current.s, t: current.t, to_db: toDb, to_t: toT }) });
        if (d.error) throw new Error(d.error);
        toast('已同步 ' + d.transferred + ' 行数据'); closeModal();
      } catch (e) { toast('同步失败: ' + e.message, true); }
    }
    async function copyText(t) {
      try { await navigator.clipboard.writeText(t); toast('已复制: ' + t.slice(0, 60)); }
      catch (e) { toast('复制失败(浏览器限制)', true); }
    }
    function qident(n) { return quoteIdent(CONN && CONN.db_type, n); }
    async function copySelectSql(s, t) {
      copyText('SELECT * FROM ' + qident(s) + '.' + qident(t));
    }
    async function genInsertSql(s, t) {
      try {
        const cols = await api(API + '/api/columns?' + qp({ s, t }));
        if (!cols.length) { toast('无字段', true); return; }
        copyText('INSERT INTO ' + qident(s) + '.' + qident(t) + ' (' + cols.map(c => qident(c.name)).join(', ') + ') VALUES (' + cols.map(() => '?').join(', ') + ');');
      } catch (e) { toast('生成失败: ' + e.message, true); }
    }
    // ---- ER 图: 纯 SVG 渲染中心表+直接外键关联表(邻接图) ----
    async function showEr(schema, name) {
      try {
        const hdrs = {};
        if (SESSION) hdrs['X-Session'] = SESSION; else if (CONN) hdrs['X-Conn'] = encConn(CONN);
        const d = await fetch(API + '/api/er?' + qp({ s: schema, t: name }), { headers: hdrs }).then(r => r.json());
        if (d.error) throw new Error(d.error);
        const tables = d.tables || [], rels = d.relations || [];
        if (!tables.length) { toast('无表数据', true); return; }
        renderErSvg(schema, name, tables, rels);
      } catch (e) { toast('ER 图加载失败: ' + e.message, true); }
    }
    function renderErSvg(schema, name, tables, rels) {
      const TW = 190, TH = 26, TDH = 18, PAD = 30;
      // 中心表置顶, 其余按列数排序(列多的宽)
      const centerKey = schema + '.' + name;
      const ordered = [tables.find(t => (t.schema + '.' + t.name) === centerKey) || tables[0]]
        .concat(tables.filter(t => (t.schema + '.' + t.name) !== centerKey).sort((a, b) => b.columns.length - a.columns.length));
      const n = ordered.length;
      const cols = Math.max(1, Math.ceil(Math.sqrt(n * 1.4)));   // 方形网格
      const rowsN = Math.ceil(n / cols);
      const cellW = TW + PAD, cellH = 90 + Math.max.apply(null, ordered.map(t => t.columns.length)) * TDH + PAD;
      const W = Math.max(600, cols * cellW + PAD), H = Math.max(400, rowsN * cellH + PAD);
      const pos = {};
      ordered.forEach((t, i) => {
        const cx = i % cols, cy = Math.floor(i / cols);
        pos[t.schema + '.' + t.name] = { x: PAD + cx * cellW, y: PAD + cy * cellH };
      });
      const pkSet = key => new Set((tables.find(t => (t.schema + '.' + t.name) === key) || {}).pk || []);
      // 表方框
      let box = '';
      ordered.forEach(t => {
        const p = pos[t.schema + '.' + t.name];
        const h = TH + t.columns.length * TDH;
        box += `<rect x="${p.x}" y="${p.y}" width="${TW}" height="${h}" rx="6" fill="var(--panel)" stroke="#86909c"/>`;
        box += `<rect x="${p.x}" y="${p.y}" width="${TW}" height="${TH}" rx="6" fill="#165dff" opacity="0.15"/>`;
        box += `<text x="${p.x + 8}" y="${p.y + 17}" font-size="12" font-weight="600" fill="var(--text)">${esc(t.name)}</text>`;
        t.columns.forEach((c, ci) => {
          const y = p.y + TH + 14 + ci * TDH;
          const isPk = t.pk.includes(c.name);
          box += `<text x="${p.x + 8}" y="${y}" font-size="11" fill="${isPk ? '#f7ba1e' : 'var(--text2)'}">${isPk ? '🔑 ' : ''}${esc(c.name)}</text>`;
          box += `<text x="${p.x + TW - 8}" y="${y}" font-size="10" text-anchor="end" fill="var(--text3)">${esc(String(c.type).split('(')[0])}</text>`;
        });
      });
      // 连线(贝塞尔)
      let lines = '';
      rels.forEach(r => {
        const from = pos[r.from_schema + '.' + r.from_table];
        const to = pos[r.to_schema + '.' + r.to_table];
        if (!from || !to) return;
        const x1 = from.x + TW, y1 = from.y + TH + 8;
        const x2 = to.x, y2 = to.y + TH + 8;
        const mx = (x1 + x2) / 2;
        lines += `<path d="M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}" fill="none" stroke="#165dff" stroke-width="1.2" marker-end="url(#erArrow)"/>`;
        const lbl = (r.from_columns || []).map((c, i) => c + ' → ' + ((r.to_columns || [])[i] || '')).join(', ');
        lines += `<text x="${mx}" y="${(y1 + y2) / 2 - 4}" font-size="10" fill="#165dff" text-anchor="middle">${esc(lbl)}</text>`;
      });
      const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" style="width:100%;min-width:${W}px;background:var(--panel);border-radius:8px">
        <defs><marker id="erArrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#165dff"/></marker></defs>
        ${box}${lines}</svg>`;
      showModal(`<h3>ER 关系图 · ${esc(schema ? schema + '.' : '')}${esc(name)} <span style="color:#86909c;font-weight:400;font-size:12px">(${tables.length} 表 · ${rels.length} 关系, 双击表名打开)</span></h3>
        <div style="overflow:auto;max-height:70vh">${svg}</div>
        <div class="acts"><button class="primary" onclick="closeModal()">关闭</button></div>`);
    }
    async function exportTableCsv(s, t) {
      try {
        const hdrs = {};
        if (SESSION) hdrs['X-Session'] = SESSION; else if (CONN) hdrs['X-Conn'] = encConn(CONN);
        const r = await fetch(API + '/api/export?' + qp({ s, t, where: '', fmt: 'csv' }), { headers: hdrs });
        if (!r.ok) throw new Error('导出失败');
        const blob = await r.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob); a.download = t + '.csv';
        document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(a.href);
        toast('已导出 ' + t + '.csv');
      } catch (e) { toast('导出失败: ' + e.message, true); }
    }
