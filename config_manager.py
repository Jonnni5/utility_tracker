import json
from pathlib import Path

DEFAULT_CONFIG = {
    "theme": "System",
    "residents_count": 1,
    "water_risers_count": 1,
    "electricity_mode": "single",
    "services_mkd": [
        {"name": "Электричество", "unit": "кВт·ч"},
        {"name": "Холодная вода", "unit": "м³"},
        {"name": "Горячая вода", "unit": "м³"},
        {"name": "Отопление", "unit": "Гкал"},
        {"name": "Содержание жилья", "unit": "₽"}
    ],
    "services_house": [
        {"name": "Электричество", "unit": "кВт·ч"},
        {"name": "Вода", "unit": "м³"},
        {"name": "Газ", "unit": "м³"},
        {"name": "Вывоз мусора/ТБО", "unit": "₽"}
    ]
}

class ConfigManager:
    def __init__(self):
        self.path = Path(__file__).parent / "config.json"
        self.data = DEFAULT_CONFIG.copy()
        self.load()

    def load(self):
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    # Объединяем с дефолтными, чтобы не потерять новые ключи
                    self.data = {**DEFAULT_CONFIG, **loaded}
            except Exception:
                pass
        self.save()

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()