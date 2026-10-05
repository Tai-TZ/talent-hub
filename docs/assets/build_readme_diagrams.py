"""Sinh các sơ đồ SVG động (isometric 3D) cho README.

Chạy: python docs/assets/build_readme_diagrams.py  → ghi các tệp vào docs/assets/readme/.

Chỉ dùng SVG + CSS (GitHub không chạy script trong ảnh): khối 3D dựng bằng phép chiếu isometric, chuyển động bằng
@keyframes và offset-path, tự đổi màu theo chế độ sáng/tối của người xem và tắt chuyển động khi người xem bật
"giảm chuyển động" (prefers-reduced-motion).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

OUT = Path(__file__).parent / "readme"
COS, SIN = math.cos(math.radians(30)), math.sin(math.radians(30))

# Bảng màu: lấy từ token thương hiệu (xanh Northwind University) + các sắc phụ có độ sáng cân bằng; mỗi khối có mặt trên/trái/phải.
FACES = {
    "blue": ("#5d9bc8", "#1d6199", "#134d8b"),
    "navy": ("#387aad", "#134d8b", "#0b2a4d"),
    "teal": ("#4fc7b6", "#0e9a8a", "#0a7569"),
    "amber": ("#f2c46d", "#d39a2c", "#a87418"),
    "violet": ("#a99be6", "#7b68c9", "#5b49a6"),
    "slate": ("#c9d3de", "#93a3b5", "#6f8297"),
    "red": ("#ef8a8e", "#d73a40", "#9e171d"),
    "green": ("#7fd1a3", "#2f9a62", "#0e623a"),
}

STYLE = """
<style>
  :root { --ink: #1f2933; --muted: #52606d; --line: #9aa5b1; --halo: #ffffff; --card: #ffffff; --card-line: #d9e2ec; }
  @media (prefers-color-scheme: dark) {
    :root { --ink: #e4e7eb; --muted: #9aa5b1; --line: #616e7c; --halo: #0d1117; --card: #161b22; --card-line: #30363d; }
  }
  text { font-family: 'Segoe UI', Montserrat, Helvetica, Arial, sans-serif; fill: var(--ink); }
  .t-title { font-size: 20px; font-weight: 700; }
  .t-label { font-size: 14px; font-weight: 700; }
  .t-small { font-size: 11.5px; fill: var(--muted); }
  .t-tiny { font-size: 10px; fill: var(--muted); }
  .t-on { fill: #ffffff; font-weight: 700; font-size: 12px; }
  .leader { stroke: var(--line); stroke-width: 1.2; fill: none; stroke-dasharray: 3 3; }
  .wire { stroke: var(--line); stroke-width: 1.6; fill: none; }
  .halo { paint-order: stroke; stroke: var(--halo); stroke-width: 4px; stroke-linejoin: round; }
  .card { fill: var(--card); stroke: var(--card-line); }
  .packet { offset-rotate: 0deg; animation: travel var(--dur, 3s) linear infinite; animation-delay: var(--delay, 0s); }
  @keyframes travel { from { offset-distance: 0%; opacity: 0; } 8% { opacity: 1; } 92% { opacity: 1; } to { offset-distance: 100%; opacity: 0; } }
  .pulse { animation: pulse 2.4s ease-in-out infinite; animation-delay: var(--delay, 0s); transform-box: fill-box; transform-origin: center; }
  @keyframes pulse { 0%, 100% { opacity: 0.35; } 50% { opacity: 1; } }
  .float { animation: float 6s ease-in-out infinite; animation-delay: var(--delay, 0s); }
  @keyframes float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-6px); } }
  .dash { stroke-dasharray: 6 6; animation: dash 1.2s linear infinite; }
  @keyframes dash { to { stroke-dashoffset: -12; } }
  .grow { transform-box: fill-box; transform-origin: left center; animation: grow 1.6s cubic-bezier(.2,.7,.2,1) both; animation-delay: var(--delay, 0s); }
  @keyframes grow { from { transform: scaleX(0); } }
  .fade { animation: fade 1s ease both; animation-delay: var(--delay, 0s); }
  @keyframes fade { from { opacity: 0; } }
  @media (prefers-reduced-motion: reduce) {
    .packet, .pulse, .float, .dash, .grow, .fade { animation: none; }
    .packet { offset-distance: 50%; }
  }
