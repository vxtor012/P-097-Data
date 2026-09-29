"""src/data_pipeline/task1_vinfast_auto_crawl_data.py
Crawl toàn bộ dữ liệu bảng giá, tùy chọn màu sắc, lệ phí đăng ký,
chính sách ưu đãi và dự toán chi phí lăn bánh từ trang VinFast Auto:
https://shop.vinfastauto.com/vn_vi/chi-phi-lan-banh

Dữ liệu được trích xuất trực tiếp từ endpoint API của VinFast:
  RollingUpCost-GetInfoRolling
Sau đó lưu trữ có cấu trúc thành các file CSV trong:
  data/landing/relational/
"""

from __future__ import annotations

import csv
import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# Tự động cấu hình mã hóa UTF-8 cho stdout trên Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data"))
RELATIONAL_DIR = DATA_DIR / "landing" / "relational"
SNAPSHOT_PATH = RELATIONAL_DIR / "vinfast_rolling_raw_snapshot.json"


API_ENDPOINT = (
    "https://shop.vinfastauto.com/on/demandware.store/Sites-app_vinfast_vn-Site/vi_VN/"
    "RollingUpCost-GetInfoRolling"
)
PAGE_URL = "https://shop.vinfastauto.com/vn_vi/chi-phi-lan-banh"


