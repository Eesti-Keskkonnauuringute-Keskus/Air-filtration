# Air filtration (PM2.5) ecosystem service — Estonia

Python tool for calculating the **air filtration ecosystem service** (dry deposition of PM2.5
on vegetation) for the Estonian ecosystem accounts, following the Eurostat guidance note,
SEEA EA and Regulation (EU) 691/2011 as amended by (EU) 2024/3024.

Developed by the Estonian Environmental Research Centre (EKUK) for Statistics Estonia.
The tool reproduces the 2024 results of the report *Ökosüsteemi teenus: õhu filtreerimine*
(2026): **206.4 t PM2.5/yr** (main estimate), 109.8 t/yr (sensitivity, Sentinel-3 LAI).

* **Documentation (English):** [`air_filtration_tool/README.md`](air_filtration_tool/README.md)
* **Kasutusjuhend (eesti keeles):** [`air_filtration_tool/JUHEND_jooks.md`](air_filtration_tool/JUHEND_jooks.md)
* **Workflow diagram:** [`air_filtration_tool/docs/toovoog.png`](air_filtration_tool/docs/toovoog.png)

## Data

| Data | Provided by |
|---|---|
| Daily PM2.5 concentration field (Airviro, 1 km) | EKUK, every year |
| Ecosystem extent map | Statistics Estonia |
| ERA5-Land hourly wind, Sentinel-3 LAI | Copernicus Climate Data Store — downloaded by the tool |
| PROBA-V summer peak LAI, county boundaries | included in `air_filtration_tool/data/` |

## Licence

Code: [MIT](LICENSE). Data in `air_filtration_tool/data/` keep the licences of their providers.
