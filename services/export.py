# -*- coding: utf-8 -*-
"""dbmanager - ops 文件: xlsx生成解析/CSV·JSON导出/数据字典/导入"""
import io
import json
import zipfile

from sqlalchemy import insert, select, text, true as sa_true

from dbcore import conn_hash, get_connection, get_engine
from services.core import _clear_count_cache, _qi, py_to_json, safe_where_clause
from services.metadata import get_columns, get_indexes, get_pk, get_table_obj, get_tables


# ------------------------------
# 数据查询 / 变更
# ------------------------------
EXPORT_LIMIT = 100000  # 导出行数上限, 防止超大表拖垮服务

# ------------------------------
# Excel(xlsx) 生成/解析: 纯 Python(zip+xml, 内联字符串), 不依赖第三方库
# ------------------------------
_XLSX_CONTENT_TYPES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    '</Types>')
_XLSX_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
    '</Relationships>')
_XLSX_WORKBOOK = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>')
_XLSX_WORKBOOK_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
    '</Relationships>')


def _xlsx_col_letter(i):
    """0 -> A, 25 -> Z, 26 -> AA ..."""
    s = ""
    i += 1
    while i:
        i, m = divmod(i - 1, 26)
        s = chr(65 + m) + s
    return s


def _xlsx_bytes(columns, rows):
    """生成最小 xlsx(首行表头 + 数据), 返回 bytes; columns 为列名列表, rows 为 dict 行"""
    from xml.sax.saxutils import escape as _xesc
    import zipfile, io
    parts = []
    for ri, row in enumerate(rows):
        cells = []
        for ci, cname in enumerate(columns):
            r = _xlsx_col_letter(ci) + str(ri + 2)
            v = row.get(cname) if isinstance(row, dict) else (row[ci] if ci < len(row) else None)
            if v is None:
                cells.append('<c r="%s"/>' % r)
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                cells.append('<c r="%s"><v>%s</v></c>' % (r, v))
            else:
                cells.append('<c r="%s" t="inlineStr"><is><t>%s</t></is></c>' % (r, _xesc(str(v))))
        parts.append('<row r="%d">%s</row>' % (ri + 2, "".join(cells)))
    hdr = "".join('<c r="%s1" t="inlineStr"><is><t>%s</t></is></c>'
                  % (_xlsx_col_letter(ci), _xesc(str(cname))) for ci, cname in enumerate(columns))
    sheet = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             '<sheetData><row r="1">%s</row>%s</sheetData></worksheet>' % (hdr, "".join(parts)))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _XLSX_CONTENT_TYPES)
        z.writestr("_rels/.rels", _XLSX_RELS)
        z.writestr("xl/workbook.xml", _XLSX_WORKBOOK)
        z.writestr("xl/_rels/workbook.xml.rels", _XLSX_WORKBOOK_RELS)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    return buf.getvalue()


def parse_xlsx_import(data):
    """解析 xlsx 文件为 (表头行, 数据行) 二维数组; 第一行视为表头。支持 sharedStrings 与 inlineStr。"""
    import zipfile, io, re
    from xml.etree import ElementTree as ET
    X = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall(X + "si"):
                shared.append("".join(t.text or "" for t in si.iter(X + "t")))
        sheets = sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
        if not sheets:
            raise ValueError("xlsx 中未找到工作表")
        root = ET.fromstring(z.read(sheets[0]))
        grid = []        # 每行: {列字母: 值}
        colset = set()   # 全部出现过的列字母(并集) —— openpyxl 等工具对空单元格不写 <c>, 必须按字母对齐补空
        for row in root.iter(X + "row"):
            cells = {}
            for c in row.iter(X + "c"):
                ref = c.get("r", "")
                m = re.match(r"[A-Z]+", ref)
                col = m.group() if m else ""
                t = c.get("t")
                v = c.find(X + "v")
                if t == "s" and v is not None and v.text is not None:
                    try:
                        cells[col] = shared[int(v.text)]
                    except Exception:
                        cells[col] = ""
                elif t == "inlineStr":
                    is_ = c.find(X + "is")
                    cells[col] = ("".join(t2.text or "" for t2 in is_.iter(X + "t"))
                                  if is_ is not None else "")
                elif v is not None:
                    cells[col] = v.text or ""
                else:
                    cells[col] = ""
            if cells:
                grid.append(cells)
                colset |= set(cells.keys())
    if not grid:
        return [], []
    cols = sorted(colset, key=lambda x: (len(x), x))
    aligned = [[cells.get(c, "") for c in cols] for cells in grid]
    return aligned[0], aligned[1:]   # 首行表头, 其余数据

