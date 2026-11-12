"""Õhufiltratsiooni töövoog ühe käivitusega - iga sammu juures küsitakse,
kas jooksutada uuesti või kasutada olemasolevaid tulemusi.

Käivita tööriista kaustas (conda keskkond air-filtration):
    python run_air_filtration.py
    python run_air_filtration.py --config config_daily_2024.yaml
    python run_air_filtration.py --config config_daily_2024.yaml --auto      (küsimusteta)
    python run_air_filtration.py --config config_daily_2024.yaml --alates 4  (alusta arvutusest)
"""
from air_filtration.workflow import main

raise SystemExit(main())
