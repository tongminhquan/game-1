from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


OUTPUT = Path("docs/Huong_dan_su_dung_WordPress_Auto_Poster.docx")

BLUE = RGBColor(46, 116, 181)
DARK_BLUE = RGBColor(31, 77, 120)
INK = RGBColor(34, 34, 34)
MUTED = RGBColor(90, 90, 90)
LIGHT_BLUE = "E8EEF5"
LIGHT_GRAY = "F4F6F9"
WHITE = "FFFFFF"


def set_run_font(run, name: str = "Calibri", size: int | None = None, bold: bool | None = None, color=None) -> None:
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:ascii"), name)
    run._element.rPr.rFonts.set(qn("w:hAnsi"), name)
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color is not None:
        run.font.color.rgb = color


def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_margins(cell, top=80, start=120, bottom=80, end=120) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for margin, value in {"top": top, "start": start, "bottom": bottom, "end": end}.items():
        node = tc_mar.find(qn(f"w:{margin}"))
        if node is None:
            node = OxmlElement(f"w:{margin}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_cell_width(cell, width_in: float) -> None:
    width = int(width_in * 1440)
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_w = tc_pr.find(qn("w:tcW"))
    if tc_w is None:
        tc_w = OxmlElement("w:tcW")
        tc_pr.append(tc_w)
    tc_w.set(qn("w:w"), str(width))
    tc_w.set(qn("w:type"), "dxa")


def set_table_width(table, widths: list[float]) -> None:
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    for row in table.rows:
        for idx, width in enumerate(widths):
            set_cell_width(row.cells[idx], width)
            row.cells[idx].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            set_cell_margins(row.cells[idx])

    tbl = table._tbl
    tbl_pr = tbl.tblPr
    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(int(sum(widths) * 1440)))
    tbl_w.set(qn("w:type"), "dxa")


def add_para(doc, text: str = "", style: str | None = None, bold_prefix: str | None = None):
    paragraph = doc.add_paragraph(style=style)
    if bold_prefix and text.startswith(bold_prefix):
        run = paragraph.add_run(bold_prefix)
        set_run_font(run, bold=True)
        rest = paragraph.add_run(text[len(bold_prefix) :])
        set_run_font(rest)
    else:
        run = paragraph.add_run(text)
        set_run_font(run)
    return paragraph


def add_bullets(doc, items: list[str]) -> None:
    for item in items:
        p = doc.add_paragraph(style="List Bullet")
        set_run_font(p.add_run(item))


def add_numbers(doc, items: list[str]) -> None:
    for item in items:
        p = doc.add_paragraph(style="List Number")
        set_run_font(p.add_run(item))


def add_note(doc, label: str, body: str, fill: str = LIGHT_GRAY) -> None:
    table = doc.add_table(rows=1, cols=1)
    set_table_width(table, [6.5])
    cell = table.cell(0, 0)
    set_cell_shading(cell, fill)
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    run = p.add_run(f"{label}: ")
    set_run_font(run, bold=True, color=DARK_BLUE)
    run = p.add_run(body)
    set_run_font(run)
    doc.add_paragraph()


def add_table(doc, headers: list[str], rows: list[list[str]], widths: list[float]) -> None:
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    set_table_width(table, widths)
    header_cells = table.rows[0].cells
    for idx, header in enumerate(headers):
        set_cell_shading(header_cells[idx], LIGHT_BLUE)
        p = header_cells[idx].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(header)
        set_run_font(run, bold=True, color=DARK_BLUE)
    for row_values in rows:
        cells = table.add_row().cells
        for idx, value in enumerate(row_values):
            set_cell_width(cells[idx], widths[idx])
            set_cell_margins(cells[idx])
            p = cells[idx].paragraphs[0]
            run = p.add_run(value)
            set_run_font(run)
    doc.add_paragraph()


def configure_styles(doc: Document) -> None:
    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    normal.font.color.rgb = INK
    normal._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
    normal._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.25

    for style_name, size, color, before, after in [
        ("Heading 1", 16, BLUE, 18, 10),
        ("Heading 2", 13, BLUE, 14, 7),
        ("Heading 3", 12, DARK_BLUE, 10, 5),
    ]:
        style = styles[style_name]
        style.font.name = "Calibri"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = color
        style._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
        style._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)

    for style_name in ["List Bullet", "List Number"]:
        style = styles[style_name]
        style.font.name = "Calibri"
        style.font.size = Pt(11)
        style.paragraph_format.space_after = Pt(4)
        style.paragraph_format.line_spacing = 1.25


