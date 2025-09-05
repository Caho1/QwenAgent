#写一个提取pdf第一页的脚本，简单点
import fitz

def extract_text_from_pdf(pdf_path: str) -> str:
    try:
        doc = fitz.open(pdf_path)
        if len(doc) > 0:
            text = doc[0].get_text("text")
            doc.close()
            return text
        doc.close()
        return ""
    except Exception as e:
        print("PDF文本提取失败:", e)
        return ""

if __name__ == "__main__":
    path = "AP测试文件/ap_sample1.pdf"
    text = extract_text_from_pdf(path)
    print(text)