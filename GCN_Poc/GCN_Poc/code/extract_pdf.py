#!/usr/bin/env python3
"""Extract full text from the technical specification PDF."""
import fitz  # pymupdf

pdf_path = r"D:/lxt/learn/Best_Practices/GCN_Poc/doc/客户/原始需求/附件1+技术规范书.pdf"
doc = fitz.open(pdf_path)
print(f"Total pages: {len(doc)}")
print("=" * 80)
for i, page in enumerate(doc):
    text = page.get_text("text")
    print(f"\n--- PAGE {i+1} ---\n")
    print(text)
doc.close()
