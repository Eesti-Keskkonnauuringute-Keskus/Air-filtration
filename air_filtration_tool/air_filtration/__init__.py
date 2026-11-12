"""air_filtration - PM2.5 air-filtration ecosystem-service model.

Implements the Eurostat ENV_EA "Guidance note for accounting for the air
filtration ecosystem service in the EU" (advanced approach for PM2.5) with the
daily method used for the 2024 report (EKUK, October 2026).
"""
from .config import Config
from . import vd, aggregate, constants

__all__ = ["Config", "vd", "aggregate", "constants"]
__version__ = "0.2.0"
