import fitz
import sys

pdf_path = sys.argv[1]
out_dir = sys.argv[2]

doc = fitz.open(pdf_path)
for i in range(min(2, len(doc))):
    page = doc.load_page(i)
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x scale for high resolution
    pix.save(f"{out_dir}/page_{i+1}.png")
print("Saved PDF pages to images.")