</style>
"""


def iso(x: float, y: float, z: float, ox: float, oy: float, s: float) -> tuple[float, float]:
    """Toạ độ thế giới (x sang phải-xuống, y sang trái-xuống, z lên) → toạ độ màn hình."""
    return ox + (x - y) * COS * s, oy + (x + y) * SIN * s - z * s


def pts(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{px:.1f},{py:.1f}" for px, py in points)


def box(x: float, y: float, z: float, w: float, d: float, h: float, color: str, ox: float, oy: float, s: float, opacity: float = 1.0, extra: str = "") -> str:
    top, left, right = FACES[color]
    p = lambda a, b, c: iso(a, b, c, ox, oy, s)  # noqa: E731
    top_face = [p(x, y, z + h), p(x + w, y, z + h), p(x + w, y + d, z + h), p(x, y + d, z + h)]
    left_face = [p(x, y + d, z + h), p(x + w, y + d, z + h), p(x + w, y + d, z), p(x, y + d, z)]
    right_face = [p(x + w, y, z + h), p(x + w, y + d, z + h), p(x + w, y + d, z), p(x + w, y, z)]
    return (
        f'<g opacity="{opacity}" {extra}>'
        f'<polygon points="{pts(left_face)}" fill="{left}"/>'
        f'<polygon points="{pts(right_face)}" fill="{right}"/>'
        f'<polygon points="{pts(top_face)}" fill="{top}"/>'
        "</g>"
    )


def svg(width: int, height: int, title: str, desc: str, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-labelledby="t d">'
        f'<title id="t">{title}</title><desc id="d">{desc}</desc>{STYLE}{body}</svg>\n'
    )


def packet(path: str, color: str, dur: float, delay: float, r: float = 4.5) -> str:
    return (
        f'<circle class="packet" r="{r}" fill="{color}" stroke="#ffffff" stroke-width="1.5" '
        f"style=\"offset-path: path('{path}'); --dur: {dur}s; --delay: {delay}s\"/>"
    )


# ---------------------------------------------------------------------------------------------------------------------
# 1. Kiến trúc theo tầng
# ---------------------------------------------------------------------------------------------------------------------


def architecture() -> str:
    s, ox, oy = 30, 560, 380
    parts: list[str] = []
    # Tầng (từ dưới lên): PostgreSQL, FastAPI, Next.js BFF, người dùng. Mỗi tầng là một khối nổi, có khe hở giữa.
    layers = [
        # (z, h, color, tiêu đề, chú thích)
        (0.0, 1.0, "navy", "PostgreSQL 16 · RLS theo tổ chức", "một schema · FORCE RLS · vai trò runtime không BYPASSRLS"),
        (3.6, 1.0, "blue", "FastAPI · api → services → models", "sàng lọc AI · Rubric Lab · chất lượng chương trình · tích hợp"),
        (7.2, 0.8, "teal", "Next.js 16 BFF", "cùng origin · cookie httpOnly · tổ chức từ tên miền"),
    ]
    x0, y0, w, d = 0.0, 0.0, 6.0, 6.0
    for i, (z, h, color, label, note) in enumerate(layers):
        parts.append(f'<g class="float" style="--delay: {i * 0.6}s">{box(x0, y0, z, w, d, h, color, ox, oy, s)}')
        if i == 0:  # ba lát dữ liệu của ba tổ chức trên mặt DB
            for k, c in enumerate(("amber", "violet", "green")):
                parts.append(box(0.6 + k * 1.7, 0.6, z + h, 1.4, 4.8, 0.18, c, ox, oy, s, extra=f'class="pulse" style="--delay: {k * 0.8}s"'))
        if i == 1:  # các mô-đun nghiệp vụ trên mặt API
            for k, c in enumerate(("slate", "amber", "violet", "green")):
                parts.append(box(0.5 + (k % 2) * 2.8, 0.5 + (k // 2) * 2.8, z + h, 2.2, 2.2, 0.35, c, ox, oy, s, opacity=0.95))
        parts.append("</g>")
        rx, ry = iso(x0 + w, y0, z + h / 2, ox, oy, s)
        lx = 860
        parts.append(f'<path class="leader" d="M{rx + 4:.1f},{ry:.1f} L{lx - 8},{ry:.1f}"/>')
        parts.append(f'<text class="t-label halo" x="{lx}" y="{ry - 2:.1f}">{label}</text>')
        parts.append(f'<text class="t-small halo" x="{lx}" y="{ry + 14:.1f}">{note}</text>')
    # Người dùng trên cùng: các khối nhỏ (ứng viên, nhân sự, quản trị).
    for k, (c, name) in enumerate((("amber", "Ứng viên"), ("violet", "Nhân sự · mentor"), ("green", "Quản trị IT"))):
        bx, by = 0.4 + k * 2.4, 3.6 - k * 1.2
        parts.append(f'<g class="float" style="--delay: {1.2 + k * 0.4}s">{box(bx, by, 9.6, 1.2, 1.2, 0.9, c, ox, oy, s)}</g>')
        tx, ty = iso(bx + 0.6, by + 0.6, 10.5, ox, oy, s)
        parts.append(f'<text class="t-small halo" text-anchor="middle" x="{tx:.1f}" y="{ty - 22:.1f}">{name}</text>')
    # Đường dữ liệu giữa các tầng (trục giữa), gói tin đi xuống rồi trả về.
    cx, cy_top = iso(3, 3, 9.6, ox, oy, s)
    _, cy_bff = iso(3, 3, 8.0, ox, oy, s)
    _, cy_api = iso(3, 3, 4.6, ox, oy, s)
    _, cy_db = iso(3, 3, 1.0, ox, oy, s)
    down = f"M{cx:.1f},{cy_top:.1f} L{cx:.1f},{cy_db:.1f}"
    up = f"M{cx + 10:.1f},{cy_db:.1f} L{cx + 10:.1f},{cy_top:.1f}"
    parts.append(f'<path class="wire dash" d="{down}"/><path class="wire dash" d="{up}"/>')
    for k in range(3):
        parts.append(packet(down, "#f2c46d", 3.2, k * 1.05))
        parts.append(packet(up, "#7fd1a3", 3.2, 0.5 + k * 1.05))
    _ = (cy_bff, cy_api)
    # Hai cụm bên: LLM (trái) và tích hợp (phải), nối vào tầng API.
    side = [
        (-7.6, 2.2, "red", "LLM tuỳ chọn", ("OpenRouter · OpenAI", "Gemini · Claude", "tự lùi về luật offline")),
        (0.6, 9.6, "amber", "Tích hợp", ("Power BI (CSV)", "LMS · CRM (khoá API)", "chỉ đọc theo phạm vi")),
    ]
    api_x, api_y = iso(3, 3, 4.1, ox, oy, s)
    for k, (sx, sy, color, label, lines) in enumerate(side):
        parts.append(f'<g class="float" style="--delay: {0.3 + k}s">{box(sx, sy, 3.2, 2.2, 2.2, 1.6, color, ox, oy, s)}</g>')
        tx, _ = iso(sx + 1.1, sy + 1.1, 4.0, ox, oy, s)
        _, bottom = iso(sx + 2.2, sy + 2.2, 3.2, ox, oy, s)
        parts.append(f'<text class="t-label halo" text-anchor="middle" x="{tx:.1f}" y="{bottom + 22:.1f}">{label}</text>')
        for j, line in enumerate(lines):
            parts.append(f'<text class="t-small halo" text-anchor="middle" x="{tx:.1f}" y="{bottom + 40 + j * 15:.1f}">{line}</text>')
        bx, by = iso(sx + 1.1, sy + 1.1, 4.0, ox, oy, s)
        path = f"M{api_x:.1f},{api_y:.1f} Q{(api_x + bx) / 2:.1f},{min(api_y, by) - 60:.1f} {bx:.1f},{by:.1f}"
        parts.append(f'<path class="wire dash" d="{path}"/>')
        parts.append(packet(path, FACES[color][1], 2.6, k * 0.9))
    parts.insert(0, '<text class="t-title" x="24" y="34">Kiến trúc theo tầng</text>')
    parts.insert(1, '<text class="t-small" x="24" y="54">Gói tin vàng: yêu cầu đi xuống · gói xanh: phản hồi · ba lát màu trên DB: dữ liệu của ba tổ chức</text>')
    return svg(1220, 620, "Kiến trúc Talent Hub", "Sơ đồ isometric ba tầng: Next.js BFF, FastAPI, PostgreSQL có RLS; bên cạnh là LLM và các tích hợp.", "".join(parts))


# ---------------------------------------------------------------------------------------------------------------------
# 2. Hành trình từ hồ sơ đến kết quả (có vòng phản hồi)
# ---------------------------------------------------------------------------------------------------------------------


def journey() -> str:
    s, ox, oy = 24, 90, 210
    steps = [
        ("blue", "Nộp hồ sơ", "6 bước, tự lưu"),
        ("blue", "Sàng lọc AI", "dẫn chứng nguyên văn"),
        ("blue", "Chấm mù", "AI ẩn đến khi chấm xong"),
        ("blue", "Phê duyệt 4 mắt", "người duyệt ≠ người đề xuất"),
        ("green", "Nhập học", "lớp · nhánh · thực chiến"),
        ("green", "Đánh giá năng lực", "mentor + LMS"),
        ("violet", "Chất lượng CT", "chuẩn đầu ra · cảnh báo"),
    ]
    parts = ['<text class="t-title" x="24" y="34">Từ hồ sơ đến kết quả, rồi quay lại cải tiến tuyển chọn</text>']
    parts.append('<text class="t-small" x="24" y="54">Con người ra mọi quyết định; AI chỉ gợi ý có dẫn chứng. Kết quả đào tạo đi ngược về Rubric Lab để chọn tốt hơn ở khoá sau.</text>')
    centers = []
    for i, (color, label, note) in enumerate(steps):
        gx, gy = i * 3.4, -i * 3.4
        z = 0.0
        parts.append(f'<g class="float" style="--delay: {i * 0.35}s">{box(gx, gy, z, 2.6, 2.6, 0.9 + 0.3 * (i % 2), color, ox, oy, s)}</g>')
        cx, cy = iso(gx + 1.3, gy + 1.3, 1.2, ox, oy, s)
        centers.append((cx, cy))
        tx, _ = iso(gx + 1.3, gy + 1.3, 0, ox, oy, s)
        _, ty = iso(gx + 2.6, gy + 2.6, 0, ox, oy, s)
        parts.append(f'<text class="t-label halo" text-anchor="middle" x="{tx:.1f}" y="{ty + 26:.1f}">{label}</text>')
        parts.append(f'<text class="t-tiny halo" text-anchor="middle" x="{tx:.1f}" y="{ty + 41:.1f}">{note}</text>')
    for k, (color, name) in enumerate((("blue", "Tuyển sinh"), ("green", "Đào tạo"), ("violet", "Cải tiến"))):
        lx = 900 + k * 92
        parts.append(f'<rect x="{lx}" y="24" width="12" height="12" rx="3" fill="{FACES[color][1]}"/>')
        parts.append(f'<text class="t-small" x="{lx + 18}" y="34">{name}</text>')
    path = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in centers)
    parts.insert(2, f'<path class="wire dash" d="{path}"/>')
    for k in range(4):
        parts.append(packet(path, "#f2c46d", 9, k * 2.25, r=5))
    # Vòng phản hồi: từ "Chất lượng CT" vòng lên trên về "Sàng lọc AI" qua Rubric Lab.
    (x_end, y_end), (x_start, y_start) = centers[-1], centers[1]
    top = min(y_end, y_start) - 110
    loop = f"M{x_end:.1f},{y_end - 30:.1f} C{x_end:.1f},{top:.1f} {x_start:.1f},{top:.1f} {x_start:.1f},{y_start - 30:.1f}"
    parts.append(f'<path class="wire dash" d="{loop}" stroke="#7b68c9" stroke-width="2.2"/>')
    parts.append(packet(loop, "#a99be6", 4.5, 0, r=5))
    parts.append(packet(loop, "#a99be6", 4.5, 2.25, r=5))
    mx = (x_end + x_start) / 2
    parts.append(f'<rect class="card" x="{mx - 150:.1f}" y="{top + 6:.1f}" width="300" height="40" rx="8"/>')
    parts.append(f'<text class="t-label" text-anchor="middle" x="{mx:.1f}" y="{top + 23:.1f}">Rubric Lab</text>')
    parts.append(f'<text class="t-tiny" text-anchor="middle" x="{mx:.1f}" y="{top + 38:.1f}">tiêu chí nào dự báo thành công · thử trọng số mới · kiểm tra công bằng</text>')
    return svg(1180, 345, "Hành trình từ hồ sơ đến kết quả", "Bảy bước từ nộp hồ sơ đến đánh giá chất lượng chương trình, với vòng phản hồi về Rubric Lab.", "".join(parts))


# ---------------------------------------------------------------------------------------------------------------------
# 3. Cô lập dữ liệu nhiều tổ chức (RLS)
# ---------------------------------------------------------------------------------------------------------------------


def tenancy() -> str:
    s, ox, oy = 30, 280, 250
    orgs = [("green", "scale"), ("violet", "demo-uni"), ("amber", "northwind")]
    parts = ['<text class="t-title" x="24" y="34">Mỗi truy vấn chỉ thấy dữ liệu của tổ chức mình</text>']
    parts.append('<text class="t-small" x="24" y="54">Tên miền → app.org_id → policy RLS trên mọi bảng thuộc tổ chức. Thiếu policy là test CI đỏ.</text>')
    for k, (color, name) in enumerate(orgs):
        z = k * 1.7
        active = name == "northwind"
        parts.append(box(0, 0, z, 5, 5, 0.75, color, ox, oy, s, opacity=1.0 if active else 0.28))
        if active:  # viền sáng nhấp nháy trên mặt lớp được đọc
            ring = [iso(0, 0, z + 0.75, ox, oy, s), iso(5, 0, z + 0.75, ox, oy, s), iso(5, 5, z + 0.75, ox, oy, s), iso(0, 5, z + 0.75, ox, oy, s)]
            parts.append(f'<polygon class="pulse" points="{pts(ring)}" fill="none" stroke="#ffd36b" stroke-width="3"/>')
        rx, ry = iso(5, 0, z + 0.4, ox, oy, s)
        parts.append(f'<path class="leader" d="M{rx + 4:.1f},{ry:.1f} L{rx + 70:.1f},{ry:.1f}"/>')
        status = "được đọc" if active else "bị chặn bởi RLS"
        parts.append(f'<text class="t-label halo" x="{rx + 78:.1f}" y="{ry + 4:.1f}">{name}</text>')
        parts.append(f'<text class="t-small halo" x="{rx + 78 + len(name) * 8.5 + 8:.1f}" y="{ry + 4:.1f}">— {status}</text>')
    # Tia truy vấn đi từ trên xuống, dừng ở lát northwind.
    tx, ty = iso(2.5, 2.5, 6.6, ox, oy, s)
    _, by = iso(2.5, 2.5, 4.15, ox, oy, s)
    beam = f"M{tx:.1f},{ty:.1f} L{tx:.1f},{by:.1f}"
    parts.append(f'<path class="wire dash" d="{beam}" stroke="#387aad" stroke-width="2.4"/>')
    for k in range(3):
        parts.append(packet(beam, "#134d8b", 2.4, k * 0.8, r=5.5))
    parts.append(f'<rect class="card" x="{tx - 120:.1f}" y="{ty - 46:.1f}" width="240" height="34" rx="8"/>')
    parts.append(f'<text class="t-small" text-anchor="middle" x="{tx:.1f}" y="{ty - 24:.1f}">SET LOCAL app.org_id = northwind</text>')
    return svg(860, 430, "Cô lập dữ liệu theo tổ chức", "Ba lớp dữ liệu của ba tổ chức trong một database; truy vấn với app.org_id = northwind chỉ đọc được lớp northwind.", "".join(parts))


# ---------------------------------------------------------------------------------------------------------------------
# 4. Hiệu năng trước/sau (hai biểu đồ riêng vì khác đơn vị — không dùng hai trục)
# ---------------------------------------------------------------------------------------------------------------------


def performance() -> str:
    before, after = "#93a3b5", "#1d6199"
    panels = [
        ("Sàng lọc AI 20.000 hồ sơ", "hồ sơ/giây · cao hơn là tốt", [("Trước", 95, "95"), ("Sau", 2000, "~2.000")], 2000, "nhanh hơn ~20 lần"),
        ("Rubric Lab (12.500 hồ sơ)", "p95 mili giây · thấp hơn là tốt", [("Trước", 1839, "1.839 ms"), ("Sau", 49, "49 ms")], 1839, "nhanh hơn ~37 lần"),
    ]
    parts = ['<text class="t-title" x="24" y="34">Hiệu năng ở quy mô 20.000 hồ sơ</text>']
    parts.append('<text class="t-small" x="24" y="54">Đo trên cùng máy, cùng dữ liệu; kết quả trước/sau giống hệt từng dòng (xem WORKLOG).</text>')
    for k, (title, unit, bars, vmax, verdict) in enumerate(panels):
        x0 = 24 + k * 470
        parts.append(f'<rect class="card" x="{x0}" y="76" width="446" height="176" rx="12"/>')
        parts.append(f'<text class="t-label" x="{x0 + 20}" y="104">{title}</text>')
        parts.append(f'<text class="t-tiny" x="{x0 + 20}" y="120">{unit}</text>')
        for j, (name, value, label) in enumerate(bars):
            y = 140 + j * 44
            width = max(4.0, 300 * value / vmax)
            color = before if j == 0 else after
            parts.append(f'<text class="t-small" x="{x0 + 20}" y="{y + 17}">{name}</text>')
            parts.append(f'<line x1="{x0 + 70}" y1="{y + 26}" x2="{x0 + 370}" y2="{y + 26}" stroke="var(--card-line)"/>')
            parts.append(f'<rect class="grow" style="--delay: {0.2 + j * 0.4}s" x="{x0 + 70}" y="{y + 4}" width="{width:.1f}" height="20" rx="4" fill="{color}"/>')
            parts.append(f'<text class="t-label fade" style="--delay: {0.9 + j * 0.4}s" x="{x0 + 78 + width:.1f}" y="{y + 19}">{label}</text>')
        parts.append(f'<text class="t-small fade" style="--delay: 1.6s" x="{x0 + 20}" y="238">→ {verdict}</text>')
    return svg(968, 270, "Hiệu năng trước và sau tối ưu", "Sàng lọc 20.000 hồ sơ: 95 lên khoảng 2.000 hồ sơ mỗi giây. Rubric Lab: p95 từ 1.839 xuống 49 mili giây.", "".join(parts))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    OUT.mkdir(parents=True, exist_ok=True)
    for name, build in (("architecture", architecture), ("journey", journey), ("tenancy", tenancy), ("performance", performance)):
        (OUT / f"{name}.svg").write_text(build(), encoding="utf-8")
        print("đã ghi", OUT / f"{name}.svg")


if __name__ == "__main__":
    main()