def add_header_footer(doc: Document) -> None:
    section = doc.sections[0]
    header = section.header
    p = header.paragraphs[0]
    p.text = ""
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = p.add_run("WordPress Auto Poster - Hướng dẫn sử dụng")
    set_run_font(run, size=9, color=MUTED)

    footer = section.footer
    p = footer.paragraphs[0]
    p.text = ""
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("Tài liệu nội bộ - kiểm tra preview trước khi đăng thật")
    set_run_font(run, size=9, color=MUTED)


def build_doc() -> None:
    doc = Document()
    section = doc.sections[0]
    section.orientation = WD_ORIENT.PORTRAIT
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)

    configure_styles(doc)
    add_header_footer(doc)

    title = doc.add_paragraph()
    title.paragraph_format.space_after = Pt(3)
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = title.add_run("Hướng dẫn sử dụng WordPress Auto Poster")
    set_run_font(run, size=24, bold=True, color=BLUE)

    subtitle = doc.add_paragraph()
    subtitle.paragraph_format.space_after = Pt(12)
    run = subtitle.add_run("Dành cho quy trình đăng bài SEO HTML lên WordPress từ file Excel")
    set_run_font(run, size=12, color=MUTED)

    add_note(
        doc,
        "Mục tiêu",
        "Giúp người dùng chuẩn bị Excel, kiểm tra preview, đăng bài thủ công hoặc theo lịch, "
        "xuất báo cáo và tránh đăng nhầm lên website thật.",
        fill="F4F8FC",
    )

    doc.add_heading("1. Chuẩn bị trước khi mở app", level=1)
    add_bullets(
        doc,
        [
            "File chạy app: C:\\Users\\Admin\\OneDrive\\Tài liệu\\Đăng bài tự động\\dist\\WordPressAutoPoster.exe.",
            "File Excel mẫu: docs\\Mau_Excel_Dang_Bai_SEO_HTML_WordPress.xlsx.",
            "Thư mục ảnh mẫu: docs\\mau_ten_hinh_anh.",
            "Tài khoản WordPress có quyền tạo bài viết và Application Password hợp lệ.",
            "File Excel bài viết, ưu tiên sheet Bài SEO HTML nếu dùng bộ bài SEO đã xuất.",
            "Thư mục ảnh local nếu muốn app tự upload ảnh đại diện và ảnh chèn trong bài.",
            "Nên test trên website staging hoặc để trạng thái bài là draft trước khi đăng thật.",
        ],
    )

    doc.add_heading("2. Kết nối WordPress lần đầu", level=1)
    add_para(
        doc,
        "Trước khi chọn Excel và đăng bài, cần kết nối app với WordPress bằng REST API. "
        "Thông tin quan trọng nhất là URL phải đúng định dạng và password phải là Application Password.",
    )
    add_table(
        doc,
        ["Ô trong app", "Cách nhập đúng", "Lỗi thường gặp"],
        [
            [
                "URL",
                "Nhập đầy đủ https://tenmien.com. Không nhập thiếu https:// và không cần thêm /wp-json.",
                "Nếu chỉ nhập tenmien.com, app sẽ báo No scheme supplied.",
            ],
            [
                "Username",
                "Nhập username đăng nhập WordPress, ví dụ admin. Không dùng tên hiển thị nếu tên đó khác username.",
                "Sai username thường gây lỗi 401 hoặc không có quyền tạo bài.",
            ],
            [
                "Application password",
                "Dùng mật khẩu ứng dụng tạo trong WordPress, không dùng mật khẩu đăng nhập bình thường.",
                "Sai password hoặc dùng password thường sẽ báo rest_not_logged_in.",
            ],
        ],
        [1.35, 3.0, 2.15],
    )
    add_numbers(
        doc,
        [
            "Mở trang quản trị WordPress, ví dụ https://thongcongdongnai.com/wp-admin.",
            "Đăng nhập bằng tài khoản có quyền tạo bài viết.",
            "Vào Người dùng -> Hồ sơ. Nếu giao diện tiếng Anh: Users -> Profile.",
            "Kéo xuống mục Mật khẩu ứng dụng hoặc Application Passwords.",
            "Nhập tên ứng dụng, ví dụ WordPress Auto Poster, rồi bấm thêm mật khẩu ứng dụng mới.",
            "Copy toàn bộ mật khẩu WordPress vừa sinh ra. Mật khẩu này chỉ hiện một lần.",
            "Quay lại app, nhập URL, Username và Application password rồi bấm Kiểm tra kết nối.",
            "Chỉ bấm đăng bài khi trạng thái kết nối báo OK.",
        ],
    )
    add_note(
        doc,
        "Cách hiểu lỗi 401",
        "Nếu app báo WordPress API error 401 hoặc rest_not_logged_in, nghĩa là WordPress chưa chấp nhận thông tin đăng nhập API. "
        "Hãy tạo lại Application Password đúng user, kiểm tra username, và kiểm tra plugin bảo mật hoặc hosting có đang chặn REST API không.",
        fill="FFF7E6",
    )

    doc.add_heading("3. Cấu trúc Excel app đang hỗ trợ", level=1)
    add_para(
        doc,
        "App tự chọn sheet có dữ liệu bài viết. Với workbook SEO, app ưu tiên sheet Bài SEO HTML "
        "và giữ nguyên HTML trong cột Nội dung HTML thuần để các đầu mục H2, H3, đoạn văn và liên hệ "
        "đi vào phần nội dung WordPress.",
    )
    add_table(
        doc,
        ["Cột trong Excel", "Được đưa vào WordPress", "Ghi chú"],
        [
            ["Tiêu đề SEO", "Title", "Tên bài viết hiển thị trong WordPress."],
            ["Nội dung HTML thuần", "Content", "Giữ nguyên HTML, gồm H2, H3, P, strong và liên hệ."],
            ["Slug", "Slug", "Đường dẫn tĩnh của bài viết."],
            ["Mô tả Meta SEO", "Excerpt", "Dùng làm phần tóm tắt native của WordPress."],
            ["Danh mục", "Category", "App tìm hoặc tạo danh mục nếu tài khoản có quyền."],
            ["Từ khóa chính", "Tag", "Đưa vào tag đầu tiên."],
            ["Từ khóa phụ đã phủ thêm", "Tags", "Tách theo dấu phẩy, tự bỏ trùng."],
        ],
        [1.6, 1.65, 3.25],
    )
    add_note(
        doc,
        "Kết quả đã kiểm tra",
        "File bai_seo_thang_may_bien_hoa_html_bo_ket_luan_them_lien_he (1).xlsx đọc được 75 bài, "
        "75 slug, 75 mô tả meta, 75 thẻ H2 và 450 thẻ H3.",
        fill="FFF7E6",
    )

    doc.add_heading("4. Quy ước ảnh local", level=1)
    add_para(doc, "Nếu Excel có cột ma_bai, đặt ảnh trong cùng một thư mục theo quy ước sau:")
    add_table(
        doc,
        ["Mẫu tên file", "Vai trò", "Ví dụ"],
        [
            ["{ma_bai}_bg.jpg", "Ảnh đại diện", "bai01_bg.jpg"],
            ["{ma_bai}_1.jpg", "Ảnh nội dung thứ 1", "bai01_1.jpg"],
            ["{ma_bai}_2.png", "Ảnh nội dung thứ 2", "bai01_2.png"],
            ["{ma_bai}_3.webp", "Ảnh nội dung tiếp theo", "bai01_3.webp"],
        ],
        [2.0, 2.1, 2.4],
    )
    add_bullets(
        doc,
        [
            "Mã ma_bai trong Excel là khóa để app nhận diện ảnh thuộc bài nào.",
            "Ví dụ ma_bai = thang-may-gia-dinh thì mọi ảnh của bài đó phải bắt đầu bằng thang-may-gia-dinh_.",
            "Ảnh _bg được ưu tiên hơn featured_image_url trong Excel.",
            "Ảnh _1, _2, _3 được upload rồi chèn đều vào nội dung bài.",
            "File ảnh không khớp mã bài sẽ hiện cảnh báo ảnh không khớp trong preview.",
            "Đuôi ảnh hỗ trợ: jpg, jpeg, png, webp.",
        ],
    )

    doc.add_heading("5. Cách đăng bài thủ công", level=1)
    add_numbers(
        doc,
        [
            "Mở WordPressAutoPoster.exe. Lần đầu mở có thể chậm hơn vì file one-file tự giải nén runtime.",
            "Nhập URL website WordPress, username và Application Password.",
            "Bấm Kiểm tra kết nối. Chỉ tiếp tục khi trạng thái báo OK.",
            "Chọn file Excel. Với bộ SEO hiện tại, chỉ cần chọn workbook có sheet Bài SEO HTML.",
            "Chọn thư mục ảnh nếu cần dùng ảnh local. Có thể bỏ trống nếu chỉ đăng nội dung HTML.",
            "Chỉnh số ảnh tối đa mỗi bài nếu có nhiều ảnh nội dung.",
            "Bấm Preview để kiểm tra số bài, tiêu đề, mã bài, ảnh nền và số ảnh nội dung.",
            "Bấm Đăng ngay, đọc hộp xác nhận rồi mới đồng ý đăng.",
            "Sau khi chạy xong, xem bảng kết quả và bấm Xuất báo cáo Excel nếu cần lưu lại log.",
        ],
    )

    doc.add_heading("6. Dùng lịch tự động", level=1)
    add_bullets(
        doc,
        [
            "Mở tab Lịch tự động.",
            "Chọn file Excel cố định và thư mục ảnh cố định.",
            "Chọn Hàng ngày, Hàng tuần hoặc Custom cron.",
            "Tick Bật lịch tự động để kích hoạt.",
            "Khi bấm nút X, app thu xuống khay hệ thống để lịch vẫn chạy.",
            "Muốn thoát hẳn, dùng menu chuột phải ở icon khay hệ thống và chọn Thoát hẳn.",
        ],
    )
    add_note(
        doc,
        "Lưu ý",
        "Application Password không được lưu vào settings.json. Sau khi mở lại app, cần nhập lại password "
        "trong phiên hiện tại để job theo lịch có thể đăng bài.",
    )

    doc.add_heading("7. Checklist trước khi đăng thật", level=1)
    add_table(
        doc,
        ["Mục kiểm tra", "Trạng thái cần đạt"],
        [
            ["Kết nối WordPress", "Kiểm tra kết nối báo OK."],
            ["Excel", "Preview hiện đủ số bài cần đăng."],
            ["Sheet Bài SEO HTML", "Nội dung HTML không bị trống, tiêu đề và slug đầy đủ."],
            ["Danh mục và tag", "Danh mục đúng, tag không bị dính chuỗi sai định dạng."],
            ["Ảnh local", "Số ảnh nội dung và cảnh báo ảnh không khớp đã được kiểm tra."],
            ["Trạng thái bài", "Nên dùng draft trước khi đăng public hàng loạt."],
            ["Báo cáo", "Sau khi chạy xong, xuất báo cáo Excel để kiểm tra bài lỗi."],
        ],
        [2.45, 4.05],
    )

    doc.add_heading("8. Xử lý lỗi thường gặp", level=1)
    add_table(
        doc,
        ["Hiện tượng", "Cách xử lý"],
        [
            ["App mở chậm", "Chờ thêm trong lần mở đầu vì exe one-file cần giải nén runtime."],
            ["Không đọc được Excel", "Kiểm tra file có sheet Bài SEO HTML hoặc cột title/content chuẩn."],
            ["Preview thiếu bài", "Kiểm tra hàng trống, tiêu đề trống hoặc cột Nội dung HTML thuần trống."],
            ["No scheme supplied", "URL đang thiếu https://. Nhập dạng https://tenmien.com, không chỉ nhập tenmien.com."],
            ["rest_not_logged_in / 401", "Sai username, sai Application Password hoặc WordPress đang chặn REST API."],
            ["Không kết nối WordPress", "Kiểm tra URL, username, Application Password và REST API."],
            ["Ảnh không khớp", "Đổi tên ảnh theo đúng ma_bai_bg, ma_bai_1, ma_bai_2."],
            ["Bài bị trùng", "App kiểm tra trùng theo title và có thể skip bài đã tồn tại."],
            ["Windows cảnh báo file exe", "Chọn More info rồi Run anyway nếu bạn tin tưởng file do chính mình build."],
        ],
        [2.05, 4.45],
    )

    doc.add_heading("9. Nguyên tắc an toàn", level=1)
    add_bullets(
        doc,
        [
            "Không dùng website thật để thử lần đầu nếu chưa kiểm tra preview.",
            "Không lưu Application Password vào file chia sẻ công khai.",
            "Không tắt app giữa lúc đang đăng. Nếu cần dừng, bấm Dừng và chờ app dừng sau bài hiện tại.",
            "Luôn kiểm tra bài mẫu trên WordPress sau khi đăng để chắc HTML, slug và excerpt hiển thị đúng.",
            "Nếu dùng lịch tự động, kiểm tra múi giờ và lần chạy kế tiếp trước khi rời máy.",
        ],
    )

    doc.add_heading("10. Tóm tắt thao tác nhanh", level=1)
    add_table(
        doc,
        ["Mục tiêu", "Thao tác nhanh"],
        [
            ["Đăng 75 bài SEO HTML", "Chọn Excel -> Preview -> kiểm tra đủ 75 bài -> Đăng ngay."],
            ["Chỉ kiểm tra nội dung", "Chọn Excel -> Preview, không bấm Đăng ngay."],
            ["Đăng kèm ảnh local", "Chọn thư mục ảnh đúng quy ước ma_bai trước khi Preview."],
            ["Chạy theo lịch", "Tab Lịch tự động -> chọn Excel -> bật lịch -> để app ở khay hệ thống."],
            ["Lưu kết quả", "Sau khi chạy xong -> Xuất báo cáo Excel."],
        ],
        [2.1, 4.4],
    )

    doc.add_paragraph()
    add_note(
        doc,
        "Phiên bản tài liệu",
        "Cập nhật theo bản app đã hỗ trợ sheet Bài SEO HTML, slug, excerpt và kiểm tra 75 bài SEO thang máy.",
        fill=LIGHT_BLUE,
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUTPUT)


if __name__ == "__main__":
    build_doc()
    print(OUTPUT)
