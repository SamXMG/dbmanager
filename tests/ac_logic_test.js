// 临时验证 dbmanager SQL 补全核心逻辑（无 DOM 纯逻辑部分）
const SQL_KW_SET = new Set(('SELECT TOP DISTINCT FROM WHERE AND OR NOT IN EXISTS LIKE BETWEEN IS NULL ORDER BY GROUP HAVING AS JOIN INNER LEFT RIGHT OUTER ON SET VALUES INSERT INTO UPDATE DELETE CREATE TABLE ALTER DROP INDEX UNIQUE PRIMARY KEY FOREIGN REFERENCES CASE WHEN THEN ELSE END UNION LIMIT OFFSET COUNT SUM AVG MAX MIN COALESCE NULLIF CAST CONVERT GETDATE DATEADD DATEDIFF LEN LOWER UPPER TRIM REPLACE SUBSTRING ISNULL CURRENT_DATE NOW').toLowerCase().split(' '));

function getDotContext(text, pos) {
  const prefix = text.slice(0, pos);
  const m = prefix.match(/([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\.([\w$]*)$/);
  if (!m) return null;
  return { ref: m[1], typed: m[2], insertStart: pos - m[2].length };
}

function parseSqlAliases(text) {
  const map = {};
  const re = /(?:FROM|JOIN)\s+([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?)(?:\s+(?:AS\s+)?([A-Za-z_$][\w$]*))?/gi;
  let m;
  while ((m = re.exec(text))) {
    const tableRef = m[1];
    map[tableRef.toLowerCase()] = tableRef;
    const alias = m[2];
    if (alias && !SQL_KW_SET.has(alias.toLowerCase())) map[alias.toLowerCase()] = tableRef;
  }
  return map;
}

const TABLES = [
  { schema: '', name: 'emp', type: 'Table' },
  { schema: 'dbo', name: 'orders', type: 'Table' },
  { schema: 'dbo', name: 'users', type: 'Table' },
];

function resolveRef(ref) {
  const aliases = parseSqlAliases(ref.fullText);
  const r = ref.ref.toLowerCase();
  let schema = '', table = '';
  const tableRef = aliases[r];
  if (tableRef) {
    const parts = tableRef.split('.');
    if (parts.length === 2) { schema = parts[0]; table = parts[1]; } else { table = parts[0]; }
  } else if (r.includes('.')) {
    const idx = r.lastIndexOf('.');
    schema = r.slice(0, idx); table = r.slice(idx + 1);
  } else {
    table = r;
    const hits = TABLES.filter(t => t.name.toLowerCase() === r);
    if (hits.length === 1) schema = hits[0].schema || '';
    else if (hits.length > 1) schema = (hits.find(t => t.schema) || hits[0]).schema || '';
  }
  return { schema, table };
}

let pass = 0, fail = 0;
function eq(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { pass++; console.log('  ✓', name); }
  else { fail++; console.log('  ✗', name, '\n    got ', g, '\n    want', w); }
}

console.log('== getDotContext ==');
eq('表名.', getDotContext('SELECT emp.', 11), { ref: 'emp', typed: '', insertStart: 11 });
eq('别名.', getDotContext('SELECT u. FROM users u', 9), { ref: 'u', typed: '', insertStart: 9 });
eq('schema.表.', getDotContext('SELECT dbo.users. FROM dbo.users', 17), { ref: 'dbo.users', typed: '', insertStart: 17 });
eq('点号后已输入', getDotContext('SELECT emp.ag FROM emp', 13), { ref: 'emp', typed: 'ag', insertStart: 11 });
eq('无点号', getDotContext('SELECT emp FROM emp', 11), null);
eq('系统对象', getDotContext('SELECT sys.objects.na FROM sys.objects', 21), { ref: 'sys.objects', typed: 'na', insertStart: 19 });

console.log('== parseSqlAliases ==');
eq('FROM+别名', parseSqlAliases('SELECT u. FROM users u WHERE 1=1'), { users: 'users', u: 'users' });
eq('JOIN schema表+AS', parseSqlAliases('SELECT o. FROM dbo.orders AS o'), { 'dbo.orders': 'dbo.orders', o: 'dbo.orders' });
eq('FROM 后关键字不当别名', parseSqlAliases('SELECT * FROM users WHERE id=1'), { users: 'users' });
eq('多个JOIN', parseSqlAliases('SELECT a. FROM users a JOIN emp e ON a.id=e.id'), { users: 'users', a: 'users', emp: 'emp', e: 'emp' });

console.log('== resolveRef ==');
eq('别名→表', resolveRef({ ref: 'u', fullText: 'SELECT u. FROM users u' }), { schema: '', table: 'users' });
eq('schema.表', resolveRef({ ref: 'dbo.users', fullText: 'SELECT dbo.users. FROM dbo.users' }), { schema: 'dbo', table: 'users' });
eq('裸表名→schema', resolveRef({ ref: 'emp', fullText: 'SELECT emp. FROM emp' }), { schema: '', table: 'emp' });
eq('系统对象不解析到TABLES', resolveRef({ ref: 'sys.objects', fullText: 'SELECT sys.objects. FROM sys.objects' }), { schema: 'sys', table: 'objects' });
eq('JOIN 别名', resolveRef({ ref: 'o', fullText: 'SELECT o. FROM dbo.orders AS o' }), { schema: 'dbo', table: 'orders' });

console.log('\n结果: ' + pass + ' 通过, ' + fail + ' 失败');
process.exit(fail ? 1 : 0);