def fetch_rolling_data(
    max_retries: int = 3,
    timeout: float = 25.0,
    session_handshake: bool = True,
    use_cache_fallback: bool = True,
    cache_path: Path | None = None,
    max_backoff: float = 30.0,
) -> dict[str, Any]:
    """Gọi API RollingUpCost-GetInfoRolling của VinFast để lấy toàn bộ dữ liệu cấu hình và giá.

    Cải tiến chống Potential API Failure (PR Review feedback):
    1. Session handshake: Sử dụng CookieJar để nhận và duy trì session/CSRF cookies từ PAGE_URL.
    2. Retry & Bounded Backoff: Tự động thử lại khi gặp sự cố mạng, có chặn trên max_backoff (tránh treo vô hạn).
    3. Local snapshot fallback: Khi API bị lỗi hoặc chặn kết nối, tự động fallback đọc từ file
       snapshot cục bộ gần nhất để pipeline dữ liệu không bị gãy đột ngột.
    """
    snapshot_file = cache_path or SNAPSHOT_PATH
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": PAGE_URL,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    # 1. Bước bắt tay phiên (Session handshake) để nhận cookie hợp lệ
    if session_handshake:
        try:
            handshake_req = urllib.request.Request(
                PAGE_URL,
                headers={"User-Agent": headers["User-Agent"]},
            )
            with opener.open(handshake_req, timeout=timeout) as _:
                pass
        except Exception as e:
            print(f"⚠️  Session handshake cảnh báo (vẫn tiếp tục gọi API): {e}")

    # 2. Vòng lặp gọi API kèm Retry & Exponential Backoff
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            print(f"🌐 Đang kết nối tới endpoint VinFast (lần {attempt}/{max_retries}): {API_ENDPOINT} ...")
            req = urllib.request.Request(API_ENDPOINT, headers=headers)
            with opener.open(req, timeout=timeout) as resp:
                content = resp.read().decode("utf-8")
                data = json.loads(content)

                if not isinstance(data, dict) or ("vehicles" not in data and "objects" not in data):
                    msg = "Phản hồi API không chứa cấu trúc 'vehicles' hoặc 'objects' hợp lệ."
                    raise ValueError(msg)

                print(f"✅ Tải dữ liệu thành công! Dung lượng phản hồi: {len(content):,} bytes.")

                # Lưu snapshot dự phòng cho các lần chạy sau
                try:
                    snapshot_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(snapshot_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                except Exception as save_err:
                    print(f"⚠️  Không thể lưu snapshot dự phòng: {save_err}")

                return data

        except Exception as err:
            last_error = err
            print(f"⚠️  Lần thử {attempt}/{max_retries} thất bại: {err}")
            if attempt < max_retries:
                backoff = min(float(2 ** (attempt - 1)), max_backoff)
                time.sleep(backoff)

    # 3. Fallback sang snapshot cục bộ nếu có
    if use_cache_fallback and snapshot_file.exists():
        print(f"\n⚠️  [FALLBACK] API VinFast không thể truy cập sau {max_retries} lần thử: {last_error}")
        print(f"📂 Đang tự động nạp dữ liệu từ snapshot cục bộ dự phòng: {snapshot_file.name} ...")
        with open(snapshot_file, encoding="utf-8") as f:
            data = json.load(f)
            print(f"✅ Nạp thành công dữ liệu từ snapshot ({len(data)} khóa cấp cao).")
            return data

    raise RuntimeError(
        f"Không thể tải dữ liệu từ API VinFast sau {max_retries} lần thử và không có snapshot dự phòng: {last_error}"
    )


def export_car_editions_pricing(data: dict[str, Any]) -> int:
    """Lưu bảng giá các phiên bản xe ô tô: giá niêm yết, pin, phí cố định."""
    cars = data.get("vehicles", {}).get("cars", {})
    models_list = cars.get("models", [])
    costs = data.get("objects", {}).get("costs", [])

    model_names = {m["id"]: m["name"] for m in models_list}
    file_path = RELATIONAL_DIR / "vinfast_car_editions_pricing.csv"

    fieldnames = [
        "model_id",
        "model_name",
        "edition_id",
        "edition_name",
        "base_price_vnd",
        "price_vnd",
        "price_with_battery_vnd",
        "battery_price_vnd",
        "road_maintenance_fee_1yr",
        "civil_insurance_fee_1yr",
        "inspection_fee",
        "fee_other",
        "default_color",
        "deposit_page_url",
    ]

    rows = []
    for c in costs:
        m_id = c.get("model", "")
        if not m_id.startswith("Products-Car-"):
            continue

        ed_id = c.get("edition", "")
        m_info = cars.get(m_id, {})
        ed_info = m_info.get(ed_id, {}) if isinstance(m_info, dict) else {}
        ed_label = ed_info.get("label", ed_id) if isinstance(ed_info, dict) else ed_id
        m_name = model_names.get(m_id, m_id.replace("Products-Car-", ""))

        page = c.get("page", "")
        deposit_url = f"https://shop.vinfastauto.com/vn_vi/{page}.html" if page else ""

        rows.append({
            "model_id": m_id,
            "model_name": m_name,
            "edition_id": ed_id,
            "edition_name": ed_label,
            "base_price_vnd": c.get("basePrice", 0),
            "price_vnd": c.get("price", 0),
            "price_with_battery_vnd": c.get("priceWithBattery", 0),
            "battery_price_vnd": c.get("battery", 0),
            "road_maintenance_fee_1yr": c.get("roadMaintenance", 1560000),
            "civil_insurance_fee_1yr": c.get("insurance", 480700),
            "inspection_fee": c.get("register", 340000),
            "fee_other": c.get("fee", 0),
            "default_color": c.get("color", ""),
            "deposit_page_url": deposit_url,
        })

    with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"📁 Đã xuất: {file_path.name} ({len(rows)} phiên bản xe ô tô)")
    return len(rows)


