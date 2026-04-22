"""通用 docx 报告提取器：文本 + 内联图片标记 + 表格

用法:
    python extract_report.py <docx路径> [输出目录]

参数:
    docx路径    待提取的 .docx 文件路径
    输出目录    提取结果保存目录（默认: docx 所在目录）

输出:
    report_text.txt   段落 + 表格 + 内联 [IMAGE: xxx] 标记（按文档顺序）
    images/           嵌入图片（按出现顺序编号）

特性:
    - 图片标记直接嵌入文本流中，与上下文段落紧邻
    - 可快速定位"某图标题 → 对应图片文件"的映射关系
"""
import sys
from pathlib import Path
from lxml import etree


# Word XML 命名空间
_NS = {
    'w':  'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'r':  'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
    'a':  'http://schemas.openxmlformats.org/drawingml/2006/main',
    'pic': 'http://schemas.openxmlformats.org/drawingml/2006/picture',
    'v':  'urn:schemas-microsoft-com:vml',
}


def _extract_images_from_element(el, rels, img_dir: Path, img_counter: list) -> list[str]:
    """从一个 XML 元素中提取所有嵌入图片，返回 [IMAGE: xxx] 标记列表"""
    markers = []

    # 方式1: <w:drawing> -> <a:blip r:embed="rIdXX">
    for blip in el.findall('.//a:blip', _NS):
        r_embed = blip.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed')
        if r_embed and r_embed in rels:
            rel = rels[r_embed]
            if 'image' in rel.reltype:
                img_counter[0] += 1
                ext = Path(rel.target_ref).suffix or '.png'
                img_name = f"image_{img_counter[0]:03d}{ext}"
                (img_dir / img_name).write_bytes(rel.target_part.blob)
                markers.append(f"[IMAGE: {img_name}]")

    # 方式2: <v:imagedata r:id="rIdXX"> (旧式 VML 图片)
    for imgdata in el.findall('.//v:imagedata', _NS):
        r_id = imgdata.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
        if r_id and r_id in rels:
            rel = rels[r_id]
            if 'image' in rel.reltype:
                img_counter[0] += 1
                ext = Path(rel.target_ref).suffix or '.png'
                img_name = f"image_{img_counter[0]:03d}{ext}"
                (img_dir / img_name).write_bytes(rel.target_part.blob)
                markers.append(f"[IMAGE: {img_name}]")

    return markers


def _table_to_lines(tbl_el, rels, img_dir: Path, img_counter: list) -> list[str]:
    """将 <w:tbl> 元素转为文本行（含内联图片标记）"""
    lines = []
    for tr in tbl_el.findall('.//w:tr', _NS):
        cells = []
        for tc in tr.findall('w:tc', _NS):
            cell_text = ''.join(node.text or '' for node in tc.iter('{%s}t' % _NS['w']))
            img_marks = _extract_images_from_element(tc, rels, img_dir, img_counter)
            cell_content = cell_text.strip()
            if img_marks:
                cell_content += ' ' + ' '.join(img_marks)
            cells.append(cell_content)
        lines.append(' | '.join(cells))
    return lines


def extract_report(docx_path: Path, out_dir: Path):
    import docx as docx_lib

    doc = docx_lib.Document(str(docx_path))
    rels = {rel.rId: rel for rel in doc.part.rels.values()}
    body = doc.element.body

    out_dir.mkdir(parents=True, exist_ok=True)
    img_dir = out_dir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    img_counter = [0]  # 用列表做可变计数器

    # 按文档顺序遍历 body 的直接子元素
    for child in body:
        tag = etree.QName(child).localname

        if tag == 'p':  # 段落
            # 提取段落文本
            text = ''.join(node.text or '' for node in child.iter('{%s}t' % _NS['w']))
            text = text.strip()
            # 提取段落中的图片
            img_marks = _extract_images_from_element(child, rels, img_dir, img_counter)
            if text and img_marks:
                lines.append(f"{text}  {' '.join(img_marks)}")
            elif text:
                lines.append(text)
            elif img_marks:
                lines.append(' '.join(img_marks))
            # 空段落跳过

        elif tag == 'tbl':  # 表格
            tbl_lines = _table_to_lines(child, rels, img_dir, img_counter)
            lines.extend(tbl_lines)

    report_text = "\n".join(lines)

    # 保存
    text_path = out_dir / "report_text.txt"
    text_path.write_text(report_text, encoding="utf-8")

    print(f"文本: {text_path} ({len(report_text)} chars, {len(lines)} lines)")
    print(f"图片: {img_counter[0]} 张 -> {img_dir} (内联标记已嵌入文本)")
    print(f"段落+表格行: {len(lines)} lines")

    return text_path, img_dir, img_counter[0]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    docx_path = Path(sys.argv[1])
    if not docx_path.exists():
        print(f"ERROR: {docx_path} 不存在")
        sys.exit(1)

    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else docx_path.parent
    extract_report(docx_path, out_dir)


if __name__ == "__main__":
    main()
