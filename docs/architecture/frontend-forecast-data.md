# Frontend forecast file contract

Date: 2026-11-19. This is a separate visualization input, not a DecisionArtifact extension or a claim of model evaluation. Local HTTP GET `/forecast.json` is polled every five seconds while the automatic-update checkbox is enabled. `forecast-demo.json` is the explicit synthetic example. Imports disable automatic replacement. The frontend does not call a model or generate a research report.

Required fields:

| Field | Contract |
|---|---|
| ticker | AAPL, MSFT or NVDA |
| synthetic | Boolean; true always displays the synthetic warning |
| source | String up to 200 characters, displayed as text |
| as_of_utc | Parseable ISO timestamp with timezone |
| history | 2–5,000 rows, `{date, close}` |
| forecast | 1–1,000 rows, `{date, estimate, lower, upper}` |

Prices must be finite positive numbers no greater than 1e9. Dates in each array must increase strictly; history is at or before the cutoff and forecast is after it. Each interval must satisfy lower ≤ estimate ≤ upper. File imports reject files larger than 5 MiB before reading. Fetch responses have a text-size check after reading; this is not a streaming byte cap. Invalid parsing/shape/values preserve the last valid series and display an error. Existing JSON is not rewritten by the page.

The blue line represents the supplied history, the orange dashed line the supplied forecast estimate, and the purple band the supplied lower/upper values. The page does not establish calibrated probability coverage. Playback progressively reveals forecast points; history stays visible and is interactive. Automatic file replacement can update both arrays. A future backend exporter must produce this contract and explicitly state its source and synthetic status. That exporter and a real forecast stream are not implemented by this frontend work.