def export_car_color_options(data: dict[str, Any]) -> int:
    """Lưu bảng tùy chọn màu sắc xe, phụ phí màu, và giá xe theo từng màu."""
    cars = data.get("vehicles", {}).get("cars", {})
    models_list = cars.get("models", [])
    colors_cfg = data.get("objects", {}).get("colors", {})
    costs = data.get("objects", {}).get("costs", [])

    cost_dict = {
        (c.get("model"), c.get("edition")): c.get("price", 0)
        for c in costs
        if c.get("model", "").startswith("Products-Car-")
    }

    file_path = RELATIONAL_DIR / "vinfast_car_color_options.csv"

    fieldnames = [
        "model_id",
        "model_name",
        "edition_id",
        "edition_name",
        "color_code",
        "color_name",
        "color_type",
        "color_extra_price_vnd",
        "total_car_price_vnd",
        "image_url",
    ]

    rows = []
    for m in models_list:
        m_id = m["id"]
        m_name = m["name"]
        m_info = cars.get(m_id, {})
        if not isinstance(m_info, dict):
            continue

        for ed_id in m_info.get("listEdition", []):
            ed_info = m_info.get(ed_id, {})
            if not isinstance(ed_info, dict):
                continue

            ed_label = ed_info.get("label", ed_id)
            base_car_price = cost_dict.get((m_id, ed_id), 0)

            # Tra cứu bảng màu nâng cao / cơ bản từ colors_cfg
            ed_cfg = colors_cfg.get(m_id, {}).get(ed_id, {})
            extra_price_map = {}
            color_type_map = {}
            if isinstance(ed_cfg, dict) and ed_cfg.get("enable"):
                for group in ed_cfg.get("colors", []):
                    extra = group.get("priceValue", 0) or 0
                    c_type = "Màu nâng cao" if extra > 0 else "Màu cơ bản"
                    for ext in group.get("extcode", []):
                        extra_price_map[ext] = extra
                        color_type_map[ext] = c_type

            for c_code in ed_info.get("listColor", []):
                c_data = ed_info.get(c_code, {})
                if not isinstance(c_data, dict):
                    continue

                c_label = c_data.get("label", c_code)
                extra_price = extra_price_map.get(c_code, 0)
                c_type = color_type_map.get(c_code, "Màu cơ bản" if extra_price == 0 else "Màu nâng cao")

                # Giá có sẵn trong c_data hoặc tính theo base_price + extra_price
                color_price_dict = c_data.get("price") or {}
                if isinstance(color_price_dict, dict) and color_price_dict.get("value"):
                    total_price = color_price_dict.get("value")
                else:
                    total_price = base_car_price + extra_price

                img_url = ""
                img_obj = c_data.get("image") or {}
                if isinstance(img_obj, dict):
                    img_url = img_obj.get("absURL") or img_obj.get("url") or ""

                rows.append({
                    "model_id": m_id,
                    "model_name": m_name,
                    "edition_id": ed_id,
                    "edition_name": ed_label,
                    "color_code": c_code,
                    "color_name": c_label,
                    "color_type": c_type,
                    "color_extra_price_vnd": extra_price,
                    "total_car_price_vnd": total_price,
                    "image_url": img_url,
                })

    with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"📁 Đã xuất: {file_path.name} ({len(rows)} tùy chọn màu xe)")
    return len(rows)


def export_provinces_fees(data: dict[str, Any]) -> int:
    """Lưu bảng thông tin 63 tỉnh/thành, khu vực và biểu phí đăng ký/biển số."""
    provinces = data.get("objects", {}).get("provinces", [])
    fees = data.get("objects", {}).get("fees", [])
    fee_dict = {f.get("zone"): f for f in fees}

    file_path = RELATIONAL_DIR / "vinfast_provinces_fees.csv"

    fieldnames = [
        "province_id",
        "province_name",
        "zone",
        "car_license_plate_fee_vnd",
        "car_registration_fee_pct",
        "bike_license_fee_low_vnd",
        "bike_license_fee_medium_vnd",
        "bike_license_fee_high_vnd",
        "bike_registration_fee_pct",
    ]

    rows = []
    for p in provinces:
        zone = p.get("zone", "")
        zone_fee = fee_dict.get(zone, {})

        rows.append({
            "province_id": p.get("ID", ""),
            "province_name": p.get("name", ""),
            "zone": zone,
            "car_license_plate_fee_vnd": zone_fee.get("carLicenseFee", 1000000),
            "car_registration_fee_pct": p.get("carRegistrationFee", 0.0),
            "bike_license_fee_low_vnd": zone_fee.get("bikeLicenseFeeLow", 0),
            "bike_license_fee_medium_vnd": zone_fee.get("bikeLicenseFeeMedium", 0),
            "bike_license_fee_high_vnd": zone_fee.get("bikeLicenseFeeHigh", 0),
            "bike_registration_fee_pct": p.get("bikeRegistrationFee", 0.0),
        })

    with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"📁 Đã xuất: {file_path.name} ({len(rows)} tỉnh thành & biểu phí)")
    return len(rows)


