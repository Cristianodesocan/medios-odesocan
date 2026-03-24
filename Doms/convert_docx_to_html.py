#!/usr/bin/env python3
import os
import zipfile
import xml.etree.ElementTree as ET

FOLDER = "/Users/cristiancpv/Desktop/TRABAJO/OBSERVATORIO/PROYECTOS/2026/Laboratorio/Panel de medios/files/Doms"
WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def extract_html_from_docx(docx_path):
    with zipfile.ZipFile(docx_path, "r") as zf:
        with zf.open("word/document.xml") as xml_file:
            tree = ET.parse(xml_file)
    root = tree.getroot()
    body = root.find(".//w:body", WORD_NS)
    lines = []
    for paragraph in body.findall("w:p", WORD_NS):
        run_texts = []
        for run in paragraph.findall(".//w:r", WORD_NS):
            t_node = run.find("w:t", WORD_NS)
            if t_node is not None:
                run_texts.append(t_node.text or "")
        lines.append("".join(run_texts))
    return "\n".join(lines)


def main():
    docx_files = [
        f for f in os.listdir(FOLDER)
        if f.endswith(".docx") and not f.startswith("~$")
    ]
    print(f"Found {len(docx_files)} file(s) to convert.\n")
    success = 0
    for filename in sorted(docx_files):
        docx_path = os.path.join(FOLDER, filename)
        html_filename = os.path.splitext(filename)[0] + ".html"
        html_path = os.path.join(FOLDER, html_filename)
        try:
            html_content = extract_html_from_docx(docx_path)
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            size_kb = len(html_content) / 1024
            lines = html_content.count("\n") + 1
            print(f"  OK  {filename!r}")
            print(f"       -> {html_filename!r}  ({size_kb:.1f} KB, {lines} líneas)")
            success += 1
        except Exception as e:
            print(f"  ERR {filename!r}: {e}")
    print(f"\nListo. {success}/{len(docx_files)} convertidos.")


if __name__ == "__main__":
    main()
