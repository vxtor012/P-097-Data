"""
Extractor for relational vehicle pricing and rolling cost snapshot.
Transforms complex nested JSON into structured SilverVehicle records and knowledge markdown.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Generator, List

from src.extractors.base import BaseExtractor
from src.models.schemas import BronzeDocument, SilverVehicle

logger = logging.getLogger(__name__)


class RelationalExtractor(BaseExtractor):
    """Parses raw JSON snapshot of vehicle prices, editions, and rolling costs."""

    def __init__(self, bronze_dir: Path):
        self.bronze_dir = Path(bronze_dir)
        self.snapshot_path = (
            self.bronze_dir / "vinfast" / "relational" / "vinfast_rolling_raw_snapshot.json"
        )
        self._cached_vehicles: List[SilverVehicle] = []

    def get_structured_vehicles(self) -> List[SilverVehicle]:
        """Returns structured vehicle records."""
        if not self._cached_vehicles:
            list(self.extract_all())
        return self._cached_vehicles

    def extract_all(self) -> Generator[BronzeDocument, None, None]:
        """Extracts structured vehicles and yields a unified Silver/Bronze document."""
        if not self.snapshot_path.exists():
            logger.warning("Relational snapshot not found at %s", self.snapshot_path)
            return

        try:
            with open(self.snapshot_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            vehicles_data = data.get("vehicles", {})
            objects_data = data.get("objects", {})
            provinces = objects_data.get("provinces", [])
            fees = objects_data.get("fees", [])
            promotions_data = data.get("promotion", {}).get("records", [])

            self._cached_vehicles = []
            markdown_sections = ["# Bảng giá xe và chi phí lăn bánh VinFast toàn quốc\n"]

            # 1. Process Cars
            cars = vehicles_data.get("cars", {})
            car_models = cars.get("models", [])
            for m in car_models:
                v = self._process_vehicle_model(
                    model_meta=m,
                    vehicles_container=cars,
                    vehicle_type="car",
                    fees=fees,
                )
                if v:
                    self._cached_vehicles.append(v)
                    markdown_sections.append(v.searchable_markdown)

            # 2. Process Bikes
            bikes = vehicles_data.get("bikes", {})
            bike_models = bikes.get("models", [])
            for m in bike_models:
                v = self._process_vehicle_model(
                    model_meta=m,
                    vehicles_container=bikes,
                    vehicle_type="bike",
                    fees=fees,
                )
                if v:
                    self._cached_vehicles.append(v)
                    markdown_sections.append(v.searchable_markdown)

            full_markdown = "\n\n".join(markdown_sections)

            yield BronzeDocument(
                raw_id="vinfast_vehicles_catalog",
                source_type="relational_snapshot",
                source_file=str(self.snapshot_path),
                title="Bảng giá xe và chi phí lăn bánh VinFast toàn quốc (Dữ liệu cấu trúc)",
                url="https://vinfastauto.com/vn_vi/du-toan-chi-phi-lan-banh",
                category="gia_xe_va_chi_phi_lan_banh",
                domain="vinfastauto.com",
                raw_content=full_markdown,
                raw_metadata={
                    "total_vehicles": len(self._cached_vehicles),
                    "total_provinces": len(provinces),
                },
            )

        except Exception as e:
            logger.error("Failed to parse relational snapshot: %s", e)

    def _process_vehicle_model(
        self,
        model_meta: Dict[str, Any],
        vehicles_container: Dict[str, Any],
        vehicle_type: str,
        fees: List[Dict[str, Any]],
    ) -> SilverVehicle:
        model_id = model_meta.get("id", "")
        model_name = model_meta.get("name", "")
        detail = vehicles_container.get(model_id, {})

        editions = detail.get("listEdition", [])
        trims: List[Dict[str, Any]] = []

        for ed_code in editions:
            ed_data = detail.get(ed_code, {})
            label = ed_data.get("label", ed_code)
            price_str = ed_data.get("price", "0")
            price_val = ed_data.get("priceValue", 0)
            price_battery = ed_data.get("priceWithBattery", price_val)

            trims.append({
                "trim_code": ed_code,
                "label": label,
                "price_vnd": price_str,
                "price_value": price_val,
                "price_with_battery": price_battery,
            })

        # Calculate estimated rolling cost ranges based on license fees
        rolling_costs = {}
        for fee_info in fees:
            zone = fee_info.get("zone", "KV1")
            license_fee = (
                fee_info.get("carLicenseFee", 20000000)
                if vehicle_type == "car"
                else fee_info.get("bikeLicenseFeeMedium", 2000000)
            )
            rolling_costs[zone] = {
                "license_plate_fee": license_fee,
                "description": "Khu vực 1 (Hà Nội, TP.HCM)" if zone == "KV1" else "Các tỉnh thành khác",
            }

        # Synthesize clean markdown for RAG and search
        type_str = "Ô tô điện" if vehicle_type == "car" else "Xe máy điện"
        md_lines = [
            f"## {type_str} VinFast {model_name}",
            f"- **Loại phương tiện**: {type_str}",
            f"- **Mã định danh**: `{model_id}`",
            "",
            "### Các phiên bản và giá niêm yết:",
        ]

        if trims:
            md_lines.append("| Phiên bản | Giá thuê pin (VNĐ) | Giá kèm pin (VNĐ) |")
            md_lines.append("|---|---|---|")
            for t in trims:
                p_base = t['price_vnd'] if t['price_vnd'] else f"{t['price_value']:,} đ"
                p_bat = f"{t['price_with_battery']:,} đ" if t['price_with_battery'] else "Theo chính sách"
                md_lines.append(f"| {t['label']} | {p_base} | {p_bat} |")
        else:
            md_lines.append("- Liên hệ đại lý hoặc xem thông báo giá mới nhất.")

        md_lines.append("")
        md_lines.append("### Lệ phí đăng ký và biển số tham khảo:")
        md_lines.append("- Khu vực 1 (Hà Nội, TP.HCM): 20.000.000 VNĐ (ô tô) / 1.000.000 - 4.000.000 VNĐ (xe máy)")
        md_lines.append("- Khu vực 2, 3: 1.000.000 VNĐ (ô tô) / 50.000 - 150.000 VNĐ (xe máy)")
        md_lines.append("- Ô tô điện chạy pin được miễn 100% lệ phí trước bạ theo quy định của Chính phủ.")

        searchable_md = "\n".join(md_lines)

        return SilverVehicle(
            vehicle_id=model_id,
            model_name=model_name,
            vehicle_type=vehicle_type,
            trims=trims,
            battery_options=[],
            specifications={},
            promotions=[],
            rolling_costs=rolling_costs,
            searchable_markdown=searchable_md,
        )

    def get_relational_tables(self, cars_only: bool = False) -> Dict[str, List[Dict[str, Any]]]:
        """Extracts normalized relational tables for CSV export into rdb_schema."""
        if not self.snapshot_path.exists():
            return {}

        with open(self.snapshot_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        import os
        from datetime import datetime, timezone
        mtime = datetime.fromtimestamp(os.path.getmtime(self.snapshot_path), tz=timezone.utc)
        snapshot_dt = mtime.strftime("%Y-%m-%d %H:%M:%S UTC")

        # 1. Cars Catalog
        cars_catalog: List[Dict[str, Any]] = []
        model_name_map: Dict[str, str] = {}
        vehicles_data = data.get("vehicles", {})

        car_models = vehicles_data.get("cars", {}).get("models", [])
        for m in car_models:
            c_id = m.get("id", "")
            c_name = m.get("name", "")
            model_name_map[c_id] = c_name
            cars_catalog.append({
                "car_id": c_id,
                "car_name": c_name,
                "default_product_id": m.get("defaultProductID", ""),
                "vehicle_type": "Electric Car",
                "manufacturer": "VinFast",
                "snapshot_datetime": snapshot_dt,
            })

        if not cars_only:
            bike_models = vehicles_data.get("bikes", {}).get("models", [])
            for m in bike_models:
                b_id = m.get("id", "")
                b_name = m.get("name", "")
                model_name_map[b_id] = b_name
                cars_catalog.append({
                    "car_id": b_id,
                    "car_name": b_name,
                    "default_product_id": m.get("defaultProductID", ""),
                    "vehicle_type": "Electric Bike",
                    "manufacturer": "VinFast",
                    "snapshot_datetime": snapshot_dt,
                })

        # 2. Trims Pricing
        trims_pricing: List[Dict[str, Any]] = []
        costs = data.get("objects", {}).get("costs", [])
        for c in costs:
            model_id = c.get("model", "")
            if cars_only and "Car" not in model_id:
                continue

            car_name = model_name_map.get(model_id, model_id.replace("Products-Car-", ""))
            trim_name = c.get("ID", "")
            price = c.get("price") or c.get("basePrice") or 0
            try:
                price_val = int(float(price))
            except (ValueError, TypeError):
                price_val = 0

            is_battery_sales = c.get("isBatterySales", False)
            battery_option = "Kèm Pin (Mua Pin)" if is_battery_sales else "Thuê Pin"
            price_last_mod = c.get("lastModified") or snapshot_dt

            trims_pricing.append({
                "trim_id": f"{model_id}_{c.get('UUID', trim_name)}",
                "car_id": model_id,
                "car_name": car_name,
                "trim_name": trim_name,
                "battery_option": battery_option,
                "price_vat_vnd": price_val,
                "deposit_amount_vnd": 50000000 if price_val > 1000000000 else 15000000,
                "product_code": c.get("edition", ""),
                "price_last_updated": price_last_mod,
                "snapshot_datetime": snapshot_dt,
            })

        # 3. Provinces
        provinces: List[Dict[str, Any]] = []
        raw_provinces = data.get("objects", {}).get("provinces", [])
        for p in raw_provinces:
            provinces.append({
                "province_id": p.get("id", ""),
                "province_name": p.get("name", ""),
                "region_code": p.get("region", "2"),
                "snapshot_datetime": snapshot_dt,
            })

        # 4. Fee Rules
        fee_rules: List[Dict[str, Any]] = [
            {
                "fee_code": "REGISTRATION_FEE",
                "fee_name": "Lệ phí trước bạ ô tô điện",
                "rate_percent": "0.0",
                "fixed_amount_vnd": 0,
                "description": "Nghị định 10/2022/NĐ-CP & 50/2025/NĐ-CP: Ô tô điện chạy pin miễn 100% lệ phí trước bạ",
                "snapshot_datetime": snapshot_dt,
            },
            {
                "fee_code": "PLATE_FEE_HN_HCM",
                "fee_name": "Phí cấp biển số Khu vực I (Hà Nội, TP.HCM)",
                "rate_percent": "0.0",
                "fixed_amount_vnd": 20000000,
                "description": "Thông tư 60/2023/TT-BTC: Hà Nội và TP.HCM áp dụng 20.000.000 VNĐ",
                "snapshot_datetime": snapshot_dt,
            },
            {
                "fee_code": "PLATE_FEE_OTHER",
                "fee_name": "Phí cấp biển số Khu vực II & III (Tỉnh/Thành khác)",
                "rate_percent": "0.0",
                "fixed_amount_vnd": 1000000,
                "description": "Thông tư 60/2023/TT-BTC: Các tỉnh thành còn lại 1.000.000 VNĐ",
                "snapshot_datetime": snapshot_dt,
            },
            {
                "fee_code": "INSPECTION_FEE",
                "fee_name": "Phí kiểm định đăng kiểm",
                "rate_percent": "0.0",
                "fixed_amount_vnd": 340000,
                "description": "Thông tư 55/2022/TT-BTC: Xe con dưới 10 chỗ",
                "snapshot_datetime": snapshot_dt,
            },
            {
                "fee_code": "ROAD_MAINTENANCE_FEE",
                "fee_name": "Phí bảo trì đường bộ (1 năm)",
                "rate_percent": "0.0",
                "fixed_amount_vnd": 1560000,
                "description": "Nghị định 90/2023/NĐ-CP: Xe cá nhân 130.000 VNĐ/tháng",
                "snapshot_datetime": snapshot_dt,
            },
            {
                "fee_code": "MANDATORY_INSURANCE",
                "fee_name": "Bảo hiểm TNDS bắt buộc (1 năm)",
                "rate_percent": "0.0",
                "fixed_amount_vnd": 480700,
                "description": "Nghị định 67/2023/NĐ-CP: Xe dưới 6 chỗ không kinh doanh vận tải",
                "snapshot_datetime": snapshot_dt,
            },
        ]

        # 5. Rolling Cost Matrix (Major representative regions)
        key_provinces = [
            {"id": "01", "name": "Hà Nội", "plate_fee": 20000000},
            {"id": "79", "name": "TP. Hồ Chí Minh", "plate_fee": 20000000},
            {"id": "48", "name": "Đà Nẵng", "plate_fee": 1000000},
            {"id": "31", "name": "Hải Phòng", "plate_fee": 1000000},
            {"id": "92", "name": "Cần Thơ", "plate_fee": 1000000},
            {"id": "other", "name": "Các tỉnh thành khác (Khu vực II, III)", "plate_fee": 1000000},
        ]

        rolling_matrix: List[Dict[str, Any]] = []
        for t in trims_pricing:
            price = t["price_vat_vnd"]
            if price <= 0:
                continue

            for prov in key_provinces:
                plate_fee = prov["plate_fee"]
                reg_fee = 0
                insp_fee = 340000
                road_fee = 1560000
                ins_fee = 480700
                total_rolling = price + plate_fee + reg_fee + insp_fee + road_fee + ins_fee

                rolling_matrix.append({
                    "car_id": t["car_id"],
                    "car_name": t["car_name"],
                    "trim_name": t["trim_name"],
                    "battery_option": t["battery_option"],
                    "province_name": prov["name"],
                    "list_price_vnd": price,
                    "registration_fee_vnd": reg_fee,
                    "license_plate_fee_vnd": plate_fee,
                    "inspection_fee_vnd": insp_fee,
                    "road_fee_vnd": road_fee,
                    "mandatory_insurance_vnd": ins_fee,
                    "total_rolling_cost_vnd": total_rolling,
                    "snapshot_datetime": snapshot_dt,
                })

        return {
            "cars_catalog": cars_catalog,
            "trims_pricing": trims_pricing,
            "provinces": provinces,
            "fee_rules": fee_rules,
            "rolling_cost_matrix": rolling_matrix,
        }