def export_data(ci, schema, table, where, fmt="csv"):
    """导出表数据为 CSV(带 BOM, Excel 兼容)/JSON/XML/SQL-INSERT/XLSX, 受 where 过滤"""
    cols = get_columns(ci, schema, table)
    col_names = [c["name"] for c in cols]
    t = get_table_obj(ci, schema, table)
    w = safe_where_clause(where, col_names)
    where_clause = text(w) if w.strip() else sa_true()
    stmt = select(t).where(where_clause).limit(EXPORT_LIMIT)
    with get_engine(ci).connect() as conn:
        rows = [dict(r) for r in conn.execute(stmt).mappings()]
    if fmt == "xlsx":
        content = _xlsx_bytes(col_names, rows)
        return (content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                table + ".xlsx")
    if fmt == "json":
        content = json.dumps(rows, ensure_ascii=False, default=str, indent=2)
        return content, "application/json; charset=utf-8", table + ".json"
    if fmt == "xml":
        # XML 行式导出: <rows><row><col>值</col>...</row></rows>, 值经 XML 转义
        _esc = lambda s: (str(s).replace("&", "&amp;").replace("<", "&lt;")
                          .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;"))
        buf = io.StringIO()
        buf.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        buf.write("<rows>\n")
        for r in rows:
            buf.write("  <row>\n")
            for cn in col_names:
                v = py_to_json(r.get(cn))
                buf.write('    <%s>%s</%s>\n' % (cn, _esc("" if v is None else v), cn))
            buf.write("  </row>\n")
        buf.write("</rows>\n")
        return buf.getvalue(), "application/xml; charset=utf-8", table + ".xml"
    if fmt == "sql":
        # SQL-INSERT 导出: 完整 INSERT 语句(含表名/列名方言引用), 可回放
        db_type = (ci.get("db_type") or "mysql").lower()
        tbl = _qi(db_type, schema) + "." + _qi(db_type, table) if schema else _qi(db_type, table)
        buf = io.StringIO()
        cols_sql = ", ".join(_qi(db_type, c) for c in col_names)
        for r in rows:
            vals = []
            for cn in col_names:
                v = py_to_json(r.get(cn))
                if v is None:
                    vals.append("NULL")
                elif isinstance(v, (int, float)) and not isinstance(v, bool):
                    vals.append(str(v))
                else:
                    vals.append("'" + str(v).replace("'", "''") + "'")
            buf.write("INSERT INTO %s (%s) VALUES (%s);\n" % (tbl, cols_sql, ", ".join(vals)))
        return buf.getvalue(), "application/sql; charset=utf-8", table + ".sql"
    buf = io.StringIO()
    for i, cn in enumerate(col_names):
        if i:
            buf.write(",")
        buf.write('"' + str(cn).replace('"', '""') + '"')
    buf.write("\r\n")
    for r in rows:
        for i, cn in enumerate(col_names):
            if i:
                buf.write(",")
            v = py_to_json(r.get(cn))
            if v is None:
                continue
            s = str(v)
            buf.write('"' + s.replace('"', '""') + '"')
        buf.write("\r\n")
    return "\ufeff" + buf.getvalue(), "text/csv; charset=utf-8", table + ".csv"

def export_schema_doc(ci, table=None):
    """导出数据字典(Markdown): 单表或全库的表结构"""
    db_type = ci.get("db_type")
    tabs = get_tables(ci)
    if table:
        tabs = [x for x in tabs if x["name"] == table]
    md = ["# 数据字典", ""]
    md.append(f"- 数据库类型: {db_type}")
    md.append(f"- 表/视图数量: {len(tabs)}")
    md.append("")
    for tb in tabs:
        s, tname = tb["schema"], tb["name"]
        cols = get_columns(ci, s, tname)
        pk = get_pk(ci, s, tname)
        idxs = get_indexes(ci, s, tname)
        md.append(f"## {s}.{tname} ({tb['type']})")
        md.append("")
        md.append("| 字段 | 类型 | 可空 | 主键 | 自增 | 默认值 |")
        md.append("|---|---|---|---|---|---|")
        for c in cols:
            md.append(f"| {c['name']} | {c['type']} | {'是' if c['nullable'] else '否'} | "
                      f"{'是' if c['name'] in pk else ''} | {'是' if c['identity'] else ''} | {c['default'] or ''} |")
        if idxs:
            md.append("")
            md.append("**索引:**")
            for i in idxs:
                md.append(f"- {i['name'] or '(未命名)'}: {i['columns']}"
                          f"{' (唯一)' if i['is_unique'] else ''}{' (主键)' if i['is_pk'] else ''}")
        md.append("")
    return "\n".join(md)

IMPORT_ROW_LIMIT = 5000

def import_data(ci, schema, table, columns, rows, use_tx=False, tx_key=""):
    """批量导入: columns 为映射后的目标列(与 rows 每行一一对应)"""
    if not columns or not rows:
        raise ValueError("没有可导入的列或数据")
    if len(rows) > IMPORT_ROW_LIMIT:
        raise ValueError(f"单次导入最多 {IMPORT_ROW_LIMIT} 行, 当前 {len(rows)} 行")
    cols = get_columns(ci, schema, table)
    colmap = {c["name"]: c for c in cols}
    for cn in columns:
        if cn not in colmap:
            raise ValueError(f"目标列不存在: {cn}")
    target = [cn for cn in columns
              if not colmap[cn].get("identity") and not colmap[cn].get("computed")]
    if not target:
        raise ValueError("没有可导入的有效列(自增/计算列已排除)")
    t = get_table_obj(ci, schema, table)
    ins = insert(t)
    params = []
    for r in rows:
        rec = {}
        for cn in target:
            v = r.get(cn)
            if v is None:
                rec[cn] = None
            else:
                s = str(v).strip()
                rec[cn] = None if (s == "" and colmap[cn].get("nullable", True)) else s
        params.append(rec)
    engine = get_engine(ci)
    if use_tx:
        conn = get_connection(ci, use_tx=True, tx_key=tx_key)
        r = conn.execute(ins, params)
        affected = r.rowcount
    else:
        with engine.connect() as conn:
            r = conn.execute(ins, params)
            affected = r.rowcount
            conn.commit()
    _clear_count_cache(conn_hash(ci), schema, table)
    return {"ok": True, "affected": affected}