def export_promotions(data: dict[str, Any]) -> int:
    """Lưu bảng các chính sách ưu đãi giảm giá (VinClub, O2O, Chuyển đổi xanh...)."""
    promos = data.get("promotion", {}).get("records", [])
    file_path = RELATIONAL_DIR / "vinfast_promotions.csv"

    fieldnames = [
        "promo_id",
        "promo_type",
        "promo_name",
        "discount_percent",
        "discount_amount_vnd",
        "description",
        "is_active",
    ]

    rows = []
    for pr in promos:
        rows.append({
            "promo_id": pr.get("ID", ""),
            "promo_type": pr.get("type", ""),
            "promo_name": pr.get("name", ""),
            "discount_percent": pr.get("discountPercent", 0),
            "discount_amount_vnd": pr.get("discountAmount", 0),
            "description": pr.get("description", ""),
            "is_active": pr.get("active", True),
        })

    with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"📁 Đã xuất: {file_path.name} ({len(rows)} chương trình ưu đãi)")
    return len(rows)


def export_bike_pricing(data: dict[str, Any]) -> int:
    """Lưu bảng giá và chi phí đăng ký xe máy điện VinFast."""
    costs = data.get("objects", {}).get("costs", [])
    file_path = RELATIONAL_DIR / "vinfast_bike_pricing.csv"

    bike_costs = [c for c in costs if c.get("model", "").startswith("Products-Scooter-")]

    fieldnames = [
        "model_id",
        "model_name",
        "price_vnd",
        "battery_purchase_price_vnd",
        "battery_leasing_price_vnd",
        "deposit_page_url",
    ]

    rows = []
    for c in bike_costs:
        m_id = c.get("model", "")
        m_name = c.get("ID", m_id.replace("Products-Scooter-", ""))
        page = c.get("page", "")
        deposit_url = f"https://shop.vinfastauto.com/vn_vi/{page}.html" if page else ""

        rows.append({
            "model_id": m_id,
            "model_name": m_name,
            "price_vnd": c.get("price", 0),
            "battery_purchase_price_vnd": c.get("battery", 0),
            "battery_leasing_price_vnd": c.get("leasingBattery", 0),
            "deposit_page_url": deposit_url,
        })

    with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"📁 Đã xuất: {file_path.name} ({len(rows)} dòng xe máy điện)")
    return len(rows)


