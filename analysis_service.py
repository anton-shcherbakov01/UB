class AnalysisService:
    @staticmethod
    def calculate_metrics(raw_data: dict):
        if raw_data.get("status") == "error":
            return raw_data

        p = raw_data.get("prices", {})
        wallet = p.get("wallet_purple", 0)
        standard = p.get("standard_black", 0)
        base = p.get("base_crossed", 0)

        raw_data["metrics"] = {
            "wallet_benefit": standard - wallet if standard > wallet else 0,
            "total_discount_percent": round(((base - wallet) / base * 100), 1) if base > 0 else 0,
            "is_favorable": ((base - wallet) / base) > 0.45 if base > 0 else False
        }
        return raw_data

analysis_service = AnalysisService()