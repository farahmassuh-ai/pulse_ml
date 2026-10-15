# Pulse Model Delivery Report

## 1. Data
- **Months used:** April, May, and June 2026 (MBTA Bus Arrival/Departure files).
- **Row counts before/after cleaning:** 7,432,763 raw rows. I dropped 592 rows with a delay outside -30 to +120 minutes and 6,690 rows that repeated the key (service date, route, direction, stop, scheduled), which left 7,425,481 rows in `stop_events`. 451,273 of them have no `actual`, so 6,974,208 rows have a label.

  | Month | Raw rows | Delay out of range | Duplicate keys | Loaded |
  |---|---|---|---|---|
  | April | 2,459,855 | 231 | 1,698 | 2,457,926 |
  | May | 2,484,472 | 176 | 1,866 | 2,482,430 |
  | June | 2,488,436 | 185 | 3,126 | 2,485,125 |

- **Late rate by split:** the three late rates are within 6 points of each other.

  | Split | Dates | Rows | Late rate |
  |---|---|---|---|
  | Train | Apr 1 to May 31 | 4,645,567 | 45.7% |
  | Validation | Jun 1 to Jun 15 | 1,155,852 | 49.2% |
  | Test | Jun 16 to Jun 30 | 1,172,789 | 43.3% |

- **DVC data version (md5):**
  - train: `6dbba79a079af00a8eb33995744dcce1`
  - val: `59c88b7daeb30ba6dd2a2ba50d360bd8`
  - test: `1984178d852bc39db62c55af6a2e74af`
- **Daily pull (inserted rows):** Wed 2026-10-14: 92,168 (a second run that day inserted 0). Thu 2026-10-15: 92,168. Both days give the same count because Wednesday and Thursday use the same weekday timetable, and both are close to the roughly 90,000 rows of a weekday in the historical files.

## 2. Baselines
Both models were trained on the train split and scored on the validation split. Both runs are in the MLflow experiment `pulse-baselines` and exported to `mlflow_runs.csv`.

- **Majority-class:** accuracy 0.508. It always predicts "not late", so its accuracy is 1 minus the validation late rate (49.2%). AUC-ROC 0.500, PR-AUC 0.492.
- **Logistic regression** (one-hot route, direction, stop, point type, standard type, hour, day of week): accuracy 0.657, AUC-ROC 0.719, PR-AUC 0.699.
- **What the baselines tell us:** the logistic regression is about 15 points more accurate than the majority class and raises AUC from 0.50 to 0.72, so route, stop, and time of day carry real signal about whether a bus will be late. The signal is still weak, so there is plenty of room to improve in Task 3.

## 3. Model Development
- Architectures and configs tried (reference MLflow run names)
- What improved results, what didn't, and your hypothesis why
- Final architecture description + parameter count
- How you handled the high-cardinality features (route, stop), and why

## 4. Final Evaluation (held-out test weeks)
- Accuracy, AUC-ROC, PR-AUC, recall, precision at chosen threshold
- Confusion matrix
- Calibration check: predicted vs. actual late rate by hour
- Route-level sanity check: top-5 predicted-late routes vs. actual

## 5. Threshold Recommendation
- Chosen operating threshold and the rider-experience rationale
- The precision/recall trade at 2-3 alternative thresholds

## 6. Reproducibility
- Git commit, DVC versions, MLflow experiment name, registered model version
- Exact command(s) to reproduce the winning run

## 7. Limitations & Next Steps
- What the model can't do; what you'd try with more time
- How would the picture change if "late" meant five minutes instead of three? Argue it qualitatively