def export_car_rolling_cost_summary(data: dict[str, Any]) -> int:
    """Tạo bảng ma trận tính toán chi phí lăn bánh hoàn chỉnh cho các dòng xe và tỉnh thành đại diện.

    Công thức theo đúng logic của hệ thống dự toán VinFast:
      - Phí trước bạ: 0 đ (ô tô điện được nhà nước miễn 100%)
      - Phí biển số: 14.000.000 đ (KV1: Hà Nội, TP.HCM) hoặc 1.000.000 đ (KV2/KV3)
      - Phí bảo trì đường bộ: 1.560.000 đ/năm
      - Bảo hiểm TNDS: 480.700 đ/năm
      - Phí đăng kiểm: 340.000 đ
      - Tổng phí thủ tục = Phí trước bạ + Phí biển số + Đăng kiểm + Bảo trì đường bộ + Bảo hiểm TNDS
      - Chi phí lăn bánh dự kiến = Giá xe (gồm tùy chọn màu) + Tổng phí thủ tục
    """
    cars = data.get("vehicles", {}).get("cars", {})
    models_list = cars.get("models", [])
    model_names = {m["id"]: m["name"] for m in models_list}
    costs = data.get("objects", {}).get("costs", [])
    fees = data.get("objects", {}).get("fees", [])
    fee_dict = {f.get("zone"): f for f in fees}
    provinces = data.get("objects", {}).get("provinces", [])

    file_path = RELATIONAL_DIR / "vinfast_car_rolling_costs.csv"

    fieldnames = [
        "model_id",
        "model_name",
        "edition_id",
        "edition_name",
        "car_base_price_vnd",
        "province_name",
        "zone",
        "registration_fee_vnd",
        "license_plate_fee_vnd",
        "road_maintenance_fee_1yr",
        "civil_insurance_fee_1yr",
        "inspection_fee",
        "total_mandatory_fees_vnd",
        "total_rolling_cost_vnd",
    ]

    rows = []
    # Chọn danh sách các tỉnh tiêu biểu cho từng vùng để tạo bảng lăn bánh trực quan
    selected_provinces = [
        p for p in provinces
        if p.get("name") in [
            "Hà Nội",
            "TP. Hồ Chí Minh",
            "Đà Nẵng",
            "Hải Phòng",
            "Cần Thơ",
            "Bình Dương",
            "Đồng Nai",
            "Quảng Ninh",
        ]
    ]
    if not selected_provinces:
        selected_provinces = provinces[:10]

    for c in costs:
        m_id = c.get("model", "")
        if not m_id.startswith("Products-Car-"):
            continue

        ed_id = c.get("edition", "")
        m_name = model_names.get(m_id, m_id.replace("Products-Car-", ""))
        ed_info = cars.get(m_id, {}).get(ed_id, {})
        ed_label = ed_info.get("label", ed_id) if isinstance(ed_info, dict) else ed_id

        car_price = int(c.get("price", 0))
        road_fee = int(c.get("roadMaintenance", 1560000))
        insurance_fee = int(c.get("insurance", 480700))
        inspection_fee = int(c.get("register", 340000))

        for prov in selected_provinces:
            p_name = prov.get("name", "")
            zone = prov.get("zone", "KV3")
            zone_fee = fee_dict.get(zone, {})

            # Xe điện miễn 100% trước bạ
            reg_fee = 0
            plate_fee = int(zone_fee.get("carLicenseFee", 1000000))

            mandatory_fees = reg_fee + plate_fee + road_fee + insurance_fee + inspection_fee
            total_rolling = car_price + mandatory_fees

            rows.append({
                "model_id": m_id,
                "model_name": m_name,
                "edition_id": ed_id,
                "edition_name": ed_label,
                "car_base_price_vnd": car_price,
                "province_name": p_name,
                "zone": zone,
                "registration_fee_vnd": reg_fee,
                "license_plate_fee_vnd": plate_fee,
                "road_maintenance_fee_1yr": road_fee,
                "civil_insurance_fee_1yr": insurance_fee,
                "inspection_fee": inspection_fee,
                "total_mandatory_fees_vnd": mandatory_fees,
                "total_rolling_cost_vnd": total_rolling,
            })

    with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"📁 Đã xuất: {file_path.name} ({len(rows)} ma trận dự toán lăn bánh)")
    return len(rows)


def run_relational_crawl() -> dict[str, int]:
    """Hàm điều phối crawl toàn bộ dữ liệu quan hệ."""
    print("=" * 65)
    print("🚀 BẮT ĐẦU CRAWL DỮ LIỆU GIÁ & DỰ TOÁN LĂN BÁNH VINFAST AUTO")
    print(f"   Trang nguồn: {PAGE_URL}")
    print(f"   Thư mục đích: {RELATIONAL_DIR}")
    print("=" * 65)

    RELATIONAL_DIR.mkdir(parents=True, exist_ok=True)
    data = fetch_rolling_data()

    print("\n📊 Đang xử lý và bóc tách dữ liệu ra các file CSV quan hệ...")
    res = {
        "car_editions": export_car_editions_pricing(data),
        "car_colors": export_car_color_options(data),
        "provinces_fees": export_provinces_fees(data),
        "promotions": export_promotions(data),
        "bike_pricing": export_bike_pricing(data),
        "rolling_costs": export_car_rolling_cost_summary(data),
    }

    print("\n🎉 Hoàn thành toàn bộ quá trình crawl và lưu trữ CSV thành công!")
    print(f"   Vị trí lưu trữ: {RELATIONAL_DIR}")
    return res


def main():
    try:
        run_relational_crawl()
    except Exception as e:
        print(f"❌ Không thể hoàn thành crawl dữ liệu quan hệ: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

