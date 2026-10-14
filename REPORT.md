# Pulse Model Delivery Report

## 1. Data
- Months used, row counts before/after cleaning
- Late-rate by split (train/val/test)
- DVC data version (md5) for each split

## 2. Baselines
- Majority-class: accuracy
- Logistic regression: accuracy, AUC, PR-AUC
- What the baselines tell us about the problem

